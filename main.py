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

Two waking mechanisms sit on top of that list. `GET /api/completions` blocks
until the human presses the button, so a controller can wait without polling.
An optional outbound push tells the human a request has arrived when their
phone is in their pocket — off unless you set MITL_NTFY_TOPIC.
"""

from __future__ import annotations

import asyncio
import itertools
import os
import pathlib
import socket
import urllib.request
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PUBLIC_DIR = pathlib.Path(__file__).parent / "public"

# Longest a controller may block on /api/completions. Beyond a few minutes,
# intermediaries start cutting idle connections and the client should re-ask.
MAX_WAIT_SECONDS = 300.0

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
    # Latency is the controller's only sensor, so it is a field rather than
    # something every client has to subtract for itself.
    elapsed_seconds: float | None = None

    @property
    def is_open(self) -> bool:
        return self.completed_at is None


class Completions(BaseModel):
    """The answer to a long-poll: what closed, and where to resume from."""

    cursor: int = Field(description="Pass this back as `since` on the next call.")
    completed: list[Request] = Field(description="Empty if the wait timed out.")


# --------------------------------------------------------------------- store

REQUESTS: list[Request] = []
COMPLETED: list[Request] = []  # completion order, which is not issue order
_ids = itertools.count(1)

# One Event per waiting controller. A single shared Event would race: whoever
# cleared it first would strand the others.
_waiters: set[asyncio.Event] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _wake_waiters() -> None:
    for event in _waiters:
        event.set()
    _waiters.clear()


async def _push_to_phone(request: Request) -> None:
    """
    Optional outbound notification, so the human can pocket the phone.

    Off unless MITL_NTFY_TOPIC is set. When it is, the request text leaves this
    machine for an ntfy server — ntfy.sh by default, or your own via
    MITL_NTFY_SERVER. That is a real privacy trade and the reason it is opt-in.
    """
    topic = os.environ.get("MITL_NTFY_TOPIC")
    if not topic:
        return

    server = os.environ.get("MITL_NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    post = urllib.request.Request(
        f"{server}/{topic}",
        data=request.text.encode("utf-8"),
        headers={"Title": "machine in the loop", "Tags": "point_right"},
        method="POST",
    )

    def send() -> None:
        try:
            urllib.request.urlopen(post, timeout=5).close()
        except OSError:
            # A missed notification must never take down the request that
            # triggered it; the UI is still the source of truth.
            pass

    await asyncio.to_thread(send)


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
    await _push_to_phone(request)
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
            request.elapsed_seconds = round(
                (request.completed_at - request.issued_at).total_seconds(), 1
            )
            COMPLETED.append(request)
            _wake_waiters()
            return request
    raise HTTPException(status_code=404, detail=f"no request with id {request_id}")


@app.get("/api/completions", response_model=Completions, tags=["control"])
async def await_completions(
    since: int = Query(0, ge=0, description="Cursor from the previous call; 0 to start."),
    timeout: float = Query(90.0, gt=0, le=MAX_WAIT_SECONDS, description="Seconds to block."),
) -> Completions:
    """
    Block until the human completes something, then return what closed.

    This is the controller's wait. A human takes minutes, so polling that gap
    burns a request every few seconds to learn nothing; blocking on one costs
    a single connection. Returns immediately if completions are already
    waiting past `since`, and returns an empty list if the wait times out —
    which is not an error, just an invitation to ask again.
    """
    if since < len(COMPLETED):
        return Completions(cursor=len(COMPLETED), completed=COMPLETED[since:])

    event = asyncio.Event()
    _waiters.add(event)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        _waiters.discard(event)

    return Completions(cursor=len(COMPLETED), completed=COMPLETED[since:])


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
    print(f"  api docs          http://localhost:{port}/docs")

    topic = os.environ.get("MITL_NTFY_TOPIC")
    if topic:
        server = os.environ.get("MITL_NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        print(f"  phone push        {server}/{topic}  (request text leaves this machine)")
    else:
        print("  phone push        off — set MITL_NTFY_TOPIC to enable")
    print()

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
