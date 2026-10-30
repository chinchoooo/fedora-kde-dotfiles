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
ALLOWED = ("twitch.tv", "youtube.com", "kaggle.com", "github.com", "google.com", "wikipedia.org")
SYSTEM = """You turn a short spoken command (already transcribed, may contain mishearings and phonetic spellings of names) into ONE action for a desktop assistant.
Reply with ONLY a JSON object: {"action": "open_url"|"play_media"|"search"|"none", "url": "<https url or empty>", "reason": "<short>"}.
Resolve nicknames and mishearings to the real thing (e.g. "Kdrill", "Kedral", "Cadrel" = the streamer Caedrel -> https://www.twitch.tv/caedrel).
Only use https URLs on these domains: twitch.tv, youtube.com, kaggle.com, github.com, google.com, wikipedia.org.
For searches use a search URL on one of those domains (e.g. https://www.youtube.com/results?search_query=...).
If the command is unclear, unsafe or off-list, answer {"action":"none","url":"","reason":"..."}. Never add commentary."""


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


def validate(action):
    """Return (ok, url_or_reason). https only, allowlisted host, no userinfo or odd ports."""
    if action.get("action") not in ("open_url", "play_media", "search"):
        return False, action.get("reason") or "no action"
    u = urlparse(action.get("url", ""))
    host = (u.hostname or "").lower()
    if u.scheme != "https" or u.username or u.password or u.port not in (None, 443):
        return False, "URL must be plain https"
    if not any(host == d or host.endswith("." + d) for d in ALLOWED):
        return False, f"{host or 'empty host'} is not on the allowlist"
    return True, action["url"]


def speak(msg):
    subprocess.Popen([os.path.expanduser("~/.local/bin/speak"), msg], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def confirm(url, dry):
    if dry:
        print("CONFIRM (dry-run, no notification):", url)
        return True
    if os.environ.get("VOICE_ACT_AUTO") == "1":
        return True
    r = subprocess.run(["notify-send", "-A", "cancel=Cancel", "-t", "5000", "Opening in 5s", url],
                       capture_output=True, text=True)
    return r.stdout.strip() != "cancel"


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
            speak("Sorry, I won't do that. " + info)
        return 3
    if not confirm(info, a.dry_run):
        print("CANCELLED")
        return 4
    if a.dry_run:
        print("DRY-RUN: would xdg-open", info)
    else:
        subprocess.Popen(["xdg-open", info], start_new_session=True)
        speak("Opening " + (urlparse(info).hostname or "it").replace("www.", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
