"""GUI input for the voice agent (imported by va-act). Everything here is guarded IN CODE:
 - blocklist on the active window (terminals, auth dialogs, password managers, sensitive titles) -> refuse
 - typed text is length-limited and refused if it looks like a password
 - rate limit per user command (the daemon resets the counter at each new prompt)
 - panic flag (set by the daemon on "stop") refuses every action until the next prompt
 - every action is logged to ~/.cache/va-actions.log (typed text longer than 40 chars is never logged)
 - VA_DRY=1: print what would happen, touch nothing
"""
import json, os, re, subprocess, sys, tempfile, time

RUNDIR = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
STATE = os.environ.get("VA_STATE") or os.path.join(RUNDIR, "va-gui.json")      # {"count": n, "last": t}
PANIC = os.environ.get("VA_PANIC") or os.path.join(RUNDIR, "va-panic")
LOG = os.environ.get("VA_LOG") or os.path.expanduser("~/.cache/va-actions.log")
ARMED = os.environ.get("VA_ARMED") or os.path.expanduser("~/.cache/voice-agent/armed")   # written only by holdtalk.py
ARM_SECONDS = 180
MAX_ACTIONS = int(os.environ.get("VA_MAX_ACTIONS", "30"))
MAX_TYPE = 300
ENV = dict(os.environ, YDOTOOL_SOCKET=os.path.join(RUNDIR, ".ydotool_socket"))


def dry():
    return os.environ.get("VA_DRY") == "1"


class Refused(Exception):
    pass


# ---------------------------------------------------------------- blocklist
# Window classes / resource names (lower case substring match).
BLOCK_CLASS = [
    "konsole", "yakuake", "xterm", "uxterm", "urxvt", "rxvt", "alacritty", "kitty", "foot", "wezterm", "gnome-terminal", "terminator",
    "tilix", "ptyxis", "xfce4-terminal", "lxterminal", "terminology", "cool-retro-term", "qterminal", "guake", "tmux", "terminal",
    "polkit", "pkexec", "authentication", "kwallet", "ksshaskpass", "pinentry", "seahorse", "gcr-prompter", "kscreenlocker", "ksmserver",
    "systemsettings", "kcmshell", "keepass", "bitwarden", "1password", "lastpass", "enpass", "proton-pass", "protonpass", "dashlane",
    "kleopatra", "plasma-welcome",
]
# Title words / phrases (case-insensitive, word-ish boundaries).
BLOCK_TITLE_WORDS = [
    r"log ?in", r"log ?on", r"sign ?in", r"sign ?up", r"password\w*", r"pass ?code", r"otp", r"2fa", r"two[- ]factor", r"verification code",
    r"bank\w*", r"payments?", r"pay", r"pay\w+", r"checkout", r"wallet", r"billing", r"card", r"cards", r"credit", r"confirm purchase",
    r"delete account", r"authenticat\w+", r"authorization required", r"unlock", r"secret", r"private key",
]
_TITLE_RE = re.compile(r"(?<![a-z0-9])(?:" + "|".join(BLOCK_TITLE_WORDS) + r")(?![a-z0-9])", re.I)
BROWSER_CLASSES = ("helium", "chromium", "google-chrome", "chrome", "brave")


def check_window(win):
    """Return a refusal reason for this active-window dict ({'cls','name','title'}), or None if acting is allowed."""
    if not win:
        return "no active window"
    cls = ((win.get("cls") or "") + " " + (win.get("name") or "")).lower()
    title = win.get("title") or ""
    for b in BLOCK_CLASS:
        if b in cls:
            return f"active window is blocked ({b})"
    m = _TITLE_RE.search(title)
    if m:
        return f"window title looks sensitive ({m.group(0).lower()})"
    return None


