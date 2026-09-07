from __future__ import annotations

from src.api import app

if __name__ == "__main__":
    import uvicorn

    port = 4711
    print("\n  machine in the loop\n")
    print(f"  open              http://localhost:{port}")
    print(f"  api docs          http://localhost:{port}/docs")
    # flush: uvicorn.run blocks forever, so a block-buffered stdout (anything
    # other than a terminal) would swallow the banner entirely.
    print("\n  Bound to 127.0.0.1 — this device only. Nothing leaves the machine.\n", flush=True)

    # 127.0.0.1, not 0.0.0.0: nothing off this machine can reach it, which is
    # also why there is no auth to write.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
