#!/usr/bin/env bash
# Copy ONLY allow-listed paths (manifest.txt) from the live system into this repo, scan the staged diff for secrets/identity,
# and commit + push only if clean. On any hit: nothing is committed or pushed, the offending file is reverted, and a notification names it.
#   ./sync.sh            sync, scan, commit, push
#   ./sync.sh --check    scan the whole committed tree + working tree only (no copy, no commit)
# Env: DOTFILES_MANIFEST=<file> (testing), DOTFILES_NO_PUSH=1
set -uo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"; cd "$REPO"
exec 9>"$REPO/.sync.lock"; flock -n 9 || { echo "another sync is running"; exit 0; }
MANIFEST="${DOTFILES_MANIFEST:-$REPO/manifest.txt}"
DENY="$REPO/denylist.txt"; ALLOW="$REPO/scan-allow.txt"
PRIVATE_TERMS="$HOME/.config/dotfiles-sync/private-terms.txt"   # local-only list of names/handles that must never appear (not in the repo)
HOST="$(hostname)"; SHORT="${HOST%%.*}"

note() { notify-send -u critical "Dotfiles sync blocked" "$1" 2>/dev/null || true; echo "BLOCKED: $1" >&2; }
denied() { local p pat; p="$1"; while IFS= read -r pat; do case "$pat" in ''|'#'*) continue;; esac; [[ "$p" == $pat ]] && return 0; done < "$DENY"; return 1; }
expand() { local p="${1/#\~/$HOME}"; echo "$p"; }

copy_one() {  # src dst
  local src dst; src="$(expand "$1")"; dst="$2"
  denied "$src" && { echo "skip (denylist): $src" >&2; return 0; }
  denied "$dst" && { echo "skip (denylist): $dst" >&2; return 0; }
  if [[ "$src" == */ ]]; then
    [ -d "$src" ] || { echo "missing dir: $src" >&2; return 0; }
    rm -rf "$dst"; mkdir -p "$(dirname "$dst")"; cp -a "${src%/}" "${dst%/}"
    find "${dst%/}" -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null
    find "${dst%/}" -type f | while read -r f; do denied "$f" && rm -f "$f"; done
    find "${dst%/}" -type f -exec grep -Iq . {} \; -exec sed -i "s|$HOME|@HOME@|g" {} \;
  else
    [ -f "$src" ] || { echo "missing file: $src" >&2; return 0; }
    mkdir -p "$(dirname "$dst")"; cp -a "$src" "$dst"
    grep -Iq . "$dst" && sed -i "s|$HOME|@HOME@|g" "$dst"
  fi
}

gen_packages() {
  mkdir -p packages
  flatpak list --app --columns=application > packages/flatpak-apps.txt 2>/dev/null
  uv tool list > packages/uv-tools.txt 2>/dev/null
  nice -n 19 dnf repoquery --userinstalled --qf '%{name}\n' 2>/dev/null | sort -u > packages/dnf-userinstalled.txt
}

if [ "${1:-}" = "--check" ]; then python3 "$REPO/scan.py" --tree && echo "check clean"; exit $?; fi

gen_packages
n=0
while read -r src dst; do
  case "$src" in ''|'#'*) continue;; esac
  copy_one "$src" "$dst"; n=$((n+1))
done < "$MANIFEST"

# stage only manifest destinations and the generated package lists
git add -A -- packages 2>/dev/null
while read -r src dst; do case "$src" in ''|'#'*) continue;; esac; git add -A -- "$dst" 2>/dev/null; done < "$MANIFEST"

if git diff --cached --quiet; then echo "nothing to commit ($n manifest entries)"; exit 0; fi

# path check (denylist) and content scan of the staged diff
hits="$(python3 "$REPO/scan.py" --staged)"
if [ -n "$hits" ]; then
  first="$(head -3 <<<"$hits" | tr '\n' ';')"
  while IFS= read -r line; do
    f="${line%%: *}"; [ -z "$f" ] && continue
    git reset -q -- "$f"; if git cat-file -e "HEAD:$f" 2>/dev/null; then git checkout -q -- "$f"; else rm -f -- "$f"; fi
  done <<<"$hits"
  note "$first"
  exit 2
fi

git commit -q -m "sync: $(date +%F\ %H:%M) ($(git diff --cached --name-only | wc -l) files)" || exit 1
echo "committed: $(git log -1 --format=%h)"
[ "${DOTFILES_NO_PUSH:-0}" = 1 ] && exit 0
git push -q origin HEAD && echo "pushed" || { notify-send "Dotfiles sync" "push failed (committed locally)" 2>/dev/null; exit 1; }
