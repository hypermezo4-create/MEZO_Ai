from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def valkey_config() -> Path:
    password = os.environ.get("VALKEY_PASSWORD", "")
    if not password or any(char in password for char in "\r\n"):
        raise RuntimeError("VALKEY_PASSWORD is required and must be one line")
    path = Path("/tmp/valkey.conf")
    path.write_text(
        "bind 127.0.0.1 ::1\nprotected-mode yes\nport 6379\ndir /data/valkey\n"
        "appendonly yes\nappendfsync everysec\nmaxmemory-policy noeviction\n"
        f"requirepass {password}\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def main() -> None:
    Path("/data/valkey").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("MEZO_BIND_HOST", "::")
    env["ROUTER_URL"] = "http://127.0.0.1:8081"
    env["INDEXER_URL"] = "http://127.0.0.1:8082"
    env["VALKEY_URL"] = f"redis://default:{env['VALKEY_PASSWORD']}@127.0.0.1:6379/0"
    commands = {
        "valkey": (["valkey-server", str(valkey_config())], "/data"),
        "api": (["uvicorn", "main:app", "--host", "::", "--port", "8080"], "/app/control"),
        "router": (["uvicorn", "main:app", "--host", "::", "--port", "8081"], "/app/router"),
        "indexer": (["uvicorn", "main:app", "--host", "::", "--port", "8082"], "/app/indexer"),
    }
    processes = {name: subprocess.Popen(command, cwd=cwd, env=env) for name, (command, cwd) in commands.items()}

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
                    raise RuntimeError(f"control service {name} exited with code {code}")
            time.sleep(2)
    finally:
        stop()
        for process in processes.values():
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"control supervisor failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
