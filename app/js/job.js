// Runs: what is being made now, what waits in the queue, and telling Marc when it's done.
// The server (scripts/app.py) keeps one queue and runs one image run at a time: batches, single images,
// remixes, retries and variations started here, plus batch.py / variations.py runs started from chat
// (read from generated/codex/.progress.json). While a run goes, the page asks every 3 s how far it is and
// shows it in the header (visible from any page), in the tab title and on the Batches page.
import { api } from './api.js';
import { store, changed } from './store.js';
import { h, batchHref, batchTitle, plural, toast, showError } from './ui.js';

export let job = { running: false, queue: [] };
let timer;
let seen = -1;             // images made at the last look
let settle = 0;            // polls left that should re-read the open batch
let followId = null;       // the run Marc just started: when its folder appears and he is still where he was, go there
let followHash = null;
const mine = new Set();    // runs started from this page (ids): report their end
let reportFor = null;      // a run from chat seen running here (by start time): report its end too
let lastReported = null;  // the run from chat already reported (by start time)
let logBox = null;         // the open log dialog's parts, refreshed on every poll
const subs = new Set();    // views that redraw on every poll (the Batches page's "Now and next")
export const onJob = (fn) => { subs.add(fn); return () => subs.delete(fn); };

// Plain words for each kind of run.
export const KIND = {
  batch: { label: 'Batch', noun: 'image' },
  single: { label: 'Single image', noun: 'image' },
  remix: { label: 'Remix', noun: 'remix', nounMany: 'remixes' },
  retry: { label: 'Retry', noun: 'image' },
  variations: { label: 'Variations', noun: 'variation' },
  list: { label: 'Run', noun: 'image' },
};
const noun = (k, n) => plural(n, KIND[k]?.noun || 'image', KIND[k]?.nounMany);
export const runTitle = (r) => (r.from_chat ? `${r.kind === 'variations' ? 'Variations' : 'Batch'} started from chat` : r.title)
  || batchTitle(r.batch || '');
export const clock = (secs) => { const s = Math.max(0, Math.round(secs)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };

// Queue a run. body: {kind, ...}; go: a page to show right away (the Batches page, where the run is listed).
// Returns the server's answer (position 1 = starts now). If it starts now and Marc stays on that page, the
// page moves on to the new batch as soon as its folder exists, where the placeholders fill in.
export async function enqueueRun(body, { go } = {}) {
  askToNotify();
  const res = await api(body.kind === 'variations' ? 'variations' : 'run', { method: 'POST', body });
  mine.add(res.queued_id);
  if (go && location.hash !== go) location.hash = go;
  if (res.position <= 1) { followId = res.queued_id; followHash = location.hash; }
  job = res;
  seen = -1;
  poll();
  return res;
}

export async function stopRun() {
  try { job = await api('stop', { method: 'POST', body: {} }); poll(); } catch (err) { showError(err); }
}

export async function cancelQueued(id, title) {
  try {
    job = await api('queue/cancel', { method: 'POST', body: { id } });
    mine.delete(id);
    toast(`Removed from the queue: ${title}`);
    poll();
  } catch (err) { showError(err); }
}

// Ask once, at the moment it makes sense (Marc just started a run), never on page load.
function askToNotify() {
  if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => {});
}

export async function poll() {
  clearTimeout(timer);
  const wasRunning = job.running;
  try {
    job = await api('job');
  } catch {
    job = { running: false, queue: [] };
  }
  job.queue ||= [];
  if (job.running && job.from_chat && reportFor === null) reportFor = job.started;
  drawChip();
  drawLog();
  drawTitle();
  if (job.batch) {
    if (followId && job.id === followId && job.exists) {
      if (location.hash === followHash) location.hash = batchHref(job.batch);
      followId = null;
    }
    // An image file lands a few seconds before codex_run.py writes its runs.csv row (style, prompt):
    // read the batch again on the next two polls too, and once more when the run ends.
    if (job.made.length !== seen || (wasRunning && !job.running)) settle = 3;
    if (settle > 0 && store.data?.batch === job.batch) changed(null, 'reload');
    settle = Math.max(0, settle - 1);
    seen = job.made.length;
    changed(null, 'job');
  }
  subs.forEach((fn) => fn(job));
  // Every 3 s while a run goes (or waits), every 10 s otherwise: a run started from chat shows up without a reload.
  timer = setTimeout(poll, job.running || job.queue.length ? 3000 : 10000);
  // Runs started here: the server keeps the last finished ones, so each is reported even if the next queued
  // run (or a run from chat) took over the header before this page looked.
  for (const r of job.recent || []) if (mine.has(r.id)) { mine.delete(r.id); report(r); }
  // A run from chat seen running here: report its end too.
  if (job.from_chat && !job.running && job.finished && reportFor === job.started && lastReported !== job.started) {
    lastReported = job.started;
    reportFor = null;
    report(job);
  }
}

