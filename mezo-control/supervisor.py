from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Service:
    name: str
    command: list[str]
    cwd: str
    probe_host: str
    probe_port: int


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


def wait_for_port(service: Service, process: subprocess.Popen[bytes], timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            raise RuntimeError(f"control service {service.name} exited during startup with code {code}")
        try:
            with socket.create_connection((service.probe_host, service.probe_port), timeout=1):
                print(
                    f"control service ready name={service.name} port={service.probe_port}",
                    flush=True,
                )
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.4)
    raise RuntimeError(
        f"control service {service.name} did not open port {service.probe_port}: "
        f"{type(last_error).__name__ if last_error else 'timeout'}"
    )


def start_service(service: Service, env: dict[str, str]) -> subprocess.Popen[bytes]:
    print(
        f"starting control service name={service.name} cwd={service.cwd} port={service.probe_port}",
        flush=True,
    )
    return subprocess.Popen(service.command, cwd=service.cwd, env=env)


def start_ready(service: Service, env: dict[str, str], attempts: int = 5) -> subprocess.Popen[bytes]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        process = start_service(service, env)
        try:
            wait_for_port(service, process)
            return process
        except Exception as exc:
            last_error = exc
            print(
                f"control service startup failed name={service.name} attempt={attempt}/{attempts} "
                f"error={type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
            time.sleep(min(attempt * 2, 8))
    raise RuntimeError(
        f"control service {service.name} failed readiness after {attempts} attempts: {last_error}"
    )


def stop_processes(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    for process in processes.values():
        if process.poll() is None:
            process.terminate()
    for process in processes.values():
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> None:
    Path("/data/valkey").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("MEZO_BIND_HOST", "::")
    env["ROUTER_URL"] = "http://127.0.0.1:8081"
    env["INDEXER_URL"] = "http://127.0.0.1:8082"
    env["VALKEY_URL"] = f"redis://default:{env['VALKEY_PASSWORD']}@127.0.0.1:6379/0"

    services = [
        Service(
            "valkey",
            ["valkey-server", str(valkey_config())],
            "/data",
            "127.0.0.1",
            6379,
        ),
        Service(
            "router",
            ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8081"],
            "/app/router",
            "127.0.0.1",
            8081,
        ),
        Service(
            "indexer",
            ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8082"],
            "/app/indexer",
            "127.0.0.1",
            8082,
        ),
        Service(
            "api",
            ["uvicorn", "main:app", "--host", "::", "--port", "8080"],
            "/app/control",
            "127.0.0.1",
            8080,
        ),
    ]
    service_by_name = {service.name: service for service in services}
    processes: dict[str, subprocess.Popen[bytes]] = {}
    stopping = threading.Event()

    def stop(*_: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        for service in services:
            processes[service.name] = start_ready(service, env)

        print("MEZO control stack ready services=valkey,router,indexer,api", flush=True)
        while not stopping.wait(1):
            for name, process in list(processes.items()):
                code = process.poll()
                if code is None:
                    continue
                service = service_by_name[name]
                print(
                    f"control service exited name={name} code={code}; restarting",
                    file=sys.stderr,
                    flush=True,
                )
                processes[name] = start_ready(service, env)
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"control supervisor failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
