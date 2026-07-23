from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def download(root: Path, repo: str, revision: str, item: dict[str, str]) -> Path:
    target = root / Path(item["path"]).name
    if target.exists() and digest(target) == item["sha256"]:
        return target
    partial = target.with_suffix(target.suffix + ".partial")
    quoted = "/".join(urllib.parse.quote(part) for part in item["path"].split("/"))
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{quoted}?download=true"
    subprocess.run(
        ["curl", "--fail", "--location", "--retry", "8", "--retry-all-errors",
         "--continue-at", "-", "--output", str(partial), url],
        check=True,
    )
    actual = digest(partial)
    if actual != item["sha256"]:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum mismatch for {item['path']}")
    partial.replace(target)
    return target


def main() -> None:
    token = os.getenv("MODEL_INTERNAL_TOKEN", "")
    if not token:
        raise RuntimeError("MODEL_INTERNAL_TOKEN is required")
    manifest_name = os.getenv("MODEL_MANIFEST", "")
    manifest_path = Path("/opt/mezo/manifests") / f"{manifest_name}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = Path(os.getenv("MODEL_ROOT", "/models"))
    root.mkdir(parents=True, exist_ok=True)
    files = [download(root, manifest["repo"], manifest["revision"], item) for item in manifest["files"]]
    (root / "verified-manifest.json").write_text(
        json.dumps({"model": manifest["model"], "revision": manifest["revision"],
                    "quantization": manifest["quantization"], "files": manifest["files"]}, indent=2),
        encoding="utf-8",
    )
    server = next(Path("/opt/llama").rglob("llama-server"), None)
    if server is None:
        raise RuntimeError("Pinned llama-server binary is missing")
    context = int(os.getenv("MODEL_CONTEXT", str(manifest.get("context", 32768))))
    if context < 1024 or context > int(manifest.get("context", context)):
        raise RuntimeError("MODEL_CONTEXT must be between 1024 and the manifest maximum")
    bind_host = os.getenv("MEZO_BIND_HOST", "0.0.0.0")
    ipaddress.ip_address(bind_host)
    port = int(os.getenv("MODEL_PORT", "8080"))
    if not 1024 <= port <= 65535:
        raise RuntimeError("MODEL_PORT must be between 1024 and 65535")
    args = [
        str(server), "--model", str(files[0]), "--host", bind_host, "--port", str(port),
        "--threads", str(os.cpu_count() or 8), "--threads-batch", str(os.cpu_count() or 8),
        "--ctx-size", str(context), "--parallel", "1", "--metrics",
    ]
    if manifest.get("jinja", True):
        args.append("--jinja")
    if manifest.get("embedding"):
        args.extend(["--embedding", "--pooling", manifest.get("pooling", "last")])
    if manifest.get("reranking"):
        args.append("--reranking")
    if manifest.get("mmproj"):
        mmproj = next(path for path in files if path.name == manifest["mmproj"])
        args.extend(["--mmproj", str(mmproj)])
    environment = os.environ.copy()
    environment["LLAMA_API_KEY"] = token
    os.execve(args[0], args, environment)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"model bootstrap failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
