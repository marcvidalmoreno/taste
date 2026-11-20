// The one image run: variations started from this page, or a batch.py / variations.py / codex_run.py run
// started from chat (the server reads its generated/codex/.progress.json). While it runs, the page asks
// the server every 3 s how far it is, shows that in the header (visible from any page) with a live log,
// and tells the open batch when a new image has landed.
import { api } from './api.js';
import { store, changed } from './store.js';
import { h, batchHref, batchTitle, plural, toast } from './ui.js';

export let job = { running: false };
let timer;
let seen = -1;             // images made at the last look
let settle = 0;            // polls left that should re-read the open batch
let followHash = null;     // where Marc was when he started: if he is still there, take him to the new batch
let reportFor = null;      // the job (by start time) whose end this page should report
let logPre = null;         // the open log dialog's <pre>, refreshed on every poll

export async function startJob(body) {
  job = await api('variations', { method: 'POST', body });
  followHash = location.hash;
  reportFor = job.started;
  seen = -1;
  return poll();
}

export async function poll() {
  clearTimeout(timer);
  const wasRunning = job.running;
  try {
    job = await api('job');
  } catch {
    job = { running: false };
  }
  if (job.running && reportFor === null) reportFor = job.started;  // seen running here: report its end
  drawChip();
  drawLog();
  if (job.batch) {
    if (job.exists && followHash !== null && location.hash === followHash) {
      followHash = null;
      location.hash = batchHref(job.batch);
    }
    // An image file lands a few seconds before codex_run.py writes its runs.csv row (style, prompt):
    // read the batch again on the next two polls too, and once more when the job ends.
    if (job.made.length !== seen || (wasRunning && !job.running)) settle = 3;
    if (settle > 0 && store.data?.batch === job.batch) changed(null, 'reload');
    settle = Math.max(0, settle - 1);
    seen = job.made.length;
    changed(null, 'job');
  }
  // Every 3 s while a run goes, every 10 s otherwise: a run started from chat shows up without a reload.
  timer = setTimeout(poll, job.running ? 3000 : 10000);
  if (!job.running && job.finished && reportFor === job.started) report();
}

const noun = () => (job.kind === 'variations' ? 'variation' : 'image');
const script = () => ({ batch: 'batch.py', variations: 'variations.py' }[job.kind] || 'codex_run.py');
const clock = (secs) => { const s = Math.max(0, Math.round(secs)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };

function report() {
  reportFor = null;
  followHash = null;
  const missing = job.expected.length - job.made.length;
  if (job.dry_run) {
    toast('Dry run finished: nothing made, nothing spent', { action: 'What it would do', onAction: showLog, timeout: 10000 });
  } else if (job.stopped) {
    toast(`${script()} stopped before the end: ${job.made.length} of ${job.expected.length} made`,
      { action: 'Details', onAction: showLog, tone: 'error', timeout: 0 });
  } else if (!missing) {
    toast(`${plural(job.made.length, noun())} ready`, { action: 'Rate them',
      onAction: () => { location.hash = batchHref(job.batch); }, timeout: 10000 });
  } else {
    toast(`${job.made.length} of ${job.expected.length} made, ${missing} failed. ${script()} stopped as the repo rules say.`,
      { action: 'Details', onAction: showLog, tone: 'error', timeout: 0 });
  }
}

function showLog() {
  logPre = h('pre', { class: 'log' });
  const dlg = h('dialog', { class: 'review' }, h('article', {},
    h('header', {}, h('h3', {}, job.dry_run ? `Dry run: what ${script()} would do` : `${script()}: what is going on`)),
    logPre,
    h('footer', {}, h('button', { onClick: () => dlg.close() }, 'Close'))));
  dlg.addEventListener('close', () => { dlg.remove(); logPre = null; });
  document.body.append(dlg);
  drawLog();
  dlg.showModal();
}

function drawLog() {
  if (!logPre) return;
  const atEnd = logPre.scrollTop + logPre.clientHeight >= logPre.scrollHeight - 8;
  const lines = [...(job.log || [])];
  if (job.running && job.current) lines.push(`          … ${job.current.name}, ${clock(Date.now() / 1000 - job.current.since)} so far`);
  logPre.textContent = lines.join('\n') || '(no output yet)';
  if (atEnd) logPre.scrollTop = logPre.scrollHeight;
}

function drawChip() {
  const chip = document.getElementById('job-chip');
  if (!job.running) { chip.hidden = true; return; }
  const doing = Math.min(job.made.length + 1, job.expected.length);
  const now = job.current?.name && job.expected.length > 1 ? ` · ${job.current.name}` : '';
  const failed = job.failed?.length ? ` · ${job.failed.length} failed` : '';
  const title = job.kind === 'variations' && job.source
    ? `Variations of ${job.source.file} into ${batchTitle(job.batch)}`
    : `${script()} into ${batchTitle(job.batch)}` + (job.current?.subject ? `\nNow: ${job.current.subject}` : '');
  chip.hidden = false;
  // Built once, then only the link changes: the Log button stays put for clicks and keyboard focus.
  if (!chip.querySelector('.chip-log')) {
    chip.replaceChildren(h('span', { class: 'job-chip' },
      h('a', {}, h('span', { class: 'pulse', 'aria-hidden': 'true' }), h('span', { class: 'label' })),
      h('button', { class: 'chip-log', onClick: showLog, title: 'What is going on: the live log of this run' }, 'Log')));
  }
  const link = chip.querySelector('.job-chip > a');
  link.href = batchHref(job.batch);
  link.title = title;
  link.querySelector('.label').replaceChildren(job.dry_run ? 'Dry run…' : `Making ${doing} of ${job.expected.length}`,
    h('span', { class: 'muted' }, `${now}${failed} · ${clock(Date.now() / 1000 - job.started)}`));
}

// A job may already be running when the page opens (reload, second tab, a run started from chat): pick it up.
poll();
