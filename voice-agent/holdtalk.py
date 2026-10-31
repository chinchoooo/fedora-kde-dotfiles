"""Hold-to-talk, fully on-device. Two hold keys:
  Right Ctrl  = dictation: record while held; on release local Whisper transcribes and ydotool types the text.
  Right Shift = voice command: record while held; on release local Whisper transcribes and the transcript goes to the voice-agent daemon
                (voice_agent.py, persistent Haiku session; falls back to the one-shot voice_act.py if the daemon is down)
                (only the transcript text goes to Claude; audio never leaves the machine).
Raw key events are read from /dev/input only to watch those two keys; nothing is logged or stored.
Taps under 0.3 s and chords (another key pressed while held) are ignored, so normal Ctrl/Shift shortcuts keep working;
except that a lone Right Shift tap while the voice agent is busy is a PANIC STOP (the daemon is asked first, an idle agent is untouched)."""
import glob, os, selectors, shutil, socket, struct, subprocess, tempfile, threading, time, wave
import numpy as np

KEYS = {97: "dictate", 54: "command"}      # KEY_RIGHTCTRL, KEY_RIGHTSHIFT (change here)
HOLD_MIN = 0.3
EV = struct.Struct("llHHi")
HERE = os.path.dirname(os.path.abspath(__file__))
env = dict(os.environ, YDOTOOL_SOCKET=os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"), ".ydotool_socket"))
FAKE_WAV = os.environ.get("HOLDTALK_FAKE_WAV")      # test hook: use this audio instead of the microphone recording
DRY = os.environ.get("HOLDTALK_DRY")                # test hook: voice commands never open anything
MIC = os.environ.get("HOLDTALK_MIC", "alsa_input.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__Mic1__source")   # built-in digital mic; a USB dongle must not hijack the default input
KEEP = os.environ.get("HOLDTALK_KEEP")              # test hook: keep recordings and report their length

AGENT_SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"), "voice-agent.sock")
NO_AGENT = os.environ.get("HOLDTALK_NO_AGENT")      # test hook: skip the daemon, use the one-shot voice_act.py

def agent_send(line, wait=60.0):
    """Send one line to the voice-agent daemon and wait until it starts speaking (or finishes), so the popup closes then.
    Returns False if the daemon is not reachable (caller falls back to voice_act.py)."""
    try:
        s = socket.socket(socket.AF_UNIX); s.settimeout(3)
        s.connect(AGENT_SOCK)
        s.sendall((line.replace("\n", " ") + "\n").encode())
    except OSError:
        return False
    if wait:
        s.settimeout(wait)
        try:
            s.recv(64)                      # 'speaking' or 'done'
        except OSError:
            pass
    s.close()
    return True

def agent_query(cmd):
    """Send a control line to the daemon and return its one-line reply ('' if unreachable)."""
    try:
        s = socket.socket(socket.AF_UNIX); s.settimeout(5)
        s.connect(AGENT_SOCK)
        s.sendall((cmd + "\n").encode())
        r = s.recv(64).decode().strip()
        s.close()
        return r
    except OSError:
        return ""

ARMED = os.path.expanduser("~/.cache/voice-agent/armed")
UP_FLAG = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"), "voice-agent.up")

def arm():
    """Write the 'armed' stamp. ONLY here, ONLY after a real Right Shift hold (from key events). va-act and va-guard refuse
    GUI input and workspace writes when this stamp is missing or older than 180 s."""
    try:
        os.makedirs(os.path.dirname(ARMED), mode=0o700, exist_ok=True)
        tmp = ARMED + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, str(time.time()).encode()); os.close(fd)
        os.replace(tmp, ARMED)
    except OSError:
        pass

def panic_check():
    """A quick tap of Right Shift: if (and only if) the agent is busy, PANIC STOP it. Normal Shift typing never reaches here
    (it is a chord with another key, which is discarded) and an idle agent is left alone."""
    if not os.path.exists(UP_FLAG):             # daemon asleep: nothing to stop, and do not wake it
        return
    if agent_query("\x00busy") == "1":
        agent_query("\x00stop")
        close_notification()

model = None
model_lock = threading.Lock()
last_use = time.monotonic()
IDLE_UNLOAD = int(os.environ.get("HOLDTALK_IDLE_UNLOAD", "1200"))   # seconds idle before the Whisper model is freed (about 550 MB); 20 min so normal use never waits

def ensure_model():
    """Load Whisper on demand (a key press pre-warms it while you speak)."""
    global model, last_use
    with model_lock:
        last_use = time.monotonic()
        if model is None:
            from faster_whisper import WhisperModel
            model = WhisperModel("small.en", device="cpu", compute_type="int8", cpu_threads=4, download_root=os.path.join(HERE, "models"))
        return model

def unloader():
    """Free the model after a quiet spell so the idle service stays small."""
    global model
    import ctypes, gc
    while True:
        time.sleep(30)
        with model_lock:
            if model is not None and time.monotonic() - last_use > IDLE_UNLOAD and rec_active is False:
                model = None
                gc.collect()
                try:
                    ctypes.CDLL("libc.so.6").malloc_trim(0)
                except OSError:
                    pass

rec_active = False

nid = 0
def notify(msg, t=1200):
    """Show/replace ONE popup (reuses the notification id so it never stacks)."""
    global nid
    cmd = ["notify-send", "-p", "-t", str(t), "-e"] + (["-r", str(nid)] if nid else []) + ["Dictation", msg]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    if out.isdigit():
        nid = int(out)

