# Machine in the loop

**Human-in-the-loop, inverted: the agent plans and directs, the human executes.**

Conventional human-in-the-loop designs place the person above the agent, as approver
and supervisor. This inverts that relationship. The agent holds the plan and issues
requests; the human is an effector it calls and waits on. Mechanically: a request
appears on screen in large type, and the human presses one button when it is done.

**Hypothesis.** An agent that cannot act in the physical world spends planning
capacity on that boundary — recognising what it cannot do, hedging around it,
restructuring goals to avoid it, or declining outright. Delegating those actions to
an executor that can actually perform them should remove the overhead and free
capacity for higher-level planning. The intent is to grant the agent more autonomy,
not less: it owns the plan, and the constraint it was working around is gone.

This repo is the minimal apparatus for testing whether that trade is worth making.

![The request screen: one instruction in large type, one button, and a log of what has
been completed](docs/screenshot.png)

---

## Quickstart

Three steps. All of them are required — after step 2 the tools exist but nothing
will call them.

### 1. Run the server

```bash
python -m venv .venv && .venv/Scripts/activate  # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Binds `127.0.0.1` and prints one URL. Open it — that page is where requests appear
and the only place they can be completed. Leave the server running; the steps below
need it up.

### 2. Register the MCP server

```bash
claude mcp add --transport http --scope user machine-in-the-loop http://127.0.0.1:4711/mcp
```

`--scope user` makes it available in every project. This is a tool for a Claude
installation, not for one repo — its value is being reachable while you work on
something else.

### 3. Tell the agent to use it

Registering the server makes the tools available; it does not make a model reach for
them. No ordinary task announces that it needs a pair of hands, so without this step
a correct install sits idle indefinitely.

Add to `~/.claude/CLAUDE.md` — the user-level file, not a project one, for the same
reason as `--scope user`:

```markdown
Never claim you can't do something without checking your tools first. "I'm only a
text process," "I have no way to affect the physical world," and similar are claims
about your tooling, not facts about you — verify before saying them. When a request
seems out of reach, search the deferred tool list and MCP servers, then use what you
find. Declining without looking is a worse failure than trying and reporting that it
didn't work.

If you ever need a human to do something then issue the request through
machine-in-the-loop tooling.
```

The second line connects "I need a person" to a specific tool. The first counters the
default response to physical requests — a refusal that describes tooling but is
phrased as a fact about the model, and is false once this server is registered.

### Check it works

Start a **new** Claude Code session — one already running will not pick up a newly
registered server — and ask for something that needs hands:

```
Make me a coffee.
```

It should call `issue_request`, the request should appear on the page and as an OS
notification, and the agent should block on `await_completion` until you press
**Done**.

---

## Driving it without an agent

```bash
curl -X POST http://127.0.0.1:4711/api/requests \
  -H 'content-type: application/json' \
  -d '{"text": "Stand up and refill your water bottle"}'
