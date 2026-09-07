# machine in the loop

**Human-in-the-loop, inverted. The model runs the loop; you are the hands.**

Normally an agent calls `bash`, gets a clean string back, and plans its next move.
This swaps the tool for a person. The agent issues a request, it appears on your
phone in large type, and you press one button when it is done.

The interesting part is not the app — it is what happens to the agent's planning.
Its tool is now high-latency, non-deterministic, refusable, and embodied. It has to
decompose goals into single physical acts, sequence them, and cope with a tool that
takes four minutes to return. Meanwhile you get externalised executive function:
one instruction at a time, no queue to stare at, no decision to make.

> v0 is deliberately tiny: **one screen, one button, one endpoint that matters.**

<sub>On the name: HCI already uses "machine-in-the-loop" for systems where a machine
assists a human who stays in control. Here the principal is reversed — the machine
decides, the human acts. The collision is deliberate.</sub>

---

## Quickstart

```bash
python -m venv .venv && .venv/Scripts/activate  # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

It prints a `localhost` URL and a LAN URL. Open the LAN one on your phone — that is
the point of the thing. Then, from anywhere:

```bash
curl -X POST http://localhost:4711/api/requests \
  -H 'content-type: application/json' \
  -d '{"text": "Stand up and refill your water bottle"}'
```

It is on your phone within a second. Press **Done**.

To see it move, seed a short session:

```bash
python examples/seed.py
```

---

## The API

Three endpoints. Two of them are one line.

| Method | Path | Who calls it |
| --- | --- | --- |
| `GET` | `/api/requests` | anyone — the full list, oldest first |
| `POST` | `/api/requests` | the **controller** — issue a request |
| `POST` | `/api/requests/{id}/complete` | the **human** — the button |

A request:

```json
{
  "id": 1,
  "text": "Stand up and refill your water bottle",
  "note": null,
  "issued_at": "2026-09-07T08:31:29.480758Z",
  "completed_at": null
}
```

`completed_at: null` means open. The UI shows the oldest open one and nothing else.
Interactive docs at `/docs`.

### Notes on the design

- **In-memory.** `REQUESTS` is a module-level list. Restarting wipes it, which is
  correct for v0: a session is a sitting, not a record. Persistence is a v0.2 problem
  and should not be a database when a JSONL file will do.
- **Polling, not websockets.** The client polls every second. Over a LAN hop with an
  in-memory store that is indistinguishable from a push, at a fraction of the machinery.
- **No auth.** It binds `0.0.0.0` so your phone can reach it. That means anyone on
  your network can issue you requests. On a home network that is fine and funny. On
  café wifi it is not — see below.
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
- **Bind to localhost** (`host="127.0.0.1"` in `main.py`) if you are not on a network
  you trust. There is no auth by design, and adding some is a fine first PR.

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
- [ ] **Push** — a web push subscription, so the phone can be in a pocket.

## Licence

MIT. See [LICENSE](LICENSE).
