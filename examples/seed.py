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
Seed a short session, so you can see the loop move without wiring up an agent.

    python examples/seed.py

Deliberately mundane: the point is to feel the rhythm of one-thing-at-a-time,
not to be impressed by the requests.
"""

import json
import urllib.error
import urllib.request

BASE = "http://localhost:4711"

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
