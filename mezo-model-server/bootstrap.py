from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path


ROOT = Path("/models")
ROOT.mkdir(parents=True, exist_ok=True)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def download(repo: str, revision: str, item: dict[str, str]) -> Path:
    target = ROOT / Path(item["path"]).name
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
    files = [download(manifest["repo"], manifest["revision"], item) for item in manifest["files"]]
    (ROOT / "verified-manifest.json").write_text(
        json.dumps({"model": manifest["model"], "revision": manifest["revision"],
                    "quantization": manifest["quantization"], "files": manifest["files"]}, indent=2),
        encoding="utf-8",
    )
    server = next(Path("/opt/llama").rglob("llama-server"), None)
    if server is None:
        raise RuntimeError("Pinned llama-server binary is missing")
    args = [
        str(server), "--model", str(files[0]), "--host", "0.0.0.0", "--port", "8080",
        "--threads", str(os.cpu_count() or 8), "--threads-batch", str(os.cpu_count() or 8),
        "--ctx-size", str(manifest.get("context", 32768)), "--parallel", "1", "--metrics",
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
