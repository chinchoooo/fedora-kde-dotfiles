#!/usr/bin/env bash
# Idempotent user-level installer. Backs up anything it would overwrite to ~/dotfiles-backup-<date>.
# Never runs root commands: it prints the sudo steps at the end.
set -euo pipefail
cd "$(dirname "$0")"
BK="$HOME/dotfiles-backup-$(date +%Y%m%d-%H%M%S)"
changed=0

put() {  # put <repo file> <dest>
  local src="$1" dst="$2" tmp
  tmp="$(mktemp)"
  sed "s|@HOME@|$HOME|g" "$src" > "$tmp"
  if [ -e "$dst" ] && cmp -s "$tmp" "$dst"; then rm -f "$tmp"; return; fi
  if [ -e "$dst" ]; then mkdir -p "$BK/$(dirname "${dst#$HOME/}")"; cp -a "$dst" "$BK/${dst#$HOME/}"; fi
  mkdir -p "$(dirname "$dst")"; install -m "$(stat -c %a "$src")" "$tmp" "$dst"; rm -f "$tmp"; changed=$((changed+1))
  echo "installed ${dst#$HOME/}"
}

while IFS= read -r -d '' f; do put "$f" "$HOME/${f#home/}"; done < <(find home -type f ! -name '*.template.json' -print0)
while IFS= read -r -d '' f; do put "$f" "$HOME/code/voice-agent/${f#voice-agent/}"; done < <(find voice-agent -type f -print0)
# resume-widget pins: expand @HOME@ and local aliases (~/.config/dotfiles-sync/path-aliases.txt: name=@TOKEN@); merge, never overwrite
python3 - "$HOME" "$HOME/.config/dotfiles-sync/path-aliases.txt" <<'PY'
import json, os, sys
home, alias = sys.argv[1:3]
amap = {}
try:
    for l in open(alias):
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1); amap[v.strip()] = k.strip()
except OSError:
    pass
src, dst = "home/.config/resume-pins.template.json", os.path.join(home, ".config", "resume-pins.json")
if os.path.exists(src):
    cur = json.load(open(dst)) if os.path.exists(dst) else []
    for p in json.load(open(src)):
        p = p.replace("@HOME@", home)
        for tok, name in amap.items():
            p = p.replace(tok, name)
        if "@" in p:
            print("skipped pin (unresolved placeholder):", p); continue
        if p not in cur and os.path.isdir(p):
            cur.append(p)
    json.dump(cur, open(dst, "w"))
PY
put kaggle-runs/kaggle_run.sh "$HOME/code/kaggle-runs/kaggle_run.sh"
while IFS= read -r -d '' f; do put "$f" "$HOME/.claude/${f#claude/}"; done < <(find claude/skills -type f -print0)
# Claude Code settings are not overwritten: merge by hand
mkdir -p "$HOME/.claude" && cp -n claude/settings.json "$HOME/.claude/settings.dotfiles.json" || true

systemctl --user daemon-reload 2>/dev/null || true
chmod +x "$HOME/.local/bin/"* 2>/dev/null || true
systemctl --user enable --now dotfiles-sync.timer 2>/dev/null || echo "enable manually: systemctl --user enable --now dotfiles-sync.timer"
mkdir -p "$HOME/.config/dotfiles-sync" && [ -e "$HOME/.config/dotfiles-sync/private-terms.txt" ] || printf "%s\n" "# local-only: names/handles that must never appear in this repo (one per line)" > "$HOME/.config/dotfiles-sync/private-terms.txt"
echo "$changed file(s) changed. Backup (if any): $BK"
cat <<'MSG'

Next steps (not automated):
  1. Python envs for the voice stack (user level):
       cd ~/code/voice-agent && uv venv venv && uv pip install --python venv/bin/python faster-whisper numpy
       uv venv tts/venv && uv pip install --python tts/venv/bin/python piper-tts
       tts/venv/bin/python -m piper.download_voices en_US-lessac-medium --data-dir tts/voices
       venv/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('small.en', device='cpu', compute_type='int8', download_root='models')"
  2. Icons: install Gruvbox-Plus-Dark into ~/.local/share/icons, then python3 scripts/make-mono-icons.py
  3. Enable services:  systemctl --user enable --now ydotoold holdtalk
  4. Enable the KWin shortcut script: kwriteconfig6 --file kwinrc --group Plugins --key voice-shortcutsEnabled true
  5. Restart the shell: systemctl --user restart plasma-plasmashell
  6. Root steps (run yourself):
       sudo dnf install --setopt=install_weak_deps=False $(grep -v '^$' packages/dnf-userinstalled.txt | tr '\n' ' ')   # optional, big
       sudo dnf install ydotool tuned && sudo tuned-adm profile balanced
       sudo cp system/*.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=input --subsystem-match=misc
  7. Flatpaks: xargs -a packages/flatpak-apps.txt flatpak install -y --user flathub
  8. Kaggle CLI: uv tool install kaggle   (then log in yourself)
  9. Merge ~/.claude/settings.dotfiles.json into ~/.claude/settings.json (hooks, permissions, voice).
 10. Git per-folder identity and gh wrapper: see templates/.
MSG
