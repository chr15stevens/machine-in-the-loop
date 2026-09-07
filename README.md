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

Three tiers, because the good one is not always available:

1. **Vibration and a two-note chime** while the tab is open. Works everywhere, needs no
   permission. Browsers refuse to make noise until you have interacted with the page, so
   a "tap to enable alerts" pill appears in the status bar until you do.
2. **A real notification**, when the page is a secure context — `localhost`, or anything
   behind HTTPS. Served over plain HTTP to a LAN address, which is the normal way to use
   this from a phone, the Notification API simply is not there. That is a browser rule,
   not something the app can opt out of. Put it behind HTTPS (mkcert, a tunnel, Tailscale)
   and notifications come back.
3. **Push to a phone in your pocket**, via [ntfy](https://ntfy.sh):

   ```bash
   MITL_NTFY_TOPIC=some-string-only-you-know python main.py
   ```

   Install the ntfy app, subscribe to the same topic, and requests arrive on the lock
   screen. **This sends the request text off your machine** to ntfy.sh, which is why it
   is off by default. Point `MITL_NTFY_SERVER` at your own ntfy instance to keep it local.
   Topics are unauthenticated: anyone who guesses yours can read your requests, so pick
   something long.

### Notes on the design

- **In-memory.** `REQUESTS` is a module-level list. Restarting wipes it, which is
  correct for v0: a session is a sitting, not a record. Persistence is a v0.2 problem
  and should not be a database when a JSONL file will do.
- **Polling, not websockets.** The client polls every second. Over a LAN hop with an
  in-memory store that is indistinguishable from a push, at a fraction of the machinery.
- **No auth.** It binds `0.0.0.0` so your phone can reach it. That means anyone on
  your network can issue you requests. On a home network that is fine and funny. On
  café wifi it is not — see below.
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
- [x] **Waking the controller** — `/api/completions` long-polls instead of spinning.
- [x] **Waking the human** — chime, vibration, notification where permitted, optional
      ntfy push.

## Licence

LGPL-3.0-or-later. The full text is in [LICENSE](LICENSE); it applies on top of the
GPL-3.0 text in [COPYING](COPYING), which is how the LGPL is written.

In plain terms: fork it, run it, change it. If you distribute a modified version of
*these files*, those changes stay under the same licence. Building something separate
that talks to the API does not oblige you to license your own work.
