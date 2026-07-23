from __future__ import annotations

import ipaddress
import os

import uvicorn


def main() -> None:
    host = os.getenv("MEZO_BIND_HOST", "0.0.0.0")
    ipaddress.ip_address(host)
    uvicorn.run("main:app", host=host, port=8080, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
