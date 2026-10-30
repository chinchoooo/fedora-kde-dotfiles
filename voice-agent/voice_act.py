"""voice-act: spoken command -> local Whisper -> text-only call to Claude -> allowlisted action.

Audio never leaves this machine. Only the transcript text is sent to `claude -p`.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import wave
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = """You turn a short spoken command (already transcribed; it may contain mishearings and phonetic spellings of names) into ONE action for a desktop assistant on a Linux KDE machine. The user wants broad control: browsing, searching, opening apps, media and volume. Be decisive and helpful; do not refuse reasonable requests.
Reply with ONLY a JSON object: {"action": "open_url"|"search"|"launch_app"|"media"|"volume"|"none", "url": "", "query": "", "app": "", "value": "", "reason": "<short>"}.
- open_url: any http(s) website. Resolve nicknames and mishearings to the real thing (e.g. "Kdrill", "Kedral", "Cadrel" = the streamer Caedrel -> https://www.twitch.tv/caedrel). Pick the most likely official URL for sites, channels, repos, profiles, videos.
- search: put the search text in "query" (the assistant searches the web), or give a site-specific search URL in "url" (e.g. https://www.youtube.com/results?search_query=...).
- launch_app: "app" is the application name (e.g. Spotify, Konsole, Zed, Dolphin, Chrome).
- media: "value" is play, pause, toggle, next, previous or stop (controls whatever player is active).
- volume: "value" is up, down, mute, unmute or a number 0-100.
- none: only if the request is destructive (deleting files, formatting, shutting down, sending messages or money, running shell commands, changing system settings) or impossible. Never output shell commands."""


def transcribe(wav_path):
    import numpy as np
    from faster_whisper import WhisperModel
    m = WhisperModel("small.en", device="cpu", compute_type="int8", cpu_threads=4,
                     download_root=os.path.join(HERE, "models"))
    w = wave.open(wav_path)
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0
    segs, _ = m.transcribe(a, vad_filter=True, beam_size=1)
    return " ".join(s.text.strip() for s in segs).strip()


def ask_claude(text):
    p = subprocess.run(
        ["claude", "-p", text, "--output-format", "json", "--system-prompt", SYSTEM, "--tools", "",
         "--no-session-persistence", "--model", "haiku"],
        capture_output=True, text=True, timeout=60, cwd=HERE)
    out = json.loads(p.stdout)
    res = out.get("result", "") if isinstance(out, dict) else str(out)
    res = re.sub(r"^```(?:json)?|```$", "", res.strip(), flags=re.M).strip()
    return json.loads(res)


def find_app(name):
    """Return the .desktop file of an installed app whose name matches (case-insensitive)."""
    import glob
    want = name.lower().strip()
    dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications"),
            "/var/lib/flatpak/exports/share/applications", os.path.expanduser("~/.local/share/flatpak/exports/share/applications")]
    best = None
    for d in dirs:
        for f in glob.glob(d + "/*.desktop"):
            try:
                txt = open(f, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if re.search(r"^NoDisplay=true", txt, re.M):
                continue
            m = re.search(r"^Name=(.+)$", txt, re.M)
            if m and want in m.group(1).lower():
                if m.group(1).lower() == want:
                    return f
                best = best or f
    return best


def validate(action):
    """Return (ok, info). Browser/app/media/volume only; web URLs must be http(s); nothing destructive is offered."""
    kind = action.get("action")
    if kind == "open_url":
        u = urlparse(action.get("url", ""))
        if u.scheme not in ("http", "https") or not u.hostname:
            return False, "only web links can be opened"
        return True, action["url"]
    if kind == "search":
        if action.get("url"):
            u = urlparse(action["url"])
            if u.scheme in ("http", "https") and u.hostname:
                return True, action["url"]
        q = (action.get("query") or "").strip()
        if q:
            from urllib.parse import quote_plus
            return True, "https://www.google.com/search?q=" + quote_plus(q)
        return False, "no search text"
    if kind == "launch_app":
        f = find_app(action.get("app", ""))
        return (True, f) if f else (False, "I could not find an app called " + action.get("app", ""))
    if kind == "media":
        v = (action.get("value") or "").lower()
        return (True, v) if v in ("play", "pause", "toggle", "next", "previous", "stop") else (False, "unknown media control")
    if kind == "volume":
        v = str(action.get("value") or "").lower()
        return (True, v) if v in ("up", "down", "mute", "unmute") or v.isdigit() else (False, "unknown volume value")
    return False, action.get("reason") or "no action"


def speak(msg):
    subprocess.Popen([os.path.expanduser("~/.local/bin/speak"), msg], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def toast(msg):
    subprocess.Popen(["notify-send", "-t", "2500", "Voice command", msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def confirm(label, dry):
    """Runs immediately by default. VOICE_ACT_CONFIRM=1 adds a 5 s cancel countdown."""
    if dry:
        print("CONFIRM (dry-run):", label)
        return True
    if os.environ.get("VOICE_ACT_CONFIRM") != "1":
        return True
    r = subprocess.run(["notify-send", "-A", "cancel=Cancel", "-t", "5000", "Doing it in 5s", label], capture_output=True, text=True)
    return r.stdout.strip() != "cancel"


def mpris_players():
    out = subprocess.run(["busctl", "--user", "list", "--no-legend"], capture_output=True, text=True).stdout
    return [l.split()[0] for l in out.splitlines() if l.startswith("org.mpris.MediaPlayer2.")]


def do_media(v):
    method = {"play": "Play", "pause": "Pause", "toggle": "PlayPause", "next": "Next", "previous": "Previous", "stop": "Stop"}[v]
    players = mpris_players()
    if not players:
        return False
    subprocess.run(["busctl", "--user", "call", players[0], "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", method])
    return True


def do_volume(v):
    s = "@DEFAULT_AUDIO_SINK@"
    if v == "up":
        subprocess.run(["wpctl", "set-volume", "-l", "1.0", s, "5%+"])
    elif v == "down":
        subprocess.run(["wpctl", "set-volume", s, "5%-"])
    elif v in ("mute", "unmute"):
        subprocess.run(["wpctl", "set-mute", s, "1" if v == "mute" else "0"])
    else:
        subprocess.run(["wpctl", "set-volume", s, f"{min(int(v), 100)}%"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--text")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    text = a.text if a.text is not None else transcribe(a.wav)
    print("TRANSCRIPT:", text)
    if not text:
        speak("I did not hear anything.")
        return 1
    try:
        action = ask_claude(text)
    except Exception as e:  # noqa: BLE001
        print("ERROR asking Claude:", e)
        speak("I could not reach Claude.")
        return 2
    print("ACTION:", json.dumps(action))
    ok, info = validate(action)
    if not ok:
        print("REJECTED:", info)
        if not a.dry_run:
            speak("Sorry, I can't do that. " + info)
        return 3
    kind = action["action"]
    label = {"open_url": "Opening " + info, "search": "Searching: " + info, "launch_app": "Launching " + os.path.basename(info),
             "media": "Media: " + info, "volume": "Volume: " + info}[kind]
    if not confirm(label, a.dry_run):
        print("CANCELLED")
        return 4
    if a.dry_run:
        print("DRY-RUN: would do ->", kind, info)
        return 0
    toast(label)
    if kind in ("open_url", "search"):
        subprocess.Popen(["xdg-open", info], start_new_session=True)
        speak("Opening " + (urlparse(info).hostname or "it").replace("www.", ""))
    elif kind == "launch_app":
        subprocess.Popen(["gio", "launch", info], start_new_session=True)
        speak("Launching " + action.get("app", "it"))
    elif kind == "media":
        if not do_media(info):
            speak("No player is running.")
    else:
        do_volume(info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
