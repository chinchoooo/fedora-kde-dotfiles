# fedora-kde-dotfiles

Personal desktop setup for a Fedora 44 laptop running KDE Plasma 6.6 on Wayland (Intel Iris Xe, 15 GB RAM, tuned `balanced` profile),
plus the on-device voice stack built on top of it. Private repository.

## Look
- Black-and-white: `MonoDark` colour scheme, `Mono-Plus-Dark` icons (a desaturated copy of Gruvbox-Plus-Dark), `Utterly-Round-Solid` Plasma theme and
  `Utterly-Round-Dark-Solid` Aurorae window decoration (third-party, authors credited in their metadata), Bibata-Modern-Classic cursor,
  JetBrainsMono Nerd Font everywhere including Konsole (`Mono` profile).
- Grayscale anime wallpapers as a slideshow (the images are not committed; see `docs/wallpapers.txt`).
- Night light 20:00-06:00 at 3400 K.
- Top panel: custom `sysdiag` widget (net/CPU/memory text with a graph popup), clock, system tray, and the `resume` widget ("Pick Up Where I Left Off":
  recent projects from the Claude Code history and Zed, with Resume Claude / Terminal / Zed buttons and a Pin button; pins live in `~/.config/resume-pins.json`).
- Bottom floating dock: launcher, pinned apps (browser, Konsole, Dolphin, Spotify, Zed, Chrome), and the `spotifymini` media widget.

## Voice stack (everything on-device except the text sent to Claude)
- Hold **Right Ctrl** for push-to-talk: `holdtalk.service` records, faster-whisper (`small.en`, int8, CPU) transcribes, `ydotool` types the text.
- `voice-act`: speech to a Claude text command to an allow-listed URL action. Only the transcript leaves the machine, never audio.
- Spoken replies with Piper TTS (`speak`), silenced while the Konsole is focused (`speak-away` plus a focus flag set by a KWin script).
- Global shortcuts live in a KWin script (`voice-shortcuts`): Ctrl+Alt+Space toggle dictation, Meta+Alt+T split Konsole/Helium.
- `kaggle-runs/kaggle_run.sh` and the `kaggle-run` Claude Code skill wrap the Kaggle CLI (credentials are never stored here).

## Keys and automation
| Input | What it does |
|---|---|
| Hold **Right Ctrl** (about 0.3 s or longer) | push-to-talk dictation: records, transcribes on-device, types the text into the focused window |
| **Ctrl+Alt+Space** | toggle dictation, text goes to the clipboard (paste with Ctrl+Shift+V) |
| **Meta+Alt+T** | split screen: Konsole left, Helium right |
| `voice-act` (command, no key) | speech to an allow-listed URL action, with a 5 s cancel |
| Timer `dotfiles-sync.timer` | every 30 minutes and 2 minutes after login: copy allow-listed files, scan for secrets, commit, push; a hit blocks the push and sends a notification |
The resume widget's pinned projects are stored as `home/.config/resume-pins.template.json` with `@HOME@` and private path names replaced by placeholders;
`install.sh` expands them back (private names come from a local-only `~/.config/dotfiles-sync/path-aliases.txt`, `name=@TOKEN@` per line).

## Layout
```
home/            files mirrored into $HOME ( @HOME@ is replaced by your home path on install )
voice-agent/     holdtalk.py, voice_act.py (no venvs, models or audio)
kaggle-runs/     Kaggle CLI wrapper
claude/          Claude Code settings (merge by hand) and skills
system/          udev rules that need root
packages/        dnf user-installed list, flatpaks, uv tools
templates/       bashrc snippets, per-folder git identity template (placeholders only)
scripts/         make-mono-icons.py
docs/            kde.md voice.md system.md troubleshooting.md wallpapers.txt
```

## Clone and install
```bash
git clone https://github.com/<you>/fedora-kde-dotfiles ~/code/dotfiles
cd ~/code/dotfiles && ./install.sh      # backs up overwritten files, prints the remaining manual and sudo steps
```
Make the repo public (only after re-reading the files): `gh repo edit <you>/fedora-kde-dotfiles --visibility public --accept-visibility-change-consequences`.

## What is not here
KDE Connect, KWallet, browser/Spotify/Zed data, shell history, credentials, tokens, model weights, wallpaper images, the 217 MB icon theme.
