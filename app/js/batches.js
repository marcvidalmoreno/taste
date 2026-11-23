// Batches view: every folder in generated/codex/, newest first, grouped by day, with what is left to rate.
// On top, "Now and next": the run being made and the queue, so a run started anywhere is never out of sight.
import { api } from './api.js';
import { job, onJob, KIND, runTitle, statusLine, stopButton, queueList, showLog, resumeAll } from './job.js';
import { COST } from './cost.js';
import { h, thumbUrl, batchHref, batchTitle, shortDate, plural, showError, toast } from './ui.js';

// Filters live for the session: coming back from a batch finds the list as it was left.
const KINDS = { all: 'All', batch: 'Batches', derived: 'Variations & remixes', single: 'Single' };
const ui = JSON.parse(sessionStorage.getItem('taste-batches') || '{"kind":"all","q":"","todo":false}');
const saveUi = () => sessionStorage.setItem('taste-batches', JSON.stringify(ui));
const kindGroup = (k) => (k === 'variations' || k === 'remix' ? 'derived' : k === 'single' ? 'single' : 'batch');

let batches = [], view, listEl, nowEl, stoppedEl, unsub;

export async function renderBatches(el) {
  view = el;
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading batches…'));
  try {
    ({ batches } = await api('batches'));
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not load the batches.'));
    return showError(err);
  }
  document.title = 'Batches · taste';
  nowEl = h('section', { class: 'now-next', 'aria-label': 'Now and next', 'aria-live': 'polite' });
  stoppedEl = h('div');
  listEl = h('div');
  const left = batches.reduce((n, b) => n + b.to_rate, 0);
  view.replaceChildren(
    h('header', { class: 'grid-head' },
      h('hgroup', {}, h('h1', {}, 'Batches'), h('p', {}, left ? `${plural(left, 'image')} to rate` : 'Everything is rated')),
      h('a', { href: '#/new', role: 'button', class: 'secondary outline' }, 'New run…')),
    nowEl,
    stoppedEl,
    batches.length ? toolbar() : '',
    listEl);
  drawNow(job);
  drawList();
  drawStopped();
  unsub?.();
  let lastMade = job.made?.length, lastBusy = busyKey(job);
  unsub = onJob((j) => {
    if (!nowEl.isConnected) { unsub(); unsub = null; return; }
    drawNow(j);
    // A run started or ended, or the queue changed: what still waits to be resumed may have changed too.
    if (busyKey(j) !== lastBusy) { lastBusy = busyKey(j); drawStopped(); }
    // A new image or a new batch folder: read the list again so its row and counts are current.
    if (j.made?.length !== lastMade) { lastMade = j.made?.length; api('batches').then((d) => { batches = d.batches; drawList(); }).catch(() => {}); }
  });
}

// ---------------------------------------------------------------- now and next

function drawNow(j) {
  const recent = !j.running && j.finished && Date.now() / 1000 - j.finished < 30 * 60;
  if (!j.running && !j.queue?.length && !recent) { nowEl.hidden = true; return; }
  nowEl.hidden = false;
  const pct = j.expected?.length ? Math.round((100 * j.made.length) / j.expected.length) : 0;
  nowEl.replaceChildren(...[
    j.batch && (j.running || recent) && h('article', { class: 'run-card' + (j.running ? ' is-running' : '') },
      h('div', { class: 'run-main' },
        h('span', { class: 'run-kind' }, j.running ? h('span', { class: 'pulse', 'aria-hidden': 'true' }) : null,
          j.running ? 'Now' : 'Just finished', ' · ', KIND[j.kind]?.label || 'Run'),
        h('strong', {}, runTitle(j)),
        h('span', { class: 'muted small' }, statusLine(j)),
        j.running && j.current?.subject && h('span', { class: 'muted small run-subject' }, `Now: ${j.current.subject}`),
        h('span', { class: 'progress', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': j.expected.length,
          'aria-valuenow': j.made.length, 'aria-label': 'Images made' }, h('i', { style: { width: pct + '%' } }))),
      h('div', { class: 'run-actions' },
        j.exists && h('a', { href: batchHref(j.batch), role: 'button', class: j.running ? 'secondary outline' : '' },
          j.running ? 'Open' : j.made.length ? 'Rate them' : 'Open'),
        h('button', { class: 'secondary outline', onClick: showLog }, 'Log'),
        j.running && stopButton())),
    j.queue?.length > 0 && queueList(j.queue)].filter(Boolean));
}

// ---------------------------------------------------------------- runs the usage limit cut short
// When Codex hits its usage limit mid-queue, every run after it stops with nothing or half made. Once the
// limit resets, one calm line and one button queue them all again (23 Nov 2026). Images blocked by the
// filter are not counted: they would only fail again.

const busyKey = (j) => `${j.running ? j.batch : ''}|${(j.queue || []).map((q) => q.id).join(',')}`;

