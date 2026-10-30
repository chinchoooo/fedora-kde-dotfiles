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
3. The transcript text goes to `claude -p` (Haiku, no tools). It returns one action: open_url, search, launch_app, media, volume or none. Any http(s) site is allowed; nothing destructive is offered, and shell commands are never produced.
   ("Kdrill's channel" -> Caedrel) and returns one JSON action.
4. Validation only checks the action type, http(s) URLs and that an app exists. There is no domain allowlist.
5. It runs immediately and shows a short toast; set VOICE_ACT_CONFIRM=1 to get a 5 s cancel countdown first.

Test without a mic or side effects: `venv/bin/python voice_act.py --wav file.wav --dry-run` (or `--text "..."`). `--dry-run` never opens anything.

## Privacy
Audio never leaves the machine (record, transcribe and speak are all local). Only the transcript text is sent to Claude, as with any Claude Code prompt.
Models live in `models/` (Whisper) and `tts/voices/` (Piper); venvs are in `venv/` and `tts/venv/`.

## Known limits
Typing the result straight into a terminal (instead of the clipboard) waits on `ydotool` (queued behind another dnf job). Global shortcuts fire on press only, so these are toggles, not hold-to-talk.
