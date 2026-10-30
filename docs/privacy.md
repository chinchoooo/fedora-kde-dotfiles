# Privacy filter

`sync.sh` is the only thing that moves files from the live system into this repo, and it works from an allowlist.

**How it works**
1. `manifest.txt` lists every live path that may be copied (`<live path>  <repo path>`, `~` = home, trailing `/` = directory). Nothing else is ever copied.
2. `denylist.txt` holds glob patterns that are refused even if someone lists them in the manifest: wallet and KDE Connect data, `~/.kaggle`, `~/.ssh`, `~/.config/gh`, browser profiles, shell history, Claude credentials/history/memory, keys.
3. After copying, `scan.py --staged` scans only the lines added in the staged diff for: API tokens (GitHub, Hugging Face, Slack, AWS, Google, JWT), `BEGIN ... PRIVATE KEY`, `password|secret|token|api_key = value` assignments, email addresses, MAC addresses, this machine's hostname, and any term in the local-only file `~/.config/dotfiles-sync/private-terms.txt` (names and handles; never committed), plus any staged path matching the denylist.
4. On a hit: nothing is committed or pushed, the offending file is reverted, and a desktop notification names it (exit code 2). Otherwise it commits with a plain message and pushes.
5. Your home path is rewritten to `@HOME@` on the way in and back on install.

`./sync.sh --check` scans the whole work tree without copying.

**Timer:** `dotfiles-sync.timer` runs the sync 2 minutes after login and every 30 minutes (Nice=19, idle IO). Check it: `systemctl --user list-timers dotfiles-sync.timer`, logs: `journalctl --user -u dotfiles-sync`.

**Add a path:** append `~/path/in/home  home/path/in/home` to `manifest.txt` (directories end with `/`), make sure no denylist pattern matches it, run `./sync.sh`, read the commit before trusting it.

**Make the repo public safely**
1. `./sync.sh --check` must say `check clean`.
2. Search the history, not just the tree: `git log -p | python3 scan.py`-style review, or `git log --all -p | grep -i -E 'token|secret|@'`. If anything ever slipped in, rewrite history (`git filter-repo`) before flipping; deleting the file in a new commit is not enough.
3. Read `README.md`, `docs/` and `home/.config/plasma-*` once by eye (layout, paths, wallpaper names).
4. Then: `gh repo edit <you>/fedora-kde-dotfiles --visibility public --accept-visibility-change-consequences`.
