from __future__ import annotations

from src import notify
from src.api import app
from src.config import PORT

if __name__ == "__main__":
    import uvicorn

    print("\n  machine in the loop\n")
    print(f"  open              http://localhost:{PORT}")
    print(f"  api docs          http://localhost:{PORT}/docs")
    print(f"  mcp               http://127.0.0.1:{PORT}/mcp")
    print(f"  notifications     {notify.capability()}")
    # flush: uvicorn.run blocks forever, so a block-buffered stdout (anything
    # other than a terminal) would swallow the banner entirely.
    print("\n  Bound to 127.0.0.1 — this device only. Nothing leaves the machine.\n", flush=True)

    # 127.0.0.1, not 0.0.0.0: nothing off this machine can reach it, which is
    # also why there is no auth to write.
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
