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
A controller: issue one request, block until it is done, decide the next.

    python examples/controller.py

This is the loop the project is named after. It issues exactly one open request
at a time and waits on /api/completions, so it costs nothing while the human is
away from the screen.

The decision here is a heuristic, not a model — deliberately, so the repo has no
API key and no dependencies. It reads one signal: how long the last request took.
Fast means the step was well sized and the next can be bigger; slow means
activation cost is high and the next should be smaller. That is the whole idea,
and `choose_next` is the seam where a model call replaces the if-statement.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

# Windows consoles still default to cp1252, and request text is arbitrary — a
# controller will sooner or later issue one containing an em dash. Fix the
# stream rather than restricting what a request may say.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 127.0.0.1, not "localhost": on Windows the latter resolves to ::1 first and
# the IPv4 fallback costs ~2s per call, which is a long time when you are in a
# loop. Browsers handle the dual stack fine, so the printed URLs still say
# localhost.
BASE = "http://127.0.0.1:4711"

# A re-entry protocol, in three sizes. Getting back to work after a break is the
# case where externalised executive function actually earns its keep.
LADDER: dict[str, list[str]] = {
    "small": [
        "Stand up",
        "Put one hand on the keyboard",
        "Open the file you were last working in",
    ],
    "medium": [
        "Read the last thing you wrote, out loud",
        "Write one sentence — it is allowed to be bad",
        "Delete one line you know is wrong",
    ],
    "large": [
        "Finish the paragraph you started",
        "Write the next test you know you need",
        "Work on one thing until you notice yourself drifting",
    ],
}

# Ordered smallest to largest; choose_next walks one rung at a time.
SIZES = ["small", "medium", "large"]

# Above this, the human is struggling with size, not with the task.
SLOW_SECONDS = 90.0
# Below this, the step was trivial and we are wasting their attention.
FAST_SECONDS = 20.0


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def get(path: str, timeout: float = 120.0) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as response:
        return json.load(response)


def issue(text: str) -> dict:
    created = post("/api/requests", {"text": text})
    print(f"  → {created['text']}")
    return created


def await_completion(cursor: int) -> tuple[int, dict | None]:
    """Block until something closes. Returns the new cursor and what closed."""
    while True:
        result = get(f"/api/completions?since={cursor}&timeout=90", timeout=120)
        cursor = result["cursor"]
        if result["completed"]:
            return cursor, result["completed"][-1]
        # A timeout is not an error — the human is simply still working.
        print("  … still waiting")


def choose_next(size: str, elapsed: float | None) -> str:
    """
    The seam. Swap this for a model call and the loop becomes an agent.

    Everything a model would need is already here: the size of the last step and
    how long it took. What it must NOT do is escalate when a request goes
    unanswered — see AGENT.md.

    One step at a time, and it saturates at each end: a run of fast completions
    should settle at "large" and stay there, not oscillate.
    """
    if elapsed is None:
        return size

    rung = SIZES.index(size)
    if elapsed > SLOW_SECONDS:
        moved = SIZES[max(0, rung - 1)]
        if moved != size:
            print(f"  ({elapsed:.0f}s — that was hard, going smaller)")
        return moved
    if elapsed < FAST_SECONDS:
        moved = SIZES[min(len(SIZES) - 1, rung + 1)]
        if moved != size:
            print(f"  ({elapsed:.0f}s — that landed, going bigger)")
        return moved
    return size


def main() -> None:
    print("\n  controller: one request at a time, waiting on the human\n")

    size = "small"
    cursor = 0
    used: set[str] = set()

    try:
        while True:
            candidates = [text for text in LADDER[size] if text not in used]
            if not candidates:
                print("\n  out of requests at this size. Stopping.\n")
                return

            text = candidates[0]
            used.add(text)
            issue(text)

            cursor, completed = await_completion(cursor)
            elapsed = completed.get("elapsed_seconds") if completed else None
            print(f"  ✓ {completed['text']}  ({elapsed}s)")

            size = choose_next(size, elapsed)

    except KeyboardInterrupt:
        print("\n  controller stopped. Anything still open stays open.\n")
    except urllib.error.URLError:
        raise SystemExit("Could not reach the server. Is `python main.py` running?")


if __name__ == "__main__":
    main()
