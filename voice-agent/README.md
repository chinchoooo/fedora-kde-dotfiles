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
Architecture: `holdtalk.py` (Whisper, local) -> unix socket `$XDG_RUNTIME_DIR/voice-agent.sock` (owned by `voice-agent.socket`, socket activation) -> `voice_agent.py` (systemd user service `voice-agent`, Nice=10, started by the first connection) -> long-lived child `claude -p --input-format stream-json --output-format stream-json --verbose --model haiku` in `agent/`. Assistant text blocks are spoken in order (Kokoro af_heart, loaded lazily in the daemon, unloaded after 3 min idle, max 3 sentences / ~320 chars, longer text goes to a notification). A new command interrupts speech. The popup closes when speech starts. Holding Right Shift past 0.3 s pre-starts the child.

Lifecycle: the child keeps the session context across commands. It is stopped after 25 prompts or 30 minutes idle and started on demand (fresh context, zero tokens while idle). If it crashes it restarts on the next command; if the daemon crashes systemd restarts it.
Tune with env vars in the unit: `VA_MODEL` (default `haiku`), `VA_ROTATE_PROMPTS` (25), `VA_ROTATE_IDLE` (1800 s), `VA_KOKORO_IDLE` (180 s), `VA_TURN_TIMEOUT` (180 s). Edit with `systemctl --user edit voice-agent`, then restart. Logs: `journalctl --user -u voice-agent -f` (shows model id, prompts, tool calls, spoken text).

Safety (deliberate): the agent has NO shell. It now has guarded GUI input and workspace writes (see "GUI power" below). Layers:
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

### True sleep (socket activation)
`voice-agent.socket` owns the socket; `voice-agent.service` is NOT enabled and only starts when something connects (the 0.3 s pre-warm of a Right Shift hold does that). After `VA_IDLE_EXIT` (180 s) with no command and no work the daemon stops its Claude child, unloads Kokoro, deletes the armed stamp and exits. Idle state: no `voice_agent.py`, no `claude`, no Kokoro. `holdtalk.py` itself (key watcher) stays; it does not wake the daemon on taps (it checks `$XDG_RUNTIME_DIR/voice-agent.up` first). Enable with `systemctl --user enable --now voice-agent.socket`. Started by hand (no LISTEN_FDS) it binds the socket itself.

### GUI power (Right Shift agent)
New `va-act` subcommands: `key <combo>`, `type <text>`, `click <x> <y> [left|right|double]`, `move <x> <y>`, `scroll <up|down> <n>`, `screenshot --grid`, `active-window`, `focus <text>`, `browser <close-tab|new-tab|next-tab|prev-tab|goto-tab n|search-tab text|reopen-closed|reload|back|forward|find text|fullscreen|close-tabs-matching text>`, `open-file <path>`, `make-folder <name>`. The agent may also Write/Edit files, only under `~/va-workspace/` (never scripts or launchers; hook `agent/va-guard` resolves symlinks). Code: `va_gui.py`; tests: `python3 test_va_gui.py` (guards only, sends no input).
Input goes through ydotool (`$XDG_RUNTIME_DIR/.ydotool_socket`, `ydotoold.service`). ydotool 1.0.4 `--absolute` does not work on this KWin (pointer lands top-left), so moves are closed loop: read the cursor from KWin, nudge relatively, repeat until within 2 px (accuracy measured against a test window: within 1-2 px). Screen is 1920x1080, scale 1; grid labels are those logical pixels. Chromium has no shortcut to mute a site: `browser mute-site` refuses and tells the agent to use media pause / volume mute. `browser *` needs the active window to be Helium/Chromium/Chrome/Brave.

Hard guards (code, not prompt):
1. ARMED: all GUI subcommands, focus, open-file, make-folder and Write/Edit need `~/.cache/voice-agent/armed`, a stamp written ONLY by `holdtalk.py` when a real Right Shift hold completes. Missing, older than 180 s, not owned by you or group/world-writable = refused. The agent cannot write it (not in the workspace; denied by rules; no subcommand touches it). Deleted on panic stop, idle exit and service stop.
2. Active-window blocklist, read before every action. Classes (substring): konsole, yakuake, xterm, uxterm, urxvt, rxvt, alacritty, kitty, foot, wezterm, gnome-terminal, terminator, tilix, ptyxis, xfce4-terminal, lxterminal, terminology, cool-retro-term, qterminal, guake, tmux, terminal, polkit, pkexec, authentication, kwallet, ksshaskpass, pinentry, seahorse, gcr-prompter, kscreenlocker, ksmserver, systemsettings, kcmshell, keepass, bitwarden, 1password, lastpass, enpass, proton-pass, protonpass, dashlane, kleopatra, plasma-welcome. Title words: log in/login/log on, sign in/up, password*, passcode, otp, 2fa, two-factor, verification code, bank*, payment(s), pay, pay*, checkout, wallet, billing, card(s), credit, confirm purchase, delete account, authenticat*, authorization required, unlock, secret, private key. No active window = refused.
3. Typed text: single line, max 300 chars, refused if it mentions passwords/PIN/OTP/secret/API key/token or looks like a password. Keys: table-validated; no delete, super, print; ctrl+alt combos, alt+function keys, alt+space, ctrl+q, ctrl+shift+w refused.
4. Max 30 GUI actions per user command (daemon resets `$XDG_RUNTIME_DIR/va-gui.json` per prompt), log of every action to `~/.cache/va-actions.log` (typed text over 40 chars is logged only as a length), `VA_DRY=1` prints instead of acting (`VA_FAKE_WINDOW='{"cls":..,"title":..}'` fakes the window in dry mode).
5. PANIC STOP: tap Right Shift (under 0.3 s, no other key) while the agent is busy: `holdtalk.py` asks the daemon (`\x00busy`, then `\x00stop`), which writes `$XDG_RUNTIME_DIR/va-panic` (all GUI actions refuse until the next prompt), kills va-act children and the agent session, disarms and says "Stopped." The next command starts a fresh session (context is lost). A tap while idle, or typing with Shift, does nothing.
