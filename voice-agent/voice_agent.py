"""voice-agent daemon: ONE persistent Haiku Claude Code session that answers every Right Shift command.

holdtalk.py sends each transcript (text only) as a line to a unix socket. This daemon writes it to a long-lived
`claude -p --input-format stream-json` child, reads the event stream and speaks assistant text with Kokoro af_heart.
The child can only run `va-act` (see agent/CLAUDE.md and README.md). Idle cost: no tokens; Kokoro is unloaded after 3 min;
the child is stopped after 30 min idle or 25 prompts and restarted on demand (a fresh context).
Run with the tts venv python (needs kokoro_onnx)."""
import asyncio, ctypes, gc, json, os, re, signal, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.join(HERE, "agent")
SOCK = os.environ.get("VA_SOCK") or os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"), "voice-agent.sock")
MODEL = os.environ.get("VA_MODEL", "haiku")
ROTATE_PROMPTS = int(os.environ.get("VA_ROTATE_PROMPTS", "25"))
ROTATE_IDLE = float(os.environ.get("VA_ROTATE_IDLE", "1800"))       # seconds without a prompt -> stop the child
KOKORO_IDLE = float(os.environ.get("VA_KOKORO_IDLE", "180"))        # seconds without speech -> unload Kokoro
TURN_TIMEOUT = float(os.environ.get("VA_TURN_TIMEOUT", "180"))
VOICE = "af_heart"                                                   # the user's only voice
SPEED = 1.05
MAX_CHARS, MAX_SENT = 320, 3
SHOTS = os.path.expanduser("~/.cache/va-shots")

ALLOWED = ["Bash(va-act:*)", f"Read(/{SHOTS}/**)", "WebSearch", "WebFetch"]       # Read path is absolute: leading //
DENIED = ["Bash(rm:*)", "Bash(sudo:*)", "Bash(pkexec:*)", "Bash(dnf:*)", "Bash(mv:*)", "Bash(dd:*)", "Bash(curl:*)",
          "Bash(wget:*)", "Bash(ydotool:*)", "Bash(systemctl:*)", "Bash(bash:*)", "Bash(sh:*)", "Bash(python:*)", "Bash(python3:*)",
          "Bash(ssh:*)", "Bash(git:*)", "Edit", "Write", "NotebookEdit", "Agent", "Task", "TodoWrite", "KillShell", "Monitor",
          "Read(~/.ssh/**)", "Read(~/.config/**)", "Read(~/.claude/**)", "Read(/etc/**)"]

def log(*a):
    print(*a, flush=True)

def child_cmd():
    return ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--model", MODEL, "--setting-sources", "project", "--settings", os.path.join(AGENT_DIR, "settings.json"),
            "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
            "--tools", "Bash,Read,WebSearch,WebFetch", "--permission-mode", "dontAsk",
            "--allowedTools", *ALLOWED, "--disallowedTools", *DENIED]

