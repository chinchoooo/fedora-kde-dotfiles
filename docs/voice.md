# Voice notes
- Claude Code's built-in /voice sends audio to Anthropic servers; this setup replaces it with local Whisper (`holdtalk.py`). Turn the built-in off with `/voice off` or `voice.enabled=false`.
- holdtalk reads raw key events for ONE key (Right Ctrl, `KEY = 97` in `holdtalk.py`) via /dev/input, which needs the udev rule in `system/61-voice-input-uaccess.rules` (grants the logged-in user read access to keyboard event devices). Nothing is logged. Remove the rule to revoke.
- Taps shorter than 0.3 s and chords (another key pressed while holding) are ignored; transcriptions are serialised.
- Typing uses `ydotool` through a user `ydotoold` service; it needs /dev/uinput access (rule 60).
- Hold-to-talk cannot be done with KDE global shortcuts: they only fire on key press.
- Text-to-speech: Piper `en_US-lessac-medium`. `speak-away` stays silent while the Konsole has focus (flag file `~/.cache/focus-console` set by the KWin script).

## Reproduce the voice stack on a new machine
1. User-level environments (no root): `uv venv ~/code/voice-agent/venv && uv pip install --python ~/code/voice-agent/venv/bin/python faster-whisper numpy`, and `uv venv ~/code/voice-agent/tts/venv && uv pip install --python ~/code/voice-agent/tts/venv/bin/python piper-tts`.
2. Models (downloaded once, then fully offline; not stored in this repo): `~/code/voice-agent/tts/venv/bin/python -m piper.download_voices en_US-lessac-medium --data-dir ~/code/voice-agent/tts/voices`, and faster-whisper `small.en` into `~/code/voice-agent/models` (first call of `WhisperModel('small.en', device='cpu', compute_type='int8', download_root=...)`).
3. Typing needs ydotool: `sudo dnf install ydotool`, the udev rules in `system/` (they give the logged-in user access to /dev/uinput and keyboard event devices via `uaccess`), then `systemctl --user enable --now ydotoold holdtalk`.
4. Enable the KWin script: `kwriteconfig6 --file kwinrc --group Plugins --key voice-shortcutsEnabled true` and reconfigure KWin.
5. Spoken alerts: a Claude Code Notification hook in `claude/settings.json` calls `speak-away`. Claude Code's own voice setting stays off (`voice.enabled=false`).
Privacy: only the text transcript goes to Claude; audio never leaves the machine. The keyboard access in step 3 is read-only watching of a single key; revoke by deleting `/etc/udev/rules.d/61-voice-input-uaccess.rules`.