function report(job) {
  const made = job.made.length, total = job.expected.length, missing = total - made;
  const title = runTitle(job);
  const open = () => { location.hash = batchHref(job.batch); };
  let text;
  if (job.dry_run) {
    text = `Dry run finished: ${title}. Nothing made, nothing spent.`;
    toast(text, { action: 'What it would do', onAction: () => showLog(job), timeout: 10000 });
  } else if (job.error) {
    text = `${title} could not start: ${job.error}`;
    toast(text, { action: 'Details', onAction: () => showLog(job), tone: 'error', timeout: 0 });
  } else if (job.stopped) {
    text = `${title} stopped: ${made} of ${total} made.`;
    toast(text, { action: made ? 'See them' : 'Details', onAction: made ? open : () => showLog(job), timeout: 0 });
  } else if (!missing) {
    text = `${noun(job.kind, made)} ready: ${title}`;
    toast(text, { action: 'Rate them', onAction: open, timeout: 12000 });
  } else {
    text = `${title}: ${made} of ${total} made, ${missing} failed. The run stopped as the repo rules say.`;
    toast(text, { action: 'See them', onAction: open, tone: 'error', timeout: 0 });
  }
  // Marc is in another window or tab: a desktop notification, and a mark in the tab title until he's back.
  if (document.hidden || !document.hasFocus()) {
    if ('Notification' in window && Notification.permission === 'granted' && !job.dry_run) {
      const n = new Notification('taste', { body: text, tag: 'taste-run' });
      n.onclick = () => { window.focus(); open(); n.close(); };
    }
    doneMark = job.error || job.stopped || missing ? '! ' : '✓ ';
    drawTitle();
  }
}

// ---------------------------------------------------------------- tab title
// Views set document.title; this keeps a short prefix in front of it: "3/8 · " while a run goes, "✓ " when
// one ended while Marc was away (cleared when he comes back).
let doneMark = '';
let prefix = '';
const titleEl = document.querySelector('title');
new MutationObserver(() => {
  if (prefix && !document.title.startsWith(prefix)) { const t = document.title; prefix = ''; document.title = t; drawTitle(); }
}).observe(titleEl, { childList: true });
document.addEventListener('visibilitychange', () => { if (!document.hidden) { doneMark = ''; drawTitle(); } });
window.addEventListener('focus', () => { doneMark = ''; drawTitle(); });

function drawTitle() {
  const base = prefix && document.title.startsWith(prefix) ? document.title.slice(prefix.length) : document.title;
  const p = job.running && !job.dry_run && job.expected?.length ? `${job.made.length}/${job.expected.length} · ` : doneMark;
  if (p === prefix && document.title === prefix + base) return;
  prefix = p;
  document.title = p + base;
}

// ---------------------------------------------------------------- log dialog

// The live log of the current run, and the queue. With a finished run (from a "Details" button), that run's
// own last lines instead, unless it is still the current one.
export function showLog(r = null) {
  const pre = h('pre', { class: 'log' });
  const head = h('div', { class: 'log-head' });
  const queue = h('div');
  const dlg = h('dialog', { class: 'review log-dialog' }, h('article', {},
    h('header', {}, head),
    pre, queue,
    h('footer', {}, h('button', { onClick: () => dlg.close() }, 'Close'))));
  logBox = { pre, head, queue, fixed: r?.id && r.id !== job.id ? r : null };
  dlg.addEventListener('close', () => { dlg.remove(); logBox = null; });
  document.body.append(dlg);
  drawLog();
  dlg.showModal();
}