def clean(text):
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"https?://\S+", "a link", t)
    t = re.sub(r"[*_`#>]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()

def shorten(text):
    """Return (spoken, truncated?) limited to MAX_SENT sentences and MAX_CHARS."""
    sents = re.split(r"(?<=[.!?])\s+", clean(text))
    out = " ".join(sents[:MAX_SENT])
    cut = len(sents) > MAX_SENT
    if len(out) > MAX_CHARS:
        out = out[:MAX_CHARS].rsplit(" ", 1)[0] + "."
        cut = True
    return out, cut

class Speaker:
    """Serialised speech. Kokoro loads on first use and unloads after KOKORO_IDLE seconds."""
    def __init__(self):
        self.q = asyncio.Queue()
        self.k = None
        self.last = time.monotonic()
        self.proc = None
        self.on_start = None            # callback fired when speech playback begins

    def say(self, text):
        self.q.put_nowait(text)

    def stop(self):
        while not self.q.empty():
            self.q.get_nowait()
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()

    def _load(self):
        import onnxruntime as ort
        from kokoro_onnx import Kokoro
        so = ort.SessionOptions(); so.intra_op_num_threads = 2; so.inter_op_num_threads = 1
        sess = ort.InferenceSession(os.path.join(HERE, "tts/kokoro/kokoro-v1.0.int8.onnx"), sess_options=so, providers=["CPUExecutionProvider"])
        self.k = Kokoro.from_session(sess, os.path.join(HERE, "tts/kokoro/voices-v1.0.bin"))
        log("kokoro loaded")

    def _synth(self, sent):
        import numpy as np, soundfile as sf, tempfile
        if self.k is None:
            self._load()
        audio, sr = self.k.create(sent, voice=VOICE, speed=SPEED, lang="en-us")
        f = tempfile.mktemp(suffix=".wav", prefix="vaspeak-")
        sf.write(f, np.asarray(audio, dtype=np.float32), sr)
        return f

    async def _play(self, f):
        self.proc = await asyncio.create_subprocess_exec("pw-play", f)
        await self.proc.wait()
        try:
            os.unlink(f)
        except OSError:
            pass

    async def run(self):
        loop = asyncio.get_running_loop()
        while True:
            text = await self.q.get()
            sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
            nxt = loop.run_in_executor(None, self._synth, sents[0]) if sents else None
            for i in range(len(sents)):
                try:
                    f = await nxt
                except Exception as e:
                    log("tts error", e); break
                nxt = loop.run_in_executor(None, self._synth, sents[i + 1]) if i + 1 < len(sents) else None   # synth next while playing this
                if self.on_start:
                    self.on_start(); 
                await self._play(f)
            self.last = time.monotonic()

    async def reaper(self):
        while True:
            await asyncio.sleep(30)
            if self.k is not None and self.q.empty() and time.monotonic() - self.last > KOKORO_IDLE and not (self.proc and self.proc.returncode is None):
                self.k = None
                gc.collect()
                try:
                    ctypes.CDLL("libc.so.6").malloc_trim(0)
                except OSError:
                    pass
                log("kokoro unloaded")

class Agent:
    def __init__(self, speaker):
        self.sp = speaker
        self.proc = None
        self.prompts = 0
        self.last_prompt = time.monotonic()
        self.model = None
        self.turn_waiters = []          # per in-flight prompt: [writer, spoken_flag]
        self.lock = asyncio.Lock()
        self.reader = None
        self.turn_task = None

    async def start(self):
        if self.proc and self.proc.returncode is None:
            return
        self.model = None; self.prompts = 0
        self.proc = await asyncio.create_subprocess_exec(*child_cmd(), cwd=AGENT_DIR, stdin=asyncio.subprocess.PIPE,
                                                         stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=1 << 24)
        self.reader = asyncio.create_task(self.read(self.proc))
        log("agent started pid", self.proc.pid)

    async def stop(self, why):
        p, self.proc = self.proc, None
        if p and p.returncode is None:
            p.terminate()
            try:
                await asyncio.wait_for(p.wait(), 5)
            except asyncio.TimeoutError:
                p.kill()
        log("agent stopped:", why)
        self._finish_all()

    def _finish_all(self):
        for w in self.turn_waiters:
            self._notify_client(w, "done")
        self.turn_waiters.clear()

    def _notify_client(self, w, msg):
        if w[1]:
            return
        w[1] = True
        try:
            w[0].write((msg + "\n").encode())
        except Exception:
            pass

    async def read(self, p):
        while True:
            line = await p.stdout.readline()
            if not line:
                break
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            t = ev.get("type")
            if t == "system" and ev.get("subtype") == "init":
                self.model = ev.get("model")
                log("init model:", self.model, "tools:", ev.get("tools"))
            elif t == "assistant":
                for b in ev.get("message", {}).get("content", []):
                    if b.get("type") == "text" and b.get("text", "").strip():
                        spoken, cut = shorten(b["text"])
                        log("say:", spoken)
                        if spoken:
                            if self.turn_waiters:
                                w = self.turn_waiters[0]
                                self.sp.on_start = lambda w=w: self._notify_client(w, "speaking")
                            self.sp.say(spoken)
                        if cut:
                            subprocess.Popen(["notify-send", "-t", "15000", "Voice assistant", "--", clean(b["text"])[:900]],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif b.get("type") == "tool_use":
                        log("tool_use:", json.dumps(b.get("input"))[:200])
            elif t == "user":
                for b in ev.get("message", {}).get("content", []) if isinstance(ev.get("message", {}).get("content"), list) else []:
                    if b.get("type") == "tool_result" and b.get("is_error"):
                        log("tool error:", str(b.get("content"))[:200])
            elif t == "result":
                log("result:", ev.get("subtype"), "cost", ev.get("total_cost_usd"))
                if self.turn_waiters:
                    self._notify_client(self.turn_waiters.pop(0), "done")
                if ev.get("is_error") and ev.get("subtype") != "success":
                    self.sp.say("Sorry, something went wrong.")
        if p is self.proc:                       # child died unexpectedly: restart on the next prompt
            log("agent exited, rc", await p.wait())
            self.proc = None
            if self.turn_waiters:
                self.sp.say("Sorry, I hit a problem. Please try again.")
            self._finish_all()

    async def prompt(self, text, writer):
        async with self.lock:
            if self.prompts >= ROTATE_PROMPTS:
                await self.stop("rotated after %d prompts" % self.prompts)
            await self.start()
            w = [writer, False]
            self.turn_waiters.append(w)
            self.prompts += 1; self.last_prompt = time.monotonic()
            msg = {"type": "user", "message": {"role": "user", "content": text}}
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())
            await self.proc.stdin.drain()
        return w

    async def reaper(self):
        while True:
            await asyncio.sleep(60)
            if self.proc and not self.turn_waiters and time.monotonic() - self.last_prompt > ROTATE_IDLE:
                await self.stop("idle %ds" % ROTATE_IDLE)

async def main():
    sp = Speaker(); ag = Agent(sp)
    asyncio.create_task(sp.run()); asyncio.create_task(sp.reaper()); asyncio.create_task(ag.reaper())

    async def client(r, w):
        try:
            while True:
                line = await r.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if text == "\x00warm":
                    await ag.start()
                    continue
                if text == "\x00status":
                    w.write((json.dumps({"model": ag.model, "prompts": ag.prompts, "pid": ag.proc.pid if ag.proc else None,
                                         "kokoro": sp.k is not None}) + "\n").encode())
                    await w.drain(); continue
                if not text:
                    continue
                sp.stop()                                  # a new command interrupts speech in progress
                log("prompt:", text)
                ws = await ag.prompt(text[:2000], w)
                try:                                       # keep the connection until the client got speaking/done
                    await asyncio.wait_for(_until(ws), TURN_TIMEOUT)
                except asyncio.TimeoutError:
                    log("turn timeout"); await ag.stop("turn timeout"); sp.say("Sorry, that took too long.")
        except ConnectionError:
            pass
        finally:
            w.close()

    async def _until(ws):
        while not ws[1]:
            await asyncio.sleep(0.2)

    if os.path.exists(SOCK):
        os.unlink(SOCK)
    srv = await asyncio.start_unix_server(client, SOCK)
    os.chmod(SOCK, 0o600)
    log("listening", SOCK)
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, lambda: sys.exit(0))
    async with srv:
        await srv.serve_forever()

try:
    asyncio.run(main())
finally:
    try:
        os.unlink(SOCK)
    except OSError:
        pass
