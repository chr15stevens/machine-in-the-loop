/*
 * machine in the loop — human in the loop, inverted.
 * Copyright (C) 2026 Chris Stevens
 *
 * This program is free software: you can redistribute it and/or modify it
 * under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or (at your
 * option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License
 * for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */

'use strict';

/**
 * The subject client. One job: show the oldest open request, and let the human
 * press one button to close it.
 *
 * It polls. With an in-memory store and a LAN hop, a 1s poll is indistinguishable
 * from a push and costs a fraction of the machinery.
 */

const $ = (id) => document.getElementById(id);

const el = {
  conn: $('conn'),
  connLabel: $('conn-label'),
  completed: $('completed'),
  pending: $('pending'),
  panelIdle: $('panel-idle'),
  panelActive: $('panel-active'),
  text: $('directive-text'),
  note: $('directive-note'),
  elapsed: $('elapsed'),
  done: $('done'),
  upcoming: $('upcoming'),
  logWrap: $('log-wrap'),
  logToggle: $('log-toggle'),
  log: $('log'),
};

const POLL_MS = 1000;

let current = null; // the request on screen
let shownId = null; // last id we buzzed for
let inFlight = false;

// ------------------------------------------------------------------ chrome

function setConn(status) {
  el.conn.dataset.state = status;
  el.connLabel.textContent =
    status === 'live' ? 'live' : status === 'lost' ? 'disconnected' : 'connecting';
}

function buzz(pattern) {
  if (!navigator.vibrate) return;
  try {
    navigator.vibrate(pattern);
  } catch {
    /* vibration is a nicety, never a requirement */
  }
}

function clockOf(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ------------------------------------------------------------------ render

function render(requests) {
  const open = requests.filter((r) => !r.completed_at);
  const closed = requests.filter((r) => r.completed_at);

  el.pending.textContent = String(open.length);
  el.completed.textContent = String(closed.length);

  current = open[0] || null;

  el.panelActive.hidden = !current;
  el.panelIdle.hidden = !!current;

  if (current) {
    if (current.id !== shownId) {
      shownId = current.id;
      buzz([14, 60, 14]); // a new request landed while the phone was in a pocket
    }
    el.text.textContent = current.text;
    el.note.textContent = current.note || '';
    el.note.hidden = !current.note;

    el.upcoming.innerHTML = '';
    for (const item of open.slice(1, 4)) {
      const li = document.createElement('li');
      li.textContent = item.text;
      el.upcoming.appendChild(li);
    }
  } else {
    shownId = null;
  }

  renderLog(closed.slice(-25).reverse());
  tickElapsed();
}

function renderLog(items) {
  el.logWrap.hidden = items.length === 0;
  el.log.innerHTML = '';

  for (const item of items) {
    const li = document.createElement('li');

    const mark = document.createElement('span');
    mark.className = 'mark'; // the tick is drawn in CSS
    mark.setAttribute('aria-hidden', 'true');

    const what = document.createElement('span');
    what.className = 'what';
    what.textContent = item.text;

    const when = document.createElement('span');
    when.className = 'when';
    when.textContent = clockOf(item.completed_at);

    li.append(mark, what, when);
    el.log.appendChild(li);
  }
}

// Time-on-request is the one number worth surfacing live: it is the signal that
// separates "this was hard" from "this was avoided".
function tickElapsed() {
  if (!current) {
    el.elapsed.textContent = '';
    return;
  }
  const started = Date.parse(current.issued_at);
  if (Number.isNaN(started)) {
    el.elapsed.textContent = '';
    return;
  }
  const secs = Math.max(0, Math.round((Date.now() - started) / 1000));
  const mins = Math.floor(secs / 60);
  el.elapsed.textContent =
    mins > 0 ? `${mins}m ${String(secs % 60).padStart(2, '0')}s on this` : `${secs}s on this`;
}

setInterval(tickElapsed, 1000);

// ------------------------------------------------------------------ actions

async function complete() {
  if (inFlight || !current) return;
  inFlight = true;
  el.done.disabled = true;

  const id = current.id;
  // Optimistic: the button must feel instant even on a slow hop.
  current = null;
  el.panelActive.hidden = true;
  el.panelIdle.hidden = false;

  try {
    await fetch(`/api/requests/${id}/complete`, { method: 'POST' });
    await refresh();
  } catch {
    setConn('lost');
  } finally {
    inFlight = false;
    el.done.disabled = false;
  }
}

el.done.addEventListener('click', () => {
  el.done.classList.remove('flash');
  void el.done.offsetWidth; // restart the animation
  el.done.classList.add('flash');
  buzz(28);
  complete();
});

// Space or Enter completes, so the desk-bound case needs no mouse.
document.addEventListener('keydown', (e) => {
  if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
  if ((e.key === ' ' || e.key === 'Enter') && current) {
    e.preventDefault();
    el.done.click();
  }
});

el.logToggle.addEventListener('click', () => {
  el.log.hidden = !el.log.hidden;
});

// ------------------------------------------------------------------ polling

async function refresh() {
  try {
    const res = await fetch('/api/requests', { cache: 'no-store' });
    if (!res.ok) throw new Error(String(res.status));
    render(await res.json());
    setConn('live');
  } catch {
    setConn('lost');
  }
}

refresh();
setInterval(refresh, POLL_MS);
