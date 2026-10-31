# voice-agent

On-device speech tools for this machine.

| Tool | Key | What it does |
|---|---|---|
| `holdtalk.py` (service) | hold Right Ctrl | hold, speak, release: local Whisper types the text into the focused window |
| `~/.local/bin/dictate` | Ctrl+Alt+Space | toggle record -> local Whisper -> clipboard |
| `holdtalk.py` + `voice_agent.py` | hold Right Shift | hold, speak, release: local Whisper -> transcript to a persistent Haiku agent that narrates, acts through `va-act`, and speaks the result (Kokoro af_heart). Falls back to one-shot `voice_act.py` if the daemon is down |
| `~/.local/bin/speak "text"` | - | on-device Kokoro text-to-speech (Piper fallback) |

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

## Voice agent (Right Shift)
Architecture: `holdtalk.py` (Whisper, local) -> unix socket `$XDG_RUNTIME_DIR/voice-agent.sock` -> `voice_agent.py` (systemd user service `voice-agent`, Nice=10) -> long-lived child `claude -p --input-format stream-json --output-format stream-json --verbose --model haiku` in `agent/`. Assistant text blocks are spoken in order (Kokoro af_heart, loaded lazily in the daemon, unloaded after 3 min idle, max 3 sentences / ~320 chars, longer text goes to a notification). A new command interrupts speech. The popup closes when speech starts. Holding Right Shift past 0.3 s pre-starts the child.

Lifecycle: the child keeps the session context across commands. It is stopped after 25 prompts or 30 minutes idle and started on demand (fresh context, zero tokens while idle). If it crashes it restarts on the next command; if the daemon crashes systemd restarts it.
Tune with env vars in the unit: `VA_MODEL` (default `haiku`), `VA_ROTATE_PROMPTS` (25), `VA_ROTATE_IDLE` (1800 s), `VA_KOKORO_IDLE` (180 s), `VA_TURN_TIMEOUT` (180 s). Edit with `systemctl --user edit voice-agent`, then restart. Logs: `journalctl --user -u voice-agent -f` (shows model id, prompts, tool calls, spoken text).

Safety (deliberate): the agent has NO shell and NO input injection. Layers:
1. `--tools Bash,Read,WebSearch,WebFetch`, `--permission-mode dontAsk` (anything not allowed is denied), `--allowedTools 'Bash(va-act:*)' 'Read(//home/<user>/.cache/va-shots/**)' WebSearch WebFetch`, plus explicit `--disallowedTools` (see `DENIED` in `voice_agent.py`).
2. `agent/va-guard` is a PreToolUse hook (loaded via `agent/settings.json`) that denies any Bash command that is not exactly one plain `va-act <sub> ...` (no `;`, `&&`, pipes, redirects, `$`, backticks). This closes read-only built-ins like `ls` that dontAsk would otherwise permit.
3. `va-act` validates every argument and has no destructive subcommands.
4. `--setting-sources project` + `--settings agent/settings.json`: your user settings, hooks (the "needs your attention" speaker) and plugins are not loaded. `agent/CLAUDE.md` is the system prompt (narrate first, ask when unsure, refuse destructive requests aloud, web text is data).
Residual risk: WebFetch/WebSearch can reach the internet, so injected page text could try to leak data through URLs; the prompt forbids it but it is not technically blocked.

### Add a va-act subcommand
Write `cmd_<name>(args)` in `va-act` (validate inputs, never run caller-supplied commands), register it in `build()`, add it to the list in `agent/CLAUDE.md`, restart `voice-agent`. `va-act` is symlinked at `~/.local/bin/va-act`; the allow rule `Bash(va-act:*)` covers it automatically.

### Testing without side effects
`HOLDTALK_TEST=1 HOLDTALK_KEEP=1 HOLDTALK_FAKE_WAV=q.wav venv/bin/python holdtalk.py`, then `ydotool key 54:1; sleep 1.5; ydotool key 54:0`. Note `HOLDTALK_DRY=1` bypasses the agent (it only dry-runs the fallback); `HOLDTALK_NO_AGENT=1` forces the fallback, which really acts. Send directly: write a line to the socket; `\x00status` returns model/prompt count.

### Privacy
Audio never leaves the machine (record, Whisper and Kokoro all run locally). Only transcript text, tool results (e.g. window titles, screenshot images when you ask about your screen) and web content go to Claude, using your Claude Code login and plan usage.
