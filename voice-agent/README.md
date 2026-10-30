# voice-agent

On-device speech tools for this machine.

| Tool | Key | What it does |
|---|---|---|
| `holdtalk.py` (service) | hold Right Ctrl | hold, speak, release: local Whisper types the text into the focused window |
| `~/.local/bin/dictate` | Ctrl+Alt+Space | toggle record -> local Whisper -> clipboard |
| `holdtalk.py` + `voice_act.py` | hold Right Shift | hold, speak a command, release: local Whisper -> Claude (text only) -> allowlisted action |
| `~/.local/bin/speak "text"` | - | on-device Piper text-to-speech |

## voice-act
1. First press records (`pw-record`, 16 kHz mono), second press stops and runs `voice_act.py` at `nice -n 19`.
2. faster-whisper `small.en` (int8, CPU) transcribes locally; audio is decoded from raw samples via `wave` (PyAV is broken here).
3. The transcript text goes to `claude -p --output-format json` (Haiku, no tools, no session saved). The system prompt resolves nicknames/mishearings
   ("Kdrill's channel" -> Caedrel) and returns one JSON action.
4. The action is validated: https only, no userinfo/port tricks, host must be twitch.tv, youtube.com, kaggle.com, github.com, google.com or wikipedia.org (subdomains ok).
5. A notification offers a 5-second Cancel; `VOICE_ACT_AUTO=1` skips it. Then `xdg-open` and a spoken confirmation.

Test without a mic or side effects: `venv/bin/python voice_act.py --wav file.wav --dry-run` (or `--text "..."`). `--dry-run` never opens anything.

## Privacy
Audio never leaves the machine (record, transcribe and speak are all local). Only the transcript text is sent to Claude, as with any Claude Code prompt.
Models live in `models/` (Whisper) and `tts/voices/` (Piper); venvs are in `venv/` and `tts/venv/`.

## Known limits
Typing the result straight into a terminal (instead of the clipboard) waits on `ydotool` (queued behind another dnf job). Global shortcuts fire on press only, so these are toggles, not hold-to-talk.
