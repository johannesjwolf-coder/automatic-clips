"""Start one API and one durable worker. Linux: Codespaces / Docker / CI."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from backend import db
db.init()
lock = (db.DATA / "server.lock").open("w")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("ClipControl läuft bereits.")
children = []
stopping = False
def stop(*args):
    global stopping
    stopping = True
    for p in children:
        if p.poll() is None:
            p.terminate()
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    children.append(subprocess.Popen([sys.executable, "-m", "backend.worker"]))
    children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app",
        "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000")]))
    print("ClipControl: http://localhost:8000 — Codespaces-Port PRIVAT lassen.", flush=True)
    while not stopping:
        if any(p.poll() is not None for p in children):
            stop()
            raise SystemExit("Ein Dienst wurde beendet. ClipControl bitte neu starten.")
        time.sleep(1)
finally:
    stop()
    for p in children:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