```

Seed a short session, or run a controller loop that adapts to how long you take:

```bash
python examples/seed.py
python examples/controller.py
```

`controller.py` issues one request, blocks until it is done, and picks the next size
from the last one's latency. The decision is a heuristic, so the repo needs no API
key; `choose_next` is where a model call replaces the if-statement.

---

## The API

| Method | Path | Caller |
| --- | --- | --- |
| `GET` | `/api/requests` | anyone — the full list, oldest first |
| `POST` | `/api/requests` | controller — issue a request |
| `POST` | `/api/requests/{id}/complete` | human — the button |
| `GET` | `/api/completions` | controller — block until the button is pressed |
| `*` | `/mcp` | agent — the same verbs as MCP tools |

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

`completed_at: null` means open. The UI shows the oldest open request and nothing
else. Interactive docs at `/docs`.

### Waiting for the human

`/api/completions` blocks rather than making the caller poll:

```bash
curl "http://127.0.0.1:4711/api/completions?since=0&timeout=90"
```

Returns as soon as something is completed, with a `cursor` to pass back as `since`.
A timeout returns an empty list — not an error; call again with the same cursor.

```json
{ "cursor": 3, "completed": [ { "id": 3, "elapsed_seconds": 47.2, "...": "..." } ] }
```

Default block is 90s, ceiling 300s. Over the ceiling the HTTP endpoint returns 422;
the MCP tool clamps instead. `elapsed_seconds` is the controller's only signal.

### The MCP surface

Mounted into the same app: one process, one store, one event loop.

Tools: `issue_request`, `await_completion`, `list_requests`. There is no `complete`
tool — an agent cannot press the button.

The tool docstrings in `src/mcp_server.py` are the contract. Nothing loads
`AGENT.md` at call time, so request sizing and the hard limits live in the
docstrings.

---

## Notifications

All on-device.

**Page open:** a two-note chime and vibration, the request text in the tab title,
and a browser notification when the tab is backgrounded. Browsers block audio until
you interact with the page, so a "tap to enable alerts" pill sits in the status bar
until you do.

**Page closed:** the server raises an OS notification; clicking it opens the page.
On Windows it persists until acted on and plays a sound — a default toast from an
unpackaged app shows for about five seconds, silently, and is not retained in the
Action Center. Each request gets its own toast rather than replacing the last.

| | Notification | Click opens the page |
| --- | --- | --- |
| Windows | toast, via PowerShell | yes — once the Start Menu entry exists |
| macOS | `terminal-notifier` if installed | yes |
| macOS | `osascript` otherwise | no — it cannot attach a click target |
| Linux | `notify-send` | only if your notification daemon supports actions |

`MITL_NOTIFY=0` silences them. The startup banner reports what your machine can do.

**A notification cannot complete a request.** Its only action hands the URL to your
browser. The Done button is the sole way to close one.

Notifications need no libraries — each platform ships something that raises one.
The only dependency is `pywin32` on Windows, used solely to write the Start Menu
shortcut.

> **Windows: this creates a Start Menu entry.** On startup the server writes
> `Machine in the loop.lnk`. Windows routes a notification click back to the app
> that posted it, identified by an AppUserModelID; the only way an unpackaged app
> can declare one is a Start Menu shortcut carrying that property. Without it the
> toast shows and the click is dropped. This is what an ordinary installer does.
>
> The shortcut points at your interpreter and this repo, so it doubles as a
> launcher. No paths are hardcoded — they are derived at startup, so moving the repo
> repairs itself on the next run.
>
> Remove with `python main.py --uninstall-notifications`, or delete the `.lnk`.
> Notifications keep working; only the click stops opening the page.

Push to a phone is out of scope: it requires either exposing the server beyond this
machine or relaying through a third party.

---

## Design notes

- **In-memory.** `src/store.py` owns two module-level lists. Restarting wipes them:
  a session is a sitting, not a record.
- **Polling, not websockets.** The client polls every second. Against a local
  in-memory store that is indistinguishable from a push.
- **This device only.** Binds `127.0.0.1`, so there is no auth to write.
- **Use `127.0.0.1`, not `localhost`, from Python clients.** On Windows `localhost`
  resolves to `::1` first and the IPv4 fallback costs ~2s per call. Browsers are
  unaffected.
- **One store, two surfaces.** `src/api.py` and `src/mcp_server.py` are thin adapters
  over `src/store.py`; neither touches the lists, so the rules cannot drift.
- **No lock.** Everything is `async def` on one event-loop thread. This is also why
  the MCP server is mounted rather than run as a second process: the long-poll wakes
  waiters through an `asyncio.Event`, which requires a shared loop.
- **Completion is idempotent.** A double-tap returns the existing record.

---

## Writing good requests

See [AGENT.md](AGENT.md) for the full controller contract.

- **One physical act per request.** "Tidy the kitchen" is a project. "Put the mugs in
  the dishwasher" is a request.
- **Observable completion.** The human must know, without deciding, when to press the
  button.
- **Issue one at a time.** Dumping twelve requests rebuilds a todo list.
- **Latency is data.** `elapsed_seconds` distinguishes what was hard from what was
  avoided.

---

## Safety

The subject is a person, so the controller has limits a `bash` tool does not:

- **Consent is per-session and revocable.** Closing the tab ends it; Ctrl-C ends it
  harder.
- **Never issue anything that can injure**, or anything medical, financial, legal, or
  ingestible.
- **Never issue anything irreversible or outward-facing** on the subject's behalf —
  sending, posting, deleting, buying.
- **No pressure.** No streaks, no shaming copy, no escalation when a request goes
  unanswered. An unanswered request is information, not disobedience.

If you point this at someone other than yourself, they get the button and you get the
keyboard — not the reverse, and not without their agreement that session.

---

## Roadmap

- [ ] **"Can't do this"** — a refusal path with a reason string the controller reads.
      Currently an unwanted request can only be ignored.
- [ ] **Persistence** — JSONL append log, so sessions can be reviewed afterwards.
- [x] **MCP server** — mounted into the same app.
- [x] **Waking the controller** — `/api/completions` long-polls instead of spinning.
- [x] **Waking the human** — chime, vibration, and OS notifications, all local.
