# Troubleshooting
- **Shortcuts from .desktop files did nothing.** Command shortcuts written to kglobalshortcutsrc `[services][x.desktop]` were never registered by kglobalacceld. Fix: register them in a KWin script (`registerShortcut`) that starts a user systemd unit through D-Bus (`org.freedesktop.systemd1.Manager.StartUnit`). Bindings can be forced with `org.kde.KGlobalAccel.setForeignShortcut`.
- **faster-whisper: `open() got an unexpected keyword argument 'metadata_errors'`.** PyAV version mismatch. Workaround: decode the wav yourself with `wave`+numpy and pass the float32 array to `model.transcribe`.
- **Alt+Space did nothing.** KRunner owned it. It was removed from KRunner (Alt+F2 still works) and the single-press shortcut was dropped in favour of hold-to-talk on Right Ctrl.
- **Repeated "Listening..." notifications / queued dictations.** Right Ctrl is also a normal modifier. Fixed with a 0.3 s hold threshold, chord cancel and a lock around transcription.
- **GitHub identity.** Commits under `~/code` use the folder-based identity; never commit with real names or attribution trailers.