function drawLog() {
  if (!logBox) return;
  const { pre, head, queue, fixed } = logBox;
  const r = fixed || job;
  head.replaceChildren(...[
    h('hgroup', {}, h('h3', {}, r.batch ? runTitle(r) : 'Nothing running'),
      h('p', { class: 'muted small' }, r.batch ? statusLine(r) : 'Runs you start show their progress here.')),
    !fixed && r.running && stopButton()].filter(Boolean));
  const atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
  const lines = [...(r.log || [])];
  if (r.running && r.current) lines.push(`          … ${r.current.name}, ${clock(Date.now() / 1000 - r.current.since)} so far`);
  pre.textContent = lines.join('\n') || '(no output yet)';
  if (atEnd) pre.scrollTop = pre.scrollHeight;
  queue.replaceChildren(!fixed && job.queue.length ? queueList(job.queue) : '');
}

export function statusLine(r) {
  if (r.running) {
    if (r.phase && r.phase !== 'Making images') return `${r.phase}…`;
    const doing = Math.min(r.made.length + 1, r.expected.length);
    return `Making ${doing} of ${r.expected.length}` + (r.failed?.length ? ` · ${r.failed.length} failed` : '')
      + ` · ${clock(Date.now() / 1000 - r.started)}` + (r.dry_run ? ' · dry run' : '');
  }
  if (r.dry_run) return 'Dry run finished: nothing made, nothing spent';
  if (r.error) return `Could not start: ${r.error}`;
  const missing = r.expected.length - r.made.length;
  return (r.stopped ? 'Stopped · ' : 'Finished · ') + `${r.made.length} of ${r.expected.length} made`
    + (missing && !r.stopped ? ` · ${missing} failed` : '');
}

// Stopping loses the image being made: say so in the confirmation, keep the default on "Keep going".
export function stopButton() {
  return h('button', { class: 'secondary outline small-btn', onClick: () => {
    const what = job.from_chat ? 'This run was started from chat. ' : '';
    if (confirm(`${what}Stop "${runTitle(job)}"?\n\nThe image being made now is lost; the ${job.made.length} already made stay.`)) stopRun();
  } }, 'Stop');
}

export function queueList(queue) {
  return h('section', { class: 'queue' },
    h('h4', {}, `Next (${queue.length})`),
    h('ol', {}, queue.map((q) => h('li', {},
      h('span', {}, h('strong', {}, q.title), ' ', h('span', { class: 'muted small' }, `${KIND[q.kind]?.label || q.kind} · ${noun(q.kind, q.expected.length)}`)),
      h('button', { class: 'ghost small', onClick: () => cancelQueued(q.id, q.title), 'aria-label': `Remove ${q.title} from the queue` }, 'Remove')))));
}

// ---------------------------------------------------------------- header chip

function drawChip() {
  const chip = document.getElementById('job-chip');
  if (!job.running && !job.queue.length) { chip.hidden = true; return; }
  chip.hidden = false;
  // Built once, then only the text changes: the Log button stays put for clicks and keyboard focus.
  if (!chip.querySelector('.chip-log')) {
    chip.replaceChildren(h('span', { class: 'job-chip' },
      h('a', {}, h('span', { class: 'pulse', 'aria-hidden': 'true' }), h('span', { class: 'label' })),
      h('button', { class: 'chip-log', onClick: showLog, title: 'The live log of this run, and the queue' }, 'Log')));
  }
  const link = chip.querySelector('.job-chip > a');
  const queued = job.queue.length ? ` · +${job.queue.length} queued` : '';
  if (job.running) {
    const doing = Math.min(job.made.length + 1, job.expected.length);
    const now = job.current?.name && job.expected.length > 1 ? ` · ${job.current.name}` : '';
    const failed = job.failed?.length ? ` · ${job.failed.length} failed` : '';
    const busy = job.phase && job.phase !== 'Making images';
    link.href = job.exists ? batchHref(job.batch) : '#/';
    link.title = runTitle(job) + (job.current?.subject ? `\nNow: ${job.current.subject}` : '');
    link.querySelector('.label').replaceChildren(
      job.dry_run ? 'Dry run…' : busy ? 'Writing subjects…' : `Making ${doing} of ${job.expected.length}`,
      h('span', { class: 'muted' }, `${busy ? '' : now}${failed} · ${clock(Date.now() / 1000 - job.started)}${queued}`));
  } else {
    link.href = '#/';
    link.title = 'Waiting to start';
    link.querySelector('.label').replaceChildren(`${plural(job.queue.length, 'run')} waiting`,
      h('span', { class: 'muted' }, ' · starting…'));
  }
}

// A run may already be going when the page opens (reload, second tab, a run started from chat): pick it up.
poll();
