"""
The HTTP surface: routes for the browser, and nothing else.

Every handler is a thin adapter over src.store. No state and no rules live
here — see that module.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src import store
from src.mcp_server import mcp
from src.models import Completions, Request, RequestIn

# parent.parent: this module lives in src/, the UI sits at the repo root.
PUBLIC_DIR = pathlib.Path(__file__).parent.parent / "public"

# Built before the lifespan below can mention mcp.session_manager: the session
# manager is created lazily by this call, and touching it earlier raises.
# streamable_http_path="/" because we mount the whole app at /mcp.
MCP_APP = mcp.streamable_http_app(streamable_http_path="/")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """
    A mounted sub-application's lifespan never runs, so the parent has to start
    the MCP session manager itself. Omitting this fails at request time rather
    than at import, which is the annoying kind of failure.
    """
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Machine in the loop",
    description="Local-only directive board. The human is the tool being called.",
    version="0.1.0",
    lifespan=lifespan,
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


@app.api_route(
    "/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False
)
async def _mcp_trailing_slash() -> RedirectResponse:
    """
    Mounting puts the endpoint at /mcp/, and a bare /mcp would otherwise 405.
    Nobody types the trailing slash into a client config, so redirect — 307
    rather than 302, to preserve the method and the JSON-RPC body.
    """
    return RedirectResponse("/mcp/", status_code=307)


# The agent's surface. Must precede the catch-all mount below, which would
# otherwise swallow it.
app.mount("/mcp", MCP_APP, name="mcp")

# The UI is served from the same origin, so the browser needs no CORS dance.
# Mounted last so it never shadows /api or /mcp.
app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="ui")