def close_notification():
    global nid
    if nid:
        subprocess.run(["busctl", "--user", "call", "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                        "org.freedesktop.Notifications", "CloseNotification", "u", str(nid)], capture_output=True)
        nid = 0

def keyboards():
    if os.environ.get("HOLDTALK_TEST"):      # test mode: watch ydotool's virtual keyboard instead of real ones
        return [os.path.join("/dev/input", d.split("/")[4]) for d in glob.glob("/sys/class/input/event*/device/name")
                if "ydotool" in open(d).read().lower()]
    paths = set(os.path.realpath(p) for p in glob.glob("/dev/input/by-path/*-event-kbd"))
    for d in glob.glob("/sys/class/input/event*/device/name"):
        if "keyboard" in open(d).read().lower():
            paths.add("/dev/input/" + d.split("/")[4])
    return sorted(paths)

def mic_args():
    """Record from the built-in mic when it exists, else from the system default (a plugged-in USB DAC can silently become the default input)."""
    out = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True).stdout
    return ["--target", MIC] if MIC and MIC in out else []

def wav_seconds(path):
    w = wave.open(path)
    return w.getnframes() / float(w.getframerate())

def transcribe(wav):
    """Return the transcript of a 16 kHz mono s16 wav (empty string for silence/too short)."""
    w = wave.open(wav)
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0
    if len(a) < 16000 * HOLD_MIN:
        return ""
    global last_use
    m = ensure_model()
    segs, _ = m.transcribe(a, vad_filter=True, beam_size=1)
    text = " ".join(s.text.strip() for s in segs).strip()
    last_use = time.monotonic()
    return text

lock = threading.Lock()   # one transcription at a time, in the order spoken

def handle(wav, mode):
    with lock:
        try:
            if KEEP:
                import array, math
                _a = array.array("h", wave.open(wav).readframes(wave.open(wav).getnframes()))
                print(f"[{mode}] recorded {wav_seconds(wav):.1f}s rms={math.sqrt(sum(x*x for x in _a)/max(1,len(_a))):.0f}", flush=True)
            if FAKE_WAV:
                shutil.copy(FAKE_WAV, wav)
            text = transcribe(wav)
            if KEEP:
                print(f"[{mode}] transcript: {text!r}", flush=True)
            if not text:
                return
            if mode == "dictate":
                if not KEEP:
                    subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text + " "], env=env)
            elif not NO_AGENT and not DRY and agent_send(text):
                if KEEP:
                    print(f"[{mode}] sent to voice-agent daemon", flush=True)
            else:                                        # daemon down: one-shot fallback
                cmd = ["nice", "-n", "10", os.path.join(HERE, "venv/bin/python"), os.path.join(HERE, "voice_act.py"), "--text", text]
                if DRY:
                    cmd.append("--dry-run")
                r = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
                if KEEP:
                    print(f"[{mode}] action: {(r.stdout or r.stderr).strip()[:300]}", flush=True)
        finally:
            if not KEEP:
                try:
                    os.unlink(wav)
                except OSError:
                    pass
            close_notification()

def main():
    threading.Thread(target=unloader, daemon=True).start()
    sel = selectors.DefaultSelector()
    for p in keyboards():
        try:
            sel.register(open(p, "rb", buffering=0), selectors.EVENT_READ)
        except OSError:
            pass
    rec = None; wav = None; mode = None; t0 = 0.0; shown = False

    def stop(discard):
        nonlocal rec, wav, mode, shown
        rec.terminate(); rec.wait(); rec = None
        if not discard and mode == "command" and not NO_AGENT and time.monotonic() - t0 < HOLD_MIN:
            threading.Thread(target=panic_check, daemon=True).start()        # tap while the agent works = panic stop
        if discard or time.monotonic() - t0 < HOLD_MIN:
            try:
                os.unlink(wav)
            except OSError:
                pass
            close_notification()
        else:
            if mode == "command":
                arm()                                   # a real, completed Right Shift hold
            notify("Transcribing..." if mode == "dictate" else "Understanding command...", 3000)
            threading.Thread(target=handle, args=(wav, mode), daemon=True).start()
        shown = False; mode = None

    while True:
        for k, _ in sel.select(timeout=0.1):
            data = k.fileobj.read(EV.size * 16)
            for i in range(0, len(data) - EV.size + 1, EV.size):
                _, _, typ, code, val = EV.unpack_from(data, i)
                if typ != 1:
                    continue
                if code in KEYS:
                    if val == 1 and rec is None:
                        wav = tempfile.mktemp(suffix=".wav", prefix="holdtalk-")
                        rec = subprocess.Popen(["pw-record"] + mic_args() + ["--rate", "16000", "--channels", "1", "--format", "s16", wav])
                        mode = KEYS[code]; t0 = time.monotonic(); shown = False
                        threading.Thread(target=ensure_model, daemon=True).start()   # pre-warm while you speak
                    elif val == 0 and rec is not None and KEYS[code] == mode:
                        stop(discard=False)
                    elif val == 1 and rec is not None and KEYS[code] != mode:
                        stop(discard=True)                 # the other hold key pressed: treat as a chord
                elif val == 1 and rec is not None:         # any other key while held: a shortcut, not dictation
                    stop(discard=True)
        if rec is not None and not shown and time.monotonic() - t0 >= HOLD_MIN:
            notify("Listening..." if mode == "dictate" else "Listening for a command...", 60000); shown = True
            if mode == "command" and not NO_AGENT:
                threading.Thread(target=agent_send, args=("\x00warm", 0), daemon=True).start()   # start the agent while the user speaks

if __name__ == "__main__":
    main()
