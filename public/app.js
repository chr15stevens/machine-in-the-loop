'use strict';

/**
 * The subject client. One job: show the oldest open request, and let the human
 * press one button to close it.
 *
 * It polls. Against an in-memory store on the same machine, a 1s poll is
 * indistinguishable from a push and costs a fraction of the machinery.
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
  alertHint: $('alert-hint'),
};

const POLL_MS = 1000;
const BASE_TITLE = 'Machine in the loop';

let current = null; // the request on screen
let shownId = null; // last id we alerted for
let inFlight = false;
let ready = false; // suppresses the alert for whatever is already open at load

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

// ------------------------------------------------------------------ alerting
//
// Everything here is on-device: a chime, a vibration if the hardware has one,
// a desktop notification, and the tab title. Nothing is sent anywhere. Served
// on localhost the page is a secure context, so the Notification API is
// available; it degrades to sound and the title if that ever changes.

let audio = null;

function audioReady() {
  return audio && audio.state === 'running';
}

// Browsers refuse to make noise until the user has interacted with the page,
// so the first alert can only be armed, not fired.
function armAudio() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    if (audio.state === 'suspended') audio.resume();
  } catch {
    audio = null;
  }
  el.alertHint.hidden = audioReady() || audio === null;
}

function beep() {
  if (!audioReady()) return;
  // Two short rising notes: audible across a room, unlike a single blip, and
  // over in 260ms so it never becomes something to resent.
  const now = audio.currentTime;
  for (const [at, freq] of [[0, 660], [0.13, 880]]) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, now + at);
    gain.gain.exponentialRampToValueAtTime(0.22, now + at + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.12);
    osc.connect(gain).connect(audio.destination);
    osc.start(now + at);
    osc.stop(now + at + 0.13);
  }
}

function canNotify() {
  return window.isSecureContext && 'Notification' in window && Notification.permission === 'granted';
}

function askToNotify() {
  if (!window.isSecureContext || !('Notification' in window)) return;
  if (Notification.permission === 'default') Notification.requestPermission();
}

function alertHuman(request) {
  buzz([14, 60, 14]);
  beep();
  if (canNotify() && document.hidden) {
    new Notification(BASE_TITLE, { body: request.text, tag: 'machine-in-the-loop-request', renotify: true });
  }
  if (document.hidden) document.title = `● ${request.text}`;
}

// Any interaction is consent enough to make noise later.
for (const evt of ['pointerdown', 'keydown']) {
  document.addEventListener(evt, () => {
    armAudio();
    askToNotify();
  }, { once: true });
}

el.alertHint.addEventListener('click', armAudio);

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) document.title = BASE_TITLE;
});

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
      // Don't alert for whatever was already open when the page loaded — you
      // are looking at it.
      if (ready) alertHuman(current);
      shownId = current.id;
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
  ready = true;
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

// Surfaces the "tap to enable alerts" hint if the browser will not let us make
// noise yet. Harmless when it will.
armAudio();

refresh();
setInterval(refresh, POLL_MS);
