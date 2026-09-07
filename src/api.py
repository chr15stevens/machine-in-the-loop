from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import itertools
import pathlib

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from src.models import Completions, Request, RequestIn

PUBLIC_DIR = pathlib.Path(__file__).parent / "public"

# Longest a controller may block on /api/completions. Beyond a few minutes,
# intermediaries start cutting idle connections and the client should re-ask.
MAX_WAIT_SECONDS = 300.0


# One Event per waiting controller. A single shared Event would race: whoever
# cleared it first would strand the others.
_waiters: set[asyncio.Event] = set()

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _wake_waiters() -> None:
    for event in _waiters:
        event.set()
    _waiters.clear()
    
REQUESTS: list[Request] = []
COMPLETED: list[Request] = []  # completion order, which is not issue order
_ids = itertools.count(1)

app = FastAPI(
    title="machine in the loop",
    description="Local-only directive board. The human is the tool being called.",
    version="0.1.0",
)

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
