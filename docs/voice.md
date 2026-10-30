# Voice notes
- Claude Code's built-in /voice sends audio to Anthropic servers; this setup replaces it with local Whisper (`holdtalk.py`). Turn the built-in off with `/voice off` or `voice.enabled=false`.
- holdtalk reads raw key events for ONE key (Right Ctrl, `KEY = 97` in `holdtalk.py`) via /dev/input, which needs the udev rule in `system/61-voice-input-uaccess.rules` (grants the logged-in user read access to keyboard event devices). Nothing is logged. Remove the rule to revoke.
- Taps shorter than 0.3 s and chords (another key pressed while holding) are ignored; transcriptions are serialised.
- Typing uses `ydotool` through a user `ydotoold` service; it needs /dev/uinput access (rule 60).
- Hold-to-talk cannot be done with KDE global shortcuts: they only fire on key press.
- Text-to-speech: Piper `en_US-lessac-medium`. `speak-away` stays silent while the Konsole has focus (flag file `~/.cache/focus-console` set by the KWin script).
