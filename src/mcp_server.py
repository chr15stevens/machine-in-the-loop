"""
The MCP surface: the same four verbs as the HTTP API, exposed as tools.

Mounted into the FastAPI app in src.api, so this shares one process, one event
loop and one store with the page the human is looking at. That matters: the
long-poll wakes waiters through an asyncio.Event, which only works if the
waiter and the setter are on the same loop.

The docstrings below are not comments. They are the tool descriptions the model
reads at call time, and they are the only contract it sees — nothing loads
AGENT.md into an agent's context. Anything that must constrain behaviour has to
be written here.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from src import store
from src.models import Request

mcp = MCPServer("Machine in the loop")


def _as_dict(request: Request) -> dict[str, Any]:
    return request.model_dump(mode="json")


@mcp.tool()
async def issue_request(text: str, note: str | None = None) -> dict[str, Any]:
    """
    Give the human one physical act to perform. Returns the created request.

    You are not calling a function; you are asking a person to do something in
    the world. Write `text` as a single imperative sentence in the second
    person — it is displayed in large type and read at a glance.

    Size it so that ONE physical act finishes it, and so the human never has to
    judge whether they are done. "Put the mugs in the dishwasher" is a request.
    "Tidy the kitchen" is a project — decompose it yourself and issue the first
    step only. Use `note` for context; `text` must stand alone without it.
    """
    return _as_dict(store.issue(text, note))


@mcp.tool()
async def await_completion(since: int = 0, timeout: float = 90.0) -> dict[str, Any]:
    """
    Block until the human presses the button, then return what they completed.

    This is how you wait. Call it after issuing a request and let it block —
    do NOT poll list_requests in a loop, which spends a call every few seconds
    to learn that a person is still walking to the kitchen.

    Pass `since` as the `cursor` from your previous call (0 to start). The
    result is {"cursor": int, "completed": [request, ...]}.

    An empty `completed` list means the wait timed out, not that anything is
    wrong. Call again with the same cursor. If it keeps timing out over several
    minutes, stop and say so — do not escalate, do not reissue, and do not send
    a reminder.

    Each completed request carries `elapsed_seconds`. That is the only sensor
    you have. Fast means the step was well sized and the next can be bigger.
    Slow means activation cost was high and the next should be smaller. A run
    of slow completions means your requests are too big, not that the human is
    failing.
    """
    result = await store.await_completions(
        since=since,
        timeout=min(timeout, store.MAX_WAIT_SECONDS),
    )
    return result.model_dump(mode="json")


@mcp.tool()
async def list_requests() -> list[dict[str, Any]]:
    """
    Every request this session, oldest first, open and completed alike.

    For orienting yourself — after a reconnect, or to check what is still open
    before issuing more. To wait for the next completion use await_completion,
    not this in a loop.

    A request with `completed_at: null` is still open.
    """
    return [_as_dict(request) for request in store.list_all()]
