"""
The session store: the one place that owns state.

Both surfaces are thin adapters over the four verbs below — the HTTP API the
browser talks to, and the MCP tools the agent calls. Neither touches the lists
directly, so a rule like "completion is idempotent" is written once here and
cannot drift between transports.

State is module-level and in-memory. Stopping the process ends the session,
which is the intended behaviour: a sitting, not a record.
"""

from __future__ import annotations

import asyncio
import itertools
from datetime import datetime, timezone

from src.models import Completions, Request

# Longest a controller may block waiting for the human. Beyond a few minutes,
# intermediaries start cutting idle connections and the caller should re-ask.
MAX_WAIT_SECONDS = 300.0

REQUESTS: list[Request] = []
COMPLETED: list[Request] = []  # completion order, which is not issue order

_ids = itertools.count(1)

# One Event per waiting caller. A single shared Event would race: whoever
# cleared it first would strand the others.
_waiters: set[asyncio.Event] = set()


class UnknownRequest(LookupError):
    """No request with that id. Each adapter maps this to its own error shape."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _wake_waiters() -> None:
    for event in _waiters:
        event.set()
    _waiters.clear()


def list_all() -> list[Request]:
    """Every request this session, oldest first, open and completed alike."""
    return REQUESTS


def issue(text: str, note: str | None = None) -> Request:
    """Add a request to the queue. The controller's verb."""
    request = Request(id=next(_ids), text=text.strip(), note=note, issued_at=_now())
    REQUESTS.append(request)
    return request


def complete(request_id: int) -> Request:
    """
    Mark a request done. The human's verb — the button.

    Idempotent: completing an already-completed request returns it unchanged
    rather than erroring, because a double-tap means the intent already landed.
    """
    for request in REQUESTS:
        if request.id != request_id:
            continue
        if request.completed_at is not None:
            return request
        request.completed_at = _now()
        request.elapsed_seconds = round(
            (request.completed_at - request.issued_at).total_seconds(), 1
        )
        COMPLETED.append(request)
        _wake_waiters()
        return request
    raise UnknownRequest(request_id)


async def await_completions(since: int = 0, timeout: float = 90.0) -> Completions:
    """
    Block until the human completes something, then return what closed.

    A human takes minutes, so polling that gap costs a request every few seconds
    to learn nothing; blocking costs one connection. Returns immediately if
    completions are already waiting past `since`. Returns an empty list if the
    wait times out, which is not an error — just an invitation to ask again.
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
