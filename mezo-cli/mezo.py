from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


URL = "http://127.0.0.1:8787"
STATE = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local"))) / "MEZO AI"
PID_FILE = STATE / "tunnel.pid"
FLY_APP = "mezo-ai"


def control_machine_hostname() -> str:
    result = subprocess.run(
        ["fly", "machines", "list", "--app", FLY_APP, "--json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Unable to inventory mezo-ai Machines; check `fly auth whoami`")
    try:
        machines = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("flyctl returned an invalid Machine inventory") from exc
    for machine in machines:
        metadata = machine.get("config", {}).get("metadata", {})
        role = metadata.get("role") or metadata.get("fly_process_group")
        if role != "control" or machine.get("state") != "started":
            continue
        machine_id = machine.get("id")
        status = subprocess.run(
            ["fly", "machine", "status", machine_id, "--app", FLY_APP, "--json"],
            capture_output=True,
            text=True,
        )
        if status.returncode == 0 and '"critical"' not in status.stdout.lower():
            return f"{machine_id}.vm.{FLY_APP}.internal"
    raise RuntimeError("No healthy control Machine exists in mezo-ai; inspect `fly machines list --app mezo-ai`")


def reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8787), timeout=0.5):
            return True
    except OSError:
        return False


def ensure_tunnel() -> None:
    if reachable():
        return
    STATE.mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_supervise"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags, start_new_session=os.name != "nt",
    )
    for _ in range(40):
        if reachable():
            return
        time.sleep(0.25)
    raise RuntimeError("The private Fly tunnel did not become ready; run `mezo doctor`")


def supervise() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="ascii")
    try:
        while True:
            remote_host = control_machine_hostname()
            process = subprocess.Popen(
                ["fly", "proxy", "8787:8080", remote_host, "--app", FLY_APP, "--bind-addr", "127.0.0.1"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            process.wait()
            time.sleep(1.5)
    finally:
        PID_FILE.unlink(missing_ok=True)


def request(path: str, method: str = "GET", body: dict | None = None):
    ensure_tunnel()
    payload = json.dumps(body).encode() if body is not None else None
    value = urllib.request.Request(URL + path, data=payload, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(value, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode(errors="replace")) from exc


def run_task(text: str) -> None:
    projects = request("/api/projects")
    if not projects:
        raise RuntimeError(f"Add a repository first in {URL}")
    task = request("/api/tasks", "POST", {"project_id": projects[0]["id"], "prompt": text, "mode": "auto"})
    print(f"Task {task['id']} queued. Open {URL} for streaming output.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="mezo", description="Private client for the MEZO Fly cluster")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("web"); commands.add_parser("status"); commands.add_parser("models")
    commands.add_parser("doctor"); commands.add_parser("stop"); commands.add_parser("chat")
    run = commands.add_parser("run"); run.add_argument("task")
    commands.add_parser("_supervise")
    args = parser.parse_args()
    if args.command == "_supervise":
        supervise(); return
    if args.command == "stop":
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text(encoding="ascii"))
            os.kill(pid, signal.SIGTERM)
            PID_FILE.unlink(missing_ok=True)
        print("MEZO tunnel stopped."); return
    if args.command == "doctor":
        fly = subprocess.run(["fly", "auth", "whoami"], capture_output=True, text=True)
        print("flyctl authentication: " + ("ok" if fly.returncode == 0 else "unavailable"))
        ensure_tunnel(); print("private tunnel: ok")
        print("web API: " + request("/healthz")["status"]); return
    if args.command in {None, "web"}:
        ensure_tunnel(); webbrowser.open(URL); print(URL); return
    if args.command == "status":
        value = request("/api/status"); print(f"Machines: {len(value['machines'])}/20 · Router: {'online' if value['router']['healthy'] else 'offline'} · Queue: {value['valkey']}"); return
    if args.command == "models":
        value = request("/api/status");
        for name, state in value["router"].get("models", {}).items(): print(f"{name:12} {'online' if state['healthy'] else 'offline'}")
        return
    if args.command == "run": run_task(args.task); return
    if args.command == "chat":
        print("MEZO chat. Enter an empty line to exit.")
        while text := input("mezo> ").strip(): run_task(text)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as exc:
        print(f"mezo: {exc}", file=sys.stderr); raise SystemExit(1)
