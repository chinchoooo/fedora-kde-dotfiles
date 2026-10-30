import json, os, sys

path = os.path.expanduser("~/.config/resume-pins.json")
try:
    pins = json.load(open(path))
except (OSError, ValueError):
    pins = []
p = sys.argv[1]
if p in pins:
    pins.remove(p)
else:
    pins.insert(0, p)
json.dump(pins, open(path, "w"))
