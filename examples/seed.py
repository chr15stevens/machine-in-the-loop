"""
Seed a short session, so you can see the loop move without wiring up an agent.

    python examples/seed.py

Deliberately mundane: the point is to feel the rhythm of one-thing-at-a-time,
not to be impressed by the requests.
"""

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

REQUESTS = [
    ("Stand up", None),
    ("Refill your water bottle", "You have been at the desk a while."),
    ("Look at something 20 feet away for 20 seconds", None),
    ("Write one sentence of the thing you are avoiding", "Any sentence. It can be bad."),
]


def issue(text: str, note: str | None) -> dict:
    payload = json.dumps({"text": text, "note": note}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/requests",
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as res:
        return json.load(res)


def main() -> None:
    try:
        for text, note in REQUESTS:
            created = issue(text, note)
            print(f"  {created['id']:>3}  {created['text']}")
    except urllib.error.URLError:
        raise SystemExit("Could not reach the server. Is `python main.py` running?")

    print(f"\n  {len(REQUESTS)} requests issued. Open {BASE} and start pressing.\n")


if __name__ == "__main__":
    main()
