import calendar, json, os, sqlite3, subprocess, time

home = os.path.expanduser("~")
projects = {}

def entry(p):
    return projects.setdefault(p, {"ts": 0, "session": "", "prompt": ""})

try:
    for line in open(os.path.join(home, ".claude", "history.jsonl")):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p, ts = d.get("project"), d.get("timestamp", 0) / 1000
        if not p:
            continue
        e = entry(p)
        if ts >= e["ts"]:
            e["ts"], e["session"] = ts, d.get("sessionId", "")
        text = d.get("display", "")
        if ts >= e.get("pts", 0) and text and not text.startswith("/"):
            e["pts"], e["prompt"] = ts, " ".join(text.split())[:90]
except OSError:
    pass

try:
    db = os.path.join(home, ".local/share/zed/db/0-stable/db.sqlite")
    c = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
    for paths, stamp in c.execute("select paths, timestamp from workspaces"):
        ts = calendar.timegm(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))
        for p in (paths or "").split("\n"):
            if p:
                e = entry(p)
                e["ts"] = max(e["ts"], ts)
                e["zed"] = True
except Exception:
    pass

def git(p):
    try:
        out = subprocess.run(["git", "-C", p, "status", "--porcelain", "-b"],
                             capture_output=True, text=True, timeout=2).stdout.splitlines()
        if not out:
            return "", False
        return out[0][3:].split("...")[0], len(out) > 1
    except Exception:
        return "", False

try:
    pins = json.load(open(os.path.join(home, ".config", "resume-pins.json")))
except (OSError, ValueError):
    pins = []
for p in pins:
    entry(p)

rows = []
order = sorted(projects.items(), key=lambda kv: (kv[0] not in pins, -kv[1]["ts"]))
for p, e in order:
    if not os.path.isdir(p):
        continue
    branch, dirty = git(p)
    rows.append({"path": p, "name": "Home" if p == home else os.path.basename(p),
                 "ts": e["ts"], "session": e["session"], "prompt": e["prompt"],
                 "branch": branch, "dirty": dirty, "pinned": p in pins})
    if len(rows) == 8 + len(pins):
        break
print(json.dumps(rows))
