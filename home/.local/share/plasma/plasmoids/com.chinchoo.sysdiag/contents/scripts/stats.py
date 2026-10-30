import glob, json, os, shutil

def read(path, default=""):
    try:
        return open(path).read().strip()
    except OSError:
        return default

cpu = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:]]
mem = {l.split(":")[0]: int(l.split()[1]) for l in read("/proc/meminfo").splitlines()}
rx = tx = 0
for l in read("/proc/net/dev").splitlines()[2:]:
    name, rest = l.split(":")
    if name.strip() != "lo":
        f = rest.split()
        rx, tx = rx + int(f[0]), tx + int(f[8])
temp = 0
for z in glob.glob("/sys/class/thermal/thermal_zone*"):
    if read(z + "/type") == "x86_pkg_temp":
        temp = int(read(z + "/temp", "0")) / 1000
d = shutil.disk_usage("/")
bat = glob.glob("/sys/class/power_supply/BAT*")
print(json.dumps({
    "cpuTotal": sum(cpu[:8]), "cpuIdle": cpu[3] + cpu[4],
    "memTotal": mem["MemTotal"], "memAvail": mem["MemAvailable"],
    "swapTotal": mem["SwapTotal"], "swapFree": mem["SwapFree"],
    "rx": rx, "tx": tx, "temp": temp,
    "diskUsed": d.used, "diskTotal": d.total,
    "bat": int(read(bat[0] + "/capacity", "-1")) if bat else -1,
    "batStatus": read(bat[0] + "/status") if bat else "",
    "load": read("/proc/loadavg").split()[0],
    "uptime": float(read("/proc/uptime", "0 0").split()[0]),
}))
