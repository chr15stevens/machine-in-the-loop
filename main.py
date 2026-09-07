from __future__ import annotations

import sys

from src import notify, shortcut
from src.api import app
from src.config import PORT

if __name__ == "__main__":
    if "--uninstall-notifications" in sys.argv:
        print(shortcut.remove())
        raise SystemExit

    import uvicorn

    # Windows needs a registered app identity before a notification click can
    # open anything, and the only way to declare one for an unpackaged app is a
    # Start Menu shortcut. Idempotent, and it repairs itself if the repo moves.
    # See src/shortcut.py, and the README for how to remove it.
    registration = shortcut.ensure()

    print("\n  machine in the loop\n")
    print(f"  open              http://localhost:{PORT}")
    print(f"  api docs          http://localhost:{PORT}/docs")
    print(f"  mcp               http://127.0.0.1:{PORT}/mcp")
    print(f"  notifications     {notify.capability()}")
    if shortcut.supported():
        print(f"  start menu entry  {registration}")
    # flush: uvicorn.run blocks forever, so a block-buffered stdout (anything
    # other than a terminal) would swallow the banner entirely.
    print("\n  Bound to 127.0.0.1 — this device only. Nothing leaves the machine.\n", flush=True)

    # 127.0.0.1, not 0.0.0.0: nothing off this machine can reach it, which is
    # also why there is no auth to write.
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
