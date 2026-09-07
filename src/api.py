"""
The HTTP surface: routes for the browser, and nothing else.

Every handler is a thin adapter over src.store. No state and no rules live
here — see that module.
"""

from __future__ import annotations

import pathlib

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from src import store
from src.models import Completions, Request, RequestIn

# parent.parent: this module lives in src/, the UI sits at the repo root.
PUBLIC_DIR = pathlib.Path(__file__).parent.parent / "public"

app = FastAPI(
    title="machine in the loop",
    description="Local-only directive board. The human is the tool being called.",
    version="0.1.0",
)


@app.get("/api/requests", response_model=list[Request], tags=["read"])
async def list_requests() -> list[Request]:
    """Every request this session, oldest first, open and completed alike."""
    return store.list_all()


@app.post("/api/requests", response_model=Request, status_code=201, tags=["control"])
async def create_request(body: RequestIn) -> Request:
    """Issue a request. This is the controller's only verb."""
    return store.issue(body.text, body.note)


@app.post("/api/requests/{request_id}/complete", response_model=Request, tags=["human"])
async def complete_request(request_id: int) -> Request:
    """Mark a request done. This is the human's only verb — the button."""
    try:
        return store.complete(request_id)
    except store.UnknownRequest:
        raise HTTPException(status_code=404, detail=f"no request with id {request_id}")


@app.get("/api/completions", response_model=Completions, tags=["control"])
async def await_completions(
    since: int = Query(0, ge=0, description="Cursor from the previous call; 0 to start."),
    timeout: float = Query(
        90.0, gt=0, le=store.MAX_WAIT_SECONDS, description="Seconds to block."
    ),
) -> Completions:
    """
    Block until the human completes something, then return what closed.

    Returns immediately if completions are already waiting past `since`, and
    returns an empty list if the wait times out — which is not an error, just
    an invitation to ask again.
    """
    return await store.await_completions(since=since, timeout=timeout)


# The UI is served from the same origin, so the browser needs no CORS dance.
# Mounted last so it never shadows /api.
app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="ui")
