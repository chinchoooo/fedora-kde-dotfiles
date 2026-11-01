"""One speaker at a time, machine-wide. Every program that plays speech (kspeak.py, the voice agent daemon) takes this lock
for the whole utterance, so two voices can never overlap. Waiters give up after `wait` seconds instead of piling up stale speech."""
import fcntl, os, time

LOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "speak.lock")

class SpeakLock:
    def __init__(self):
        self.fd = None

    def acquire(self, wait=8.0):
        fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
        end = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.fd = fd
                return True
            except OSError:
                if time.monotonic() >= end:
                    os.close(fd)
                    return False
                time.sleep(0.1)

    def release(self):
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None
