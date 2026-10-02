from __future__ import annotations

import json
import socket
import sys
from urllib.error import URLError
from urllib.request import urlopen


HOST = "127.0.0.1"
PORT = 8765
HEALTH_URL = f"http://{HOST}:{PORT}/health"


def _port_open() -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.6)
    try:
        return sock.connect_ex((HOST, PORT)) == 0
    finally:
        sock.close()


def main() -> int:
    if not _port_open():
        print("FREE")
        return 0

    try:
        with urlopen(HEALTH_URL, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        name = str(payload.get("name") or "")
        status = str(payload.get("status") or "")
        if status == "ok" and name:
            print(f"AISHIN_RUNNING|{name}")
            return 10
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    print(f"PORT_BUSY|{HOST}:{PORT}")
    return 11


if __name__ == "__main__":
    raise SystemExit(main())
