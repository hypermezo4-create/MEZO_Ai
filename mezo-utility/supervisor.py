from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


SERVICES = {
    "fast": ("fast", "8101"),
    "embedding": ("embedding", "8102"),
    "reranker": ("reranker", "8103"),
}


def main() -> None:
    processes: dict[str, subprocess.Popen[bytes]] = {}
    for name, (manifest, port) in SERVICES.items():
        env = os.environ.copy()
        env.update({
            "MEZO_BIND_HOST": "::",
            "MODEL_MANIFEST": manifest,
            "MODEL_PORT": port,
            "MODEL_ROOT": f"/models/{name}",
        })
        processes[name] = subprocess.Popen(["python", "/opt/mezo/bootstrap.py"], env=env)

    def stop(*_: object) -> None:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while True:
            for name, process in processes.items():
                code = process.poll()
                if code is not None:
                    raise RuntimeError(f"utility service {name} exited with code {code}")
            time.sleep(2)
    finally:
        stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"utility supervisor failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
