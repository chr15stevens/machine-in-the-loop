# machine in the loop — human in the loop, inverted.
# Copyright (C) 2026 Chris Stevens
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License
# for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
machine in the loop — human in the loop, inverted.

A controller (an agent, or you with curl) posts requests. A human sees the
oldest open one on their phone and presses a single button when it is done.

State lives in a module-level list. Restarting the process wipes it, which is
the correct behaviour for v0: a session is a sitting, not a record. Every
handler is `async def`, so they all run on the one event-loop thread and the
list needs no lock.
"""

from __future__ import annotations

import itertools
import pathlib
import socket
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PUBLIC_DIR = pathlib.Path(__file__).parent / "public"

app = FastAPI(
    title="machine in the loop",
    description="Local-only directive board. The human is the tool being called.",
    version="0.1.0",
)


# --------------------------------------------------------------------- models


class RequestIn(BaseModel):
    """What the controller sends."""

    text: str = Field(min_length=1, max_length=500, description="The instruction, imperative and unambiguous.")
    note: str | None = Field(default=None, max_length=1000, description="Optional context the human may want.")


class Request(BaseModel):
    """What the human sees, and what the controller reads back."""

    id: int
    text: str
    note: str | None = None
    issued_at: datetime
    completed_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.completed_at is None


# --------------------------------------------------------------------- store

REQUESTS: list[Request] = []
_ids = itertools.count(1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------- routes


@app.get("/api/requests", response_model=list[Request], tags=["read"])
async def list_requests() -> list[Request]:
    """Every request this session, oldest first, open and completed alike."""
    return REQUESTS


@app.post("/api/requests", response_model=Request, status_code=201, tags=["control"])
async def create_request(body: RequestIn) -> Request:
    """Issue a request. This is the controller's only verb."""
    request = Request(id=next(_ids), text=body.text.strip(), note=body.note, issued_at=_now())
    REQUESTS.append(request)
    return request


@app.post("/api/requests/{request_id}/complete", response_model=Request, tags=["human"])
async def complete_request(request_id: int) -> Request:
    """Mark a request done. This is the human's only verb — the button."""
    for request in REQUESTS:
        if request.id == request_id:
            if request.completed_at is not None:
                # A double-tap, or a second tab. Not an error; the intent already landed.
                return request
            request.completed_at = _now()
            return request
    raise HTTPException(status_code=404, detail=f"no request with id {request_id}")


# The UI is served from the same origin, so the browser needs no CORS dance.
# Mounted last so it never shadows /api.
app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="ui")


# --------------------------------------------------------------------- boot


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
    print(f"  api docs          http://localhost:{port}/docs\n")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
