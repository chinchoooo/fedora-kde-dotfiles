"""Hold-to-talk dictation, fully on-device. Hold RIGHT CTRL: record; release: transcribe locally (faster-whisper) and type the text
into the focused window with ydotool. Reads raw key events from /dev/input only to watch that one key; nothing is logged or stored."""
import glob, os, selectors, struct, subprocess, tempfile, threading, time, wave
import numpy as np

KEY = 97           # KEY_RIGHTCTRL (change here)
EV = struct.Struct("llHHi")
HERE = os.path.dirname(os.path.abspath(__file__))
env = dict(os.environ, YDOTOOL_SOCKET=os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"), ".ydotool_socket"))

model = None
def load():
    global model
    from faster_whisper import WhisperModel
    model = WhisperModel("small.en", device="cpu", compute_type="int8", cpu_threads=4, download_root=os.path.join(HERE, "models"))
threading.Thread(target=load, daemon=True).start()

nid = 0
def notify(msg, t=1200):
    """Show/replace ONE popup (reuses the notification id so it never stacks)."""
    global nid
    cmd = ["notify-send", "-p", "-t", str(t), "-e"] + (["-r", str(nid)] if nid else []) + ["Dictation", msg]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    if out.isdigit():
        nid = int(out)

def close_notification():
    global nid
    if nid:
        subprocess.run(["busctl", "--user", "call", "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                        "org.freedesktop.Notifications", "CloseNotification", "u", str(nid)], capture_output=True)
        nid = 0

def keyboards():
    if os.environ.get("HOLDTALK_TEST"):      # test mode: also watch ydotool's virtual keyboard
        return [os.path.join("/dev/input", os.path.basename(d.rsplit("/device", 1)[0])) for d in glob.glob("/sys/class/input/event*/device/name") if "ydotool" in open(d).read().lower()]
    paths = set(os.path.realpath(p) for p in glob.glob("/dev/input/by-path/*-event-kbd"))
    for d in glob.glob("/sys/class/input/event*/device/name"):
        if "keyboard" in open(d).read().lower():
            paths.add("/dev/input/" + d.split("/")[4])
    return sorted(paths)

lock = threading.Lock()   # transcriptions run one at a time, in the order spoken

def transcribe_and_type(wav):
    try:
        lock.acquire()
        w = wave.open(wav)
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0
        if len(a) < 16000 * 0.4:
            return
        while model is None:
            time.sleep(0.2)
        segs, _ = model.transcribe(a, vad_filter=True, beam_size=1)
        text = " ".join(s.text.strip() for s in segs).strip()
        if text:
            subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text + " "], env=env)
    finally:
        lock.release() if lock.locked() else None
        try:
            os.unlink(wav)
        except OSError:
            pass
        close_notification()

def main():
    sel = selectors.DefaultSelector()
    for p in keyboards():
        try:
            sel.register(open(p, "rb", buffering=0), selectors.EVENT_READ)
        except OSError:
            pass
    rec = None; wav = None; t0 = 0.0; shown = False
    HOLD_MIN = 0.3   # shorter taps (Right Ctrl used for shortcuts) are ignored silently

    def stop(discard):
        nonlocal rec, wav, shown
        rec.terminate(); rec.wait(); rec = None
        if discard or time.monotonic() - t0 < HOLD_MIN:
            try:
                os.unlink(wav)
            except OSError:
                pass
            close_notification()
        else:
            notify("Transcribing...", 1500)
            threading.Thread(target=transcribe_and_type, args=(wav,), daemon=True).start()
        shown = False

    while True:
        for k, _ in sel.select(timeout=0.1):
            data = k.fileobj.read(EV.size * 16)
            for i in range(0, len(data) - EV.size + 1, EV.size):
                _, _, typ, code, val = EV.unpack_from(data, i)
                if typ != 1:
                    continue
                if code != KEY:
                    if val == 1 and rec is not None:      # Right Ctrl used as a modifier (Ctrl+C etc.): not dictation
                        stop(discard=True)
                    continue
                if val == 1 and rec is None:
                    wav = tempfile.mktemp(suffix=".wav", prefix="holdtalk-")
                    rec = subprocess.Popen(["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", wav])
                    t0 = time.monotonic(); shown = False
                elif val == 0 and rec is not None:
                    stop(discard=False)
        if rec is not None and not shown and time.monotonic() - t0 >= HOLD_MIN:
            notify("Listening...", 60000); shown = True

main()
