# KDE notes
- Config is plain KDE rc files under `home/.config`; `kdeglobals` holds colour scheme, fonts, icon theme; `plasma-org.kde.plasma.desktop-appletsrc` is the panel and widget layout
  (two panels: containment 2 bottom dock, containment 31 top bar).
- Custom plasmoids (`com.chinchoo.*`) are user-level in `~/.local/share/plasma/plasmoids`. Restart the shell after changing QML: `systemctl --user restart plasma-plasmashell`.
- Panel edits at runtime: `busctl --user call org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell evaluateScript s "<js>"` (qdbus is not installed). The dock widget is `org.kde.plasma.icontasks`; pinning = appending `applications:<id>.desktop` to its `launchers` setting.
- Windows/Meta key opens KRunner centred (kwinrc ModifierOnlyShortcuts); the plasmashell launcher shortcut was moved to Alt+F1.
- The Mono icon theme is derived, not committed: see `scripts/make-mono-icons.py`.