def looks_like_password(text):
    """Heuristic: a single token of 8-64 chars mixing letter, digit and symbol, or text that mentions a password."""
    if re.search(r"pass(word|code|phrase)|\bpin\b|\botp\b|secret|api[_ -]?key|token", text, re.I):
        return True
    if " " not in text and 8 <= len(text) <= 64:
        kinds = sum(bool(re.search(p, text)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
        if kinds >= 3 and re.search(r"\d", text) and re.search(r"[A-Za-z]", text):
            return True
    return False


# ---------------------------------------------------------------- log, rate limit, panic
def trim(s, n=40):
    s = str(s).replace("\n", " ")
    return s if len(s) <= n else f"<{len(s)} chars>"


def log_action(sub, arg, win, outcome):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        w = f"{(win or {}).get('cls', '?')}|{trim((win or {}).get('title', '?'), 60)[:60]}"
        with open(LOG, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {sub} {trim(arg)!r} [{w}] {outcome}\n")
        os.chmod(LOG, 0o600)
    except OSError:
        pass


def _count(add=0):
    try:
        st = json.load(open(STATE))
    except (OSError, ValueError):
        st = {"count": 0, "last": 0}
    if time.time() - st.get("last", 0) > 300:      # stale: a new command
        st = {"count": 0, "last": 0}
    if add:
        st["count"] += add
        st["last"] = time.time()
        try:
            json.dump(st, open(STATE, "w"))
        except OSError:
            pass
    return st["count"]


def armed():
    """True only while the stamp written by holdtalk after a real Right Shift hold is fresh (<= 180 s). Never written by the agent."""
    try:
        st = os.stat(ARMED)
        age = time.time() - float(open(ARMED).read().strip())
        return st.st_uid == os.getuid() and not st.st_mode & 0o022 and -5 <= age <= ARM_SECONDS and -5 <= time.time() - st.st_mtime <= ARM_SECONDS
    except (OSError, ValueError):
        return False


def require_armed():
    if not armed():
        raise Refused("not armed: hold Right Shift and speak to arm me (the permission lasts 3 minutes)")


def panic_active():
    return os.path.exists(PANIC)


# ---------------------------------------------------------------- KWin
_calls = 0


def kwin_eval(js, timeout=4000):
    """Run a KWin script that calls org.va.Report(json string); return the parsed value (or None)."""
    import dbus, dbus.service, dbus.mainloop.glib
    from gi.repository import GLib
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    got, loop = [], GLib.MainLoop()
    global _calls
    _calls += 1
    name = "org.va.Gui%d" % os.getpid()
    path = "/r%d" % _calls

    class R(dbus.service.Object):
        @dbus.service.method(name, in_signature="s")
        def Report(self, s):
            got.append(s)
            loop.quit()

    bn = dbus.service.BusName(name, bus)
    R(bus, path)
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(js.replace("@NAME@", name).replace("@PATH@", path)); f.close()
    sname = "vagui%d" % os.getpid()
    kc = lambda path, iface, m, sig="", *a: bus.call_blocking("org.kde.KWin", path, iface, m, sig, a)
    try:
        sid = kc("/Scripting", "org.kde.kwin.Scripting", "loadScript", "ss", f.name, sname)
        kc(f"/Scripting/Script{sid}", "org.kde.kwin.Script", "run")
        GLib.timeout_add(timeout, loop.quit)
        loop.run()
    finally:
        try:
            kc("/Scripting", "org.kde.kwin.Scripting", "unloadScript", "s", sname)
        except Exception:
            pass
        os.unlink(f.name)
    return json.loads(got[0]) if got else None


ACTIVE_JS = ('var w=workspace.activeWindow;var o=null;if(w){o={cls:String(w.resourceClass),name:String(w.resourceName),'
             'title:String(w.caption),x:w.frameGeometry.x,y:w.frameGeometry.y,w:w.frameGeometry.width,h:w.frameGeometry.height};}'
             'var s=workspace.virtualScreenSize;callDBus("@NAME@","@PATH@","@NAME@","Report",JSON.stringify({win:o,sw:s.width,sh:s.height}));')


def screen_and_window():
    if dry() and os.environ.get("VA_FAKE_WINDOW"):
        return json.loads(os.environ["VA_FAKE_WINDOW"]), (1920, 1080)
    r = kwin_eval(ACTIVE_JS)
    if not r:
        return None, (1920, 1080)
    return r.get("win"), (r.get("sw") or 1920, r.get("sh") or 1080)


def gate(sub, arg="", cost=1, require_browser=False):
    """Every GUI action goes through here first. Returns (win, screen). Raises Refused."""
    win, scr = None, (1920, 1080)
    try:
        if panic_active():
            raise Refused("stopped by the user (panic stop); wait for the next command")
        require_armed()
        win, scr = screen_and_window()
        why = check_window(win)
        if why:
            raise Refused(why)
        if require_browser and not any(b in ((win.get("cls") or "") + (win.get("name") or "")).lower() for b in BROWSER_CLASSES):
            raise Refused("the active window is not the browser; run: va-act focus helium")
        if _count() + cost > MAX_ACTIONS:
            raise Refused(f"rate limit reached ({MAX_ACTIONS} GUI actions for this command); ask the user to continue")
    except Refused as e:
        log_action(sub, arg, win, "REFUSED: " + str(e))
        raise
    _count(cost)
    log_action(sub, arg, win, "DRY" if dry() else "ok")
    return win, scr


# ---------------------------------------------------------------- keys
_codes = {}
for c, v in zip("qwertyuiop", range(16, 26)): _codes[c] = v
for c, v in zip("asdfghjkl", range(30, 39)): _codes[c] = v
for c, v in zip("zxcvbnm", range(44, 51)): _codes[c] = v
for i, c in enumerate("1234567890"): _codes[c] = 2 + i
for i in range(1, 11): _codes[f"f{i}"] = 58 + i
_codes.update({"f11": 87, "f12": 88, "enter": 28, "return": 28, "escape": 1, "esc": 1, "space": 57, "tab": 15, "backspace": 14,
               "up": 103, "down": 108, "left": 105, "right": 106, "home": 102, "end": 107, "pageup": 104, "pagedown": 109,
               "minus": 12, "equal": 13, "plus": 13, "comma": 51, "period": 52, "slash": 53})
# Deliberately absent: delete, insert, super/meta, print, sysrq, power, media keys.
MODS = {"ctrl": 29, "control": 29, "shift": 42, "alt": 56}
def parse_combo(s):
    raw = s.strip().lower()
    parts = [p for p in raw.split("+") if p]
    if raw.endswith("+") or not parts or len(parts) > 4:
        raise Refused("bad key combo (write the + key as 'plus')")
    key, mods = parts[-1], parts[:-1]
    if key not in _codes:
        raise Refused(f"unknown key '{key}'")
    mset = []
    for m in mods:
        if m not in MODS:
            raise Refused(f"unknown modifier '{m}' (use ctrl, shift, alt)")
        n = "ctrl" if m == "control" else m
        if n not in mset:
            mset.append(n)
    isf = key[0] == "f" and key[1:].isdigit()
    if "ctrl" in mset and "alt" in mset:
        raise Refused("ctrl+alt combos are system shortcuts and are blocked")
    if "alt" in mset and (isf or key == "space"):
        raise Refused("alt+function keys and alt+space are blocked")
    if "ctrl" in mset and isf and key not in ("f3", "f5", "f6"):
        raise Refused("that ctrl+function combo is blocked")
    if "ctrl" in mset and key == "q":
        raise Refused("quitting the whole app is blocked")
    if "ctrl" in mset and "shift" in mset and key == "w":
        raise Refused("closing the whole window is blocked; use close-tab")
    return mset, key


def combo_args(mset, key):
    seq = [MODS[m] for m in mset] + [_codes[key]]
    return [f"{c}:1" for c in seq] + [f"{c}:0" for c in reversed(seq)]


def yd(*args):
    if dry():
        print("DRY ydotool " + " ".join(args))
        return
    subprocess.run(["ydotool", *args], env=ENV, check=True, capture_output=True, timeout=20)


def send_combo(s):
    mset, key = parse_combo(s)
    yd("key", *combo_args(mset, key))


def validate_text(text, maxlen=MAX_TYPE):
    if not text or len(text) > maxlen:
        raise Refused(f"text must be 1-{maxlen} characters")
    if any((ord(c) < 32 and c != "\t") or ord(c) == 127 for c in text) or "\n" in text:
        raise Refused("text must be a single line of printable characters (use key enter)")
    if looks_like_password(text):
        raise Refused("text looks like a password or secret; I never type those")
    return text


def send_text(text):
    yd("type", "--key-delay", "12", "--", text)


# ---------------------------------------------------------------- mouse
# ydotool 1.0.4 "--absolute" does nothing useful on this KWin (the pointer always lands at the top-left corner, measured), and
# relative moves go through pointer acceleration, so moving is closed-loop: read the real cursor position from KWin, send a
# relative nudge scaled by the factor observed on the previous step, repeat until within TOL pixels.
CURSOR_JS = 'var c=workspace.cursorPos;callDBus("@NAME@","@PATH@","@NAME@","Report",JSON.stringify([c.x,c.y]));'
TOL = 2


def cursor():
    r = kwin_eval(CURSOR_JS)
    return (r[0], r[1]) if r else None


def move_abs(x, y, scr):
    w, h = scr
    if not (0 <= x < w and 0 <= y < h):
        raise Refused(f"coordinates must be inside 0-{w - 1} x 0-{h - 1}")
    if dry():
        print(f"DRY move pointer to {x},{y}")
        return (x, y)
    k = 1.8                                     # observed acceleration gain; refined every step
    cur = cursor()
    for _ in range(10):
        if cur is None:
            raise Refused("cannot read the pointer position")
        dx, dy = x - cur[0], y - cur[1]
        if abs(dx) <= TOL and abs(dy) <= TOL:
            return cur
        sx, sy = round(dx / k), round(dy / k)
        if sx == 0 and dx: sx = 1 if dx > 0 else -1
        if sy == 0 and dy: sy = 1 if dy > 0 else -1
        yd("mousemove", "-x", str(sx), "-y", str(sy))
        time.sleep(0.04)
        new = cursor()
        if new is None:
            raise Refused("cannot read the pointer position")
        moved, asked = abs(new[0] - cur[0]) + abs(new[1] - cur[1]), abs(sx) + abs(sy)
        if moved and asked:
            k = min(4.0, max(0.4, moved / asked))
        cur = new
    if abs(x - cur[0]) > 4 or abs(y - cur[1]) > 4:
        raise Refused(f"could not place the pointer accurately (at {cur[0]},{cur[1]})")
    return cur


BUTTONS = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}


def click(x, y, scr, kind="left"):
    pos = move_abs(x, y, scr)
    if dry():
        print(f"DRY click {kind}")
        return pos
    time.sleep(0.05)
    yd("click", BUTTONS["left" if kind == "double" else kind])
    if kind == "double":
        time.sleep(0.08)
        yd("click", BUTTONS["left"])
    return pos


def scroll(direction, n):
    yd("mousemove", "-w", "-x", "0", "-y", str(n if direction == "up" else -n))
