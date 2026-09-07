from __future__ import annotations

import os
import socket

from src.api import app

def _lan_address() -> str | None:
    """Best-effort local IP, so you can open this on your phone."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))  # never sends a packet
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


if __name__ == "__main__":
    import uvicorn

    port = 4711
    lan = _lan_address()
    print("\n  machine in the loop\n")
    print(f"  on this machine   http://localhost:{port}")
    if lan:
        print(f"  on your phone     http://{lan}:{port}")
    print(f"  api docs          http://localhost:{port}/docs")

    topic = os.environ.get("MITL_NTFY_TOPIC")
    if topic:
        server = os.environ.get("MITL_NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        print(f"  phone push        {server}/{topic}  (request text leaves this machine)")
    else:
        print("  phone push        off — set MITL_NTFY_TOPIC to enable")
    print()

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
