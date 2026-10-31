"""On-device speech with Kokoro-82M (int8 ONNX). Usage: kspeak.py "text"   (or pipe text on stdin).
Light on the machine: 2 CPU threads, sentence-by-sentence streaming into pw-play, runs and exits (no resident process)."""
import os, re, subprocess, sys
import numpy as np
import onnxruntime as ort
from kokoro_onnx import Kokoro

HERE = os.path.dirname(os.path.abspath(__file__))
VOICE = os.environ.get("SPEAK_VOICE", "af_heart")      # natural American English; try bf_emma for British
SPEED = float(os.environ.get("SPEAK_SPEED", "1.05"))

def main():
    text = " ".join(sys.argv[1:]).strip() or sys.stdin.read().strip()
    if not text:
        return
    so = ort.SessionOptions(); so.intra_op_num_threads = 2; so.inter_op_num_threads = 1
    sess = ort.InferenceSession(os.path.join(HERE, "kokoro/kokoro-v1.0.int8.onnx"), sess_options=so, providers=["CPUExecutionProvider"])
    k = Kokoro.from_session(sess, os.path.join(HERE, "kokoro/voices-v1.0.bin"))
    import queue, tempfile, threading
    import soundfile as sf
    q = queue.Queue()

    def synth():
        for sent in re.split(r"(?<=[.!?])\s+|\n+", text):
            if sent.strip():
                audio, sr = k.create(sent.strip(), voice=VOICE, speed=SPEED, lang="en-us")
                f = tempfile.mktemp(suffix=".wav", prefix="kspeak-")
                sf.write(f, np.asarray(audio, dtype=np.float32), sr)
                q.put(f)
        q.put(None)

    threading.Thread(target=synth, daemon=True).start()
    while True:                      # play each sentence as soon as it is ready while the next one is being made
        f = q.get()
        if f is None:
            break
        subprocess.run(["pw-play", f])
        os.unlink(f)


main()