async function drawStopped() {
  let d;
  try { d = await api('stopped'); } catch { return; }
  if (!stoppedEl?.isConnected) return;
  if (!d.images) { stoppedEl.replaceChildren(); return; }
  const n = d.images;
  stoppedEl.replaceChildren(h('section', { class: 'finish-bar' },
    h('p', {},
      h('strong', {}, `${plural(d.runs.length, 'run')} stopped when Codex hit its usage limit.`),
      ` ${plural(n, 'image')} never made.`, h('br'),
      h('span', { class: 'muted small' }, `Same prompts and folders as before · about ${n * COST.minutes} min · ≈ `
        + `${(n * COST.fiveLow).toFixed(0)}–${(n * COST.fiveHigh).toFixed(0)} % of the five-hour window`)),
    h('button', { class: 'small-btn', onClick: (e) => resume(e.currentTarget) }, `Resume all (${plural(n, 'image')})`)));
}

async function resume(btn) {
  btn.disabled = true;
  btn.setAttribute('aria-busy', 'true');
  try {
    const res = await resumeAll();
    toast(`${plural(res.runs, 'run')} queued again, ${plural(res.images, 'image')}`);
    drawStopped();
  } catch (err) {
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    showError(err);
  }
}

// ---------------------------------------------------------------- list

function toolbar() {
  const counts = { all: batches.length, batch: 0, derived: 0, single: 0 };
  for (const b of batches) counts[kindGroup(b.kind)]++;
  return h('div', { class: 'gallery-filters batch-tools' },
    h('input', { type: 'search', placeholder: 'Find a batch, style or subject', value: ui.q, 'aria-label': 'Find a batch',
      onInput: (e) => { ui.q = e.target.value; saveUi(); drawList(); } }),
    h('div', { class: 'rseg', role: 'group', 'aria-label': 'Kind' },
      Object.entries(KINDS).filter(([k]) => k === 'all' || counts[k]).map(([k, label]) => h('button', {
        class: 'rseg-btn', 'aria-pressed': String(ui.kind === k),
        onClick: (e) => { ui.kind = k; saveUi(); e.currentTarget.parentNode.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget))); drawList(); } },
      label, ' ', h('small', {}, counts[k])))),
    h('label', { class: 'nr-check' }, h('input', { type: 'checkbox', checked: ui.todo, onChange: (e) => { ui.todo = e.target.checked; saveUi(); drawList(); } }),
      h('span', {}, 'Only with images to rate')));
}

function drawList() {
  if (!batches.length) {
    listEl.replaceChildren(h('section', { class: 'empty' },
      h('h2', {}, 'No batches yet'),
      h('p', {}, 'Start one with New run. Images land in generated/codex/ and show up here.')));
    return;
  }
  const q = ui.q.trim().toLowerCase();
  const shown = batches.filter((b) => (ui.kind === 'all' || kindGroup(b.kind) === ui.kind) && (!ui.todo || b.to_rate > 0)
    && (!q || [b.batch, b.title, ...(b.styles || [])].join(' ').toLowerCase().replace(/-/g, ' ').includes(q.replace(/-/g, ' '))));
  if (!shown.length) {
    listEl.replaceChildren(h('p', { class: 'empty-filter' }, 'No batch matches. ',
      h('button', { class: 'ghost', onClick: () => { ui.q = ''; ui.kind = 'all'; ui.todo = false; saveUi(); renderBatches(view); } }, 'Show all')));
    return;
  }
  const days = new Map();
  for (const b of shown) {
    const d = dayOf(b);
    if (!days.has(d)) days.set(d, []);
    days.get(d).push(b);
  }
  listEl.replaceChildren(...[...days].map(([d, list]) => h('section', { class: 'day' },
    h('h2', { class: 'day-head' }, dayLabel(d), ' ', h('small', { class: 'muted' }, plural(list.length, 'batch', 'batches'))),
    h('ul', { class: 'batch-list' }, list.map(batchRow)))));
}

const iso = (t) => { const d = new Date(t * 1000); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const dayOf = (b) => iso(b.newest);
function dayLabel(d) {
  const today = iso(Date.now() / 1000), yesterday = iso(Date.now() / 1000 - 86400);
  if (d === today) return 'Today';
  if (d === yesterday) return 'Yesterday';
  return new Date(d + 'T12:00').toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short' });
}

function batchRow(b) {
  const done = b.to_rate === 0;
  const making = job.running && job.batch === b.batch;
  // One link per row: the whole row is the target (Fitts), and Tab stops once per batch.
  return h('li', {},
    h('a', { href: batchHref(b.batch), class: 'batch-row' + (done && !making ? ' is-done' : '') },
      h('div', { class: 'strip', 'aria-hidden': 'true' },
        b.preview.map((f) => h('img', { src: thumbUrl(b.batch, f, b.newest), alt: '', loading: 'lazy' }))),
      h('div', { class: 'batch-text' },
        h('strong', {}, b.title || batchTitle(b.batch)),
        h('small', {}, [KIND[b.kind]?.label || b.kind, shortDate(b.date), plural(b.images, 'image'),
          b.styles?.length > 2 ? plural(b.styles.length, 'style') : b.styles?.join(', ')].filter(Boolean).join(' · '))),
      h('div', { class: 'batch-counts' },
        making ? h('span', { class: 'count todo' }, 'making now')
          : done ? h('span', { class: 'count muted' }, b.images ? 'rated' : 'empty')
          : h('span', { class: 'count todo' }, `${b.to_rate} to rate`),
        b.drafts > 0 && h('span', { class: 'count draft' }, `${b.drafts} not saved`),
        b.ignored > 0 && h('span', { class: 'count muted' }, `${b.ignored} ignored`))));
}
