// The one variation job. While it runs, the page asks the server every 3 s how far it is, shows that in
// the header (visible from any page), and tells the open batch when a new image has landed.
import { api } from './api.js';
import { store, changed } from './store.js';
import { h, batchHref, batchTitle, plural, toast } from './ui.js';

export let job = { running: false };
let timer;
let seen = -1;             // images made at the last look
let settle = 0;            // polls left that should re-read the open batch
let followHash = null;     // where Marc was when he started: if he is still there, take him to the new batch
let reportFor = null;      // the job (by start time) whose end this page should report

export async function startJob(body) {
  job = await api('variations', { method: 'POST', body });
  followHash = location.hash;
  reportFor = job.started;
  seen = -1;
  return poll();
}

export async function poll() {
  clearTimeout(timer);
  try {
    job = await api('job');
  } catch {
    job = { running: false };
  }
  drawChip();
  if (job.batch) {
    if (job.exists && followHash !== null && location.hash === followHash) {
      followHash = null;
      location.hash = batchHref(job.batch);
    }
    // An image file lands a few seconds before codex_run.py writes its runs.csv row (style, prompt):
    // read the batch again on the next two polls too, and once more when the job ends.
    if (job.made.length !== seen || !job.running) settle = 3;
    if (settle > 0 && store.data?.batch === job.batch) changed(null, 'reload');
    settle = Math.max(0, settle - 1);
    seen = job.made.length;
    changed(null, 'job');
  }
  if (job.running) timer = setTimeout(poll, 3000);
  else if (job.finished && reportFor === job.started) report();
}

function report() {
  reportFor = null;
  followHash = null;
  const missing = job.expected.length - job.made.length;
  if (job.dry_run) {
    toast('Dry run finished: nothing made, nothing spent', { action: 'What it would do', onAction: showLog, timeout: 10000 });
  } else if (!missing) {
    toast(`${plural(job.made.length, 'variation')} ready`, { action: 'Rate them',
      onAction: () => { location.hash = batchHref(job.batch); }, timeout: 10000 });
  } else {
    toast(`${job.made.length} of ${job.expected.length} made, ${missing} failed. variations.py stopped as the repo rules say.`,
      { action: 'Details', onAction: showLog, tone: 'error', timeout: 0 });
  }
}

function showLog() {
  const dlg = h('dialog', { class: 'review' }, h('article', {},
    h('header', {}, h('h3', {}, job.dry_run ? 'Dry run: what variations.py would do' : 'variations.py output')),
    h('pre', { class: 'log' }, job.log.join('\n') || '(no output)'),
    h('footer', {}, h('button', { onClick: () => dlg.close() }, 'Close'))));
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
}

function drawChip() {
  const chip = document.getElementById('job-chip');
  if (!job.running) { chip.hidden = true; return; }
  const secs = Math.round(Date.now() / 1000 - job.started);
  const doing = Math.min(job.made.length + 1, job.expected.length);
  chip.hidden = false;
  chip.replaceChildren(h('a', { href: batchHref(job.batch), class: 'job-chip',
    title: `Variations of ${job.source.file} into ${batchTitle(job.batch)}` },
    h('span', { class: 'pulse', 'aria-hidden': 'true' }),
    job.dry_run ? 'Dry run…' : `Making ${doing} of ${job.expected.length}`,
    h('span', { class: 'muted' }, ` · ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`)));
}

// A job may already be running when the page opens (reload, second tab): pick it up, don't report old ones.
poll();
