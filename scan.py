#!/usr/bin/env python3
"""Secret / identity scanner for the dotfiles repo (stdlib only).
  scan.py --staged   scan lines ADDED in the staged diff
  scan.py --tree     scan every non-ignored text file in the work tree
Prints '<file>: <reason>' per hit and exits 2 if anything matched."""
import fnmatch, os, re, socket, subprocess, sys

REPO = os.path.dirname(os.path.abspath(__file__))
PATTERNS = [
    ("API token pattern", re.compile(r"(gh[pos]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|hf_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,})")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password/secret/token assignment", re.compile(r"(password|passwd|secret|token|api[_-]?key|access[_-]?key)\s*[:=]\s*[\"']?[^\s\"'$<(`]{6,}", re.I)),
    ("MAC address", re.compile(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")),
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]

def read_list(p):
    try:
        return [l.strip() for l in open(p) if l.strip() and not l.startswith("#")]
    except OSError:
        return []

allow = [re.compile(x) for x in read_list(os.path.join(REPO, "scan-allow.txt"))]
host = socket.gethostname()
terms = [host, host.split(".")[0]] + read_list(os.path.expanduser("~/.config/dotfiles-sync/private-terms.txt"))
terms = [t.lower() for t in terms if t]
deny = read_list(os.path.join(REPO, "denylist.txt"))

def why(line):
    for name, rx in PATTERNS:
        m = rx.search(line)
        if m and not (name == "email address" and any(a.search(line) for a in allow)):
            return name
    low = line.lower()
    for t in terms:
        if t in low:
            return "machine hostname or private identity term"
    return None

def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, errors="replace").stdout

def staged():
    cur = None
    for l in git("diff", "--cached", "-U0", "--no-color", "--diff-filter=AM").splitlines():
        if l.startswith("+++ b/"):
            cur = l[6:]
        elif l.startswith("+") and not l.startswith("+++") and cur:
            yield cur, l[1:]

def tree():
    for f in git("ls-files", "-co", "--exclude-standard").splitlines():
        p = os.path.join(REPO, f)
        try:
            data = open(p, "rb").read()
        except OSError:
            continue
        if b"\0" in data[:8000]:
            continue
        for l in data.decode("utf-8", "replace").splitlines():
            yield f, l

hits = {}
src = staged() if "--staged" in sys.argv else tree()
for f, l in src:
    r = why(l)
    if r:
        hits.setdefault(f, r)
names = git("diff", "--cached", "--name-only") if "--staged" in sys.argv else git("ls-files", "-co", "--exclude-standard")
for f in names.splitlines():
    if any(fnmatch.fnmatchcase("/" + f, p) for p in deny):
        hits.setdefault(f, "path on denylist")
for f, r in sorted(hits.items()):
    print(f"{f}: {r}")
sys.exit(2 if hits else 0)
