"""Start both development servers and stop them together on Ctrl-C."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if not (ROOT / "web/node_modules").exists():
    subprocess.run(["npm", "--prefix", "web", "install"], check=True)
processes = []
try:
    processes.append(
        subprocess.Popen(
            [sys.executable, "-m", "virtual_world.cli", "serve"], start_new_session=True
        )
    )
    processes.append(
        subprocess.Popen(
            ["npm", "--prefix", "web", "run", "dev"], start_new_session=True
        )
    )
    print(
        "\nWorld Simulation LLMs → http://127.0.0.1:5173\nAPI → http://127.0.0.1:8765/docs\nPress Ctrl-C to stop both.\n",
        flush=True,
    )
    while all(p.poll() is None for p in processes):
        time.sleep(0.3)
except KeyboardInterrupt:
    pass
finally:
    for p in processes:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
    for p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
