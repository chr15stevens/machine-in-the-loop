# machine in the loop

**Human-in-the-loop, inverted. The model runs the loop; you are the hands.**

Normally an agent calls `bash`, gets a clean string back, and plans its next move.
This swaps the tool for a person. The agent issues a request, it appears on screen
in large type, and you press one button when it is done.

The interesting part is not the app — it is what happens to the agent's planning.
Its tool is now high-latency, non-deterministic, refusable, and embodied. It has to
decompose goals into single physical acts, sequence them, and cope with a tool that
takes four minutes to return. Meanwhile you get externalised executive function:
one instruction at a time, no queue to stare at, no decision to make.

> v0 is deliberately tiny: **one screen, one button, one endpoint that matters.**

---

## Quickstart

```bash
python -m venv .venv && .venv/Scripts/activate  # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

It binds `127.0.0.1` and prints one URL. Open it, then from another terminal:

```bash
curl -X POST http://127.0.0.1:4711/api/requests \
  -H 'content-type: application/json' \
  -d '{"text": "Stand up and refill your water bottle"}'
```

It is on screen within a second. Press **Done**.

To see it move, seed a short session:

```bash
python examples/seed.py
```

---

## The API

Four endpoints. Three of them are trivial; the fourth is where the loop lives.

| Method | Path | Who calls it |
| --- | --- | --- |
| `GET` | `/api/requests` | anyone — the full list, oldest first |
| `POST` | `/api/requests` | the **controller** — issue a request |
| `POST` | `/api/requests/{id}/complete` | the **human** — the button |
| `GET` | `/api/completions` | the **controller** — block until the button is pressed |

A request:

```json
{
  "id": 1,
  "text": "Stand up and refill your water bottle",
  "note": null,
  "issued_at": "2026-09-07T08:31:29.480758Z",
  "completed_at": null,
  "elapsed_seconds": null
}
```

`completed_at: null` means open. The UI shows the oldest open one and nothing else.
Interactive docs at `/docs`.

### Waiting for the human

A human takes minutes. Polling that gap burns a request every few seconds to learn
nothing, so `/api/completions` blocks instead:

```bash
curl "http://127.0.0.1:4711/api/completions?since=0&timeout=90"
```

It returns as soon as something is completed, with a `cursor` to pass back as `since`
next time. If the wait times out it returns an empty list, which is not an error — the
human is simply still working. Ask again.

```json
{ "cursor": 3, "completed": [ { "id": 3, "elapsed_seconds": 47.2, "...": "..." } ] }
```

`elapsed_seconds` is the point. It is the only sensor the controller has.

### The loop

```bash
python examples/controller.py
```

Issues one request, blocks until it is done, and picks the next size from how long the
last one took — fast means step up, slow means step down. The decision is a heuristic,
not a model, so the repo needs no API key; `choose_next` is the seam where a model call
replaces the if-statement.

### Getting the human's attention

All on-device. Nothing is sent anywhere:

- **A two-note chime and a vibration** when a request arrives. Browsers refuse to make
  noise until you have interacted with the page, so a "tap to enable alerts" pill sits in
  the status bar until you do.
- **A desktop notification** when the tab is in the background, plus the request text in
  the tab title.

Push to a phone is deliberately out of scope: it would mean either exposing the server
beyond this machine or relaying through a third party, and neither is worth it yet.


### Notes on the design

- **In-memory.** `REQUESTS` is a module-level list. Restarting wipes it, which is
  correct for v0: a session is a sitting, not a record. Persistence is a v0.2 problem
  and should not be a database when a JSONL file will do.
- **Polling, not websockets.** The client polls every second. Against an in-memory store
  on the same machine that is indistinguishable from a push, at a fraction of the machinery.
- **This device only.** It binds `127.0.0.1`. Nothing off this machine can reach it,
  which is why there is no auth to write and nothing to secure.
- **Use `127.0.0.1`, not `localhost`, from Python clients.** On Windows `localhost`
  resolves to `::1` first and the IPv4 fallback costs about two seconds per call. The
  examples already do this. Browsers are unaffected.
- **No lock.** Every handler is `async def`, so they share one event-loop thread.
- **Completion is idempotent.** A double-tap returns the existing record rather than
  erroring, because the human's intent already landed.

---

## Writing good requests

This is most of the product. See [AGENT.md](AGENT.md) for the full controller
contract; the short version:

- **One physical act per request.** "Tidy the kitchen" is a project. "Put the mugs in
  the dishwasher" is a request.
- **Observable completion.** The human must know, without deciding, when to press the
  button.
- **Issue one at a time.** The queue is visible but the screen is not. Dumping twelve
  requests turns it back into a todo list, which is the thing you were escaping.
- **Latency is data.** `issued_at` vs `completed_at` tells the controller what was
  hard and what was avoided. That signal is the whole reason to time-stamp anything.

---

## Safety, briefly

The subject is a person, so the controller has limits that a `bash` tool does not:

- **Consent is per-session and revocable.** Closing the tab ends it. Ctrl-C ends it harder.
- **Never issue anything that can injure**, or anything medical, financial, legal, or
  ingestible. Not "take 400mg of ibuprofen", not "send £200 to X".
- **Never issue anything irreversible or outward-facing** on the subject's behalf —
  sending messages, posting, deleting, buying.
- **Pressure is out of scope.** No streaks, no shaming copy, no escalation when a
  request goes unanswered. An unanswered request is information, not disobedience.

If you point this at someone other than yourself, they get the button and you get the
keyboard — never the reverse without them agreeing to it first, out loud, that session.

---

## Roadmap

v0 is one button on purpose. The next honest increments:

- [ ] **"Can't do this"** — the refusal path, with a reason string the controller reads.
      This is the most important missing piece; right now an unwanted request can only
      be ignored.
- [ ] **Observations** — let the human send text back, so the agent can ask questions,
      not just give orders.
- [ ] **Photos** — `<input type="file" capture="environment">` closes the perception
      loop and needs no native app.
- [ ] **A real MCP server** — so any Claude client is a controller with no glue code.
- [ ] **Persistence** — JSONL append log, so sessions can be reviewed afterwards.
- [x] **Waking the controller** — `/api/completions` long-polls instead of spinning.
- [x] **Waking the human** — chime, vibration, and a desktop notification, all local.

