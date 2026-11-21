// Distil: turn the ratings since the last distil into written style edits, style by style (21 Nov 2026).
//   #/distil
// One button asks Codex about every style with enough new ratings (3 at a time, ~10-30 s each, medium reasoning).
// Each style's card shows the images rated (ups and downs, with the why), Codex's reading, and its proposed edit
// field by field; untick what you don't want, Apply or Skip. Nothing changes until Apply; each apply can be undone.
// When done, "Mark the distil done" starts the next round after these ratings. The leaning (thumbs re-weighting
// options) runs on its own; this is where new words enter a style.
import { api, styles, refreshStyles } from './api.js';
import { FIELDS, diffValue, undoEdit } from './styleedit.js';
import { h, thumbUrl, batchHref, shortDate, plural, toast, showError } from './ui.js';

const STATUS = { waiting: 'Waiting', thinking: 'Codex is reading…', ready: 'Proposal ready', nothing: 'No change needed',
  applied: 'Applied', skipped: 'Skipped', failed: 'Failed' };
let view, timer, state, all, skip = {};

export async function renderDistil(el) {
  view = el;
  clearTimeout(timer);
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Reading the ratings…'));
  document.title = 'Distil · taste';
  try {
    [state, all] = await Promise.all([api('distil/state'), styles()]);
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not read the ratings.'));
    return showError(err);
  }
  draw();
}

async function refresh() {
  clearTimeout(timer);
  if (!view?.isConnected || !view.querySelector('.distil-page')) return;
  try { state = await api('distil/state'); } catch { /* keep the last view */ }
  draw();
}

function draw() {
  const run = state.run;
  const cards = run ? Object.entries(run.styles) : [];
  const asked = new Set(cards.map(([k]) => k));
  const eligible = Object.entries(state.since).filter(([, d]) => d.n >= state.min).sort((a, b) => b[1].n - a[1].n);
  const few = Object.entries(state.since).filter(([k, d]) => d.n < state.min && !asked.has(k));
  const open = cards.filter(([, c]) => ['ready', 'nothing', 'failed'].includes(c.status)).length;
  const busy = run?.running;
  const doneN = cards.filter(([, c]) => c.status !== 'waiting' && c.status !== 'thinking').length;
  // focus survives a redraw (polling every 2 s while Codex works)
  const focusKey = document.activeElement?.dataset?.focus;

  view.replaceChildren(h('div', { class: 'distil-page' },
    h('header', { class: 'grid-head' },
      h('hgroup', {}, h('h1', {}, 'Distil'),
        h('p', {}, state.total ? `${plural(state.total, 'rating')} since the last distil${state.marked ? ` (${shortDate(state.marked)})` : ''}`
          + (state.total >= state.due ? ' · due' : ` · due at ${state.due}`) : 'No ratings since the last distil.')),
      !run && eligible.length > 0 && h('button', { onClick: ask, 'data-focus': 'ask' }, `Ask Codex about ${plural(eligible.length, 'style')}`)),
    !run && h('p', { class: 'muted lead-note' },
      eligible.length ? `Codex reads the ratings of each style with ${state.min} or more new ones and proposes edits to its words: what the ups share goes into the style, what the downs share goes out. About ${Math.max(1, Math.ceil(eligible.length / 3) * 0.4).toFixed(0)}–${Math.ceil(eligible.length / 3)} min, a small share of the Codex allowance. Nothing changes until you apply.`
        : `No style has ${state.min} or more ratings since the last distil yet.`),
    state.dry_run && h('p', { class: 'notice' }, 'Dry run: Codex is not asked; each proposal is a stand-in line.'),
    busy && h('p', { class: 'distil-progress', 'aria-live': 'polite' }, h('span', { class: 'pulse', 'aria-hidden': 'true' }),
      ` Codex has read ${doneN} of ${cards.length} styles. Cards fill in as answers arrive; you can start reviewing now.`),
    run && h('div', { class: 'distil-cards' }, cards.sort((a, b) => b[1].n - a[1].n).map(([k, c]) => card(k, c))),
    !run && eligible.length > 0 && h('ul', { class: 'plain distil-preview' }, eligible.map(([k, d]) => h('li', {},
      h('strong', {}, all[k]?.name || k), h('span', { class: 'muted small' }, ` · 👍 ${d.up} · 👎 ${d.down}`)))),
    few.length > 0 && h('p', { class: 'muted small' }, `Too few new ratings to say anything yet: `,
      few.map(([k, d]) => `${all[k]?.name || k} (${d.n})`).join(', '), '.'),
    state.total > 0 && h('footer', { class: 'distil-foot' },
      h('span', {}, open ? `${plural(open, 'proposal')} still to decide.` : run ? 'Every proposal decided.' : '',
        h('span', { class: 'muted' }, ` Marking the distil done starts the next one after these ${plural(state.total, 'rating')}.`)),
      h('button', { class: run && !open && !busy ? '' : 'secondary outline', disabled: busy, onClick: mark, 'data-focus': 'mark' }, 'Mark the distil done'))));
  if (focusKey) view.querySelector(`[data-focus="${CSS.escape(focusKey)}"]`)?.focus();
  if (busy) timer = setTimeout(refresh, 2000);
}

function card(k, c) {
  const s = all[k] || { name: k, palette: [] };
  const imgs = (state.since[k]?.images || []).slice().sort((a, b) => (a.rating === b.rating ? 0 : a.rating === 'keep' ? -1 : 1));
  const decided = c.status === 'applied' || c.status === 'skipped';
  const fields = c.changes ? Object.entries(c.changes) : [];
  const off = skip[k] ||= new Set();
  return h('article', { class: `card distil-card is-${c.status}` },
    h('header', { class: 'distil-card-head' },
      h('h2', {}, s.name),
      h('span', { class: 'swatches', 'aria-hidden': 'true' }, (s.palette || []).slice(0, 5).map((x) => h('i', { style: { background: x } }))),
      h('span', { class: 'muted small' }, `👍 ${c.up} · 👎 ${c.down}`),
      h('span', { class: `status-pill ${c.status}` }, c.status === 'thinking' ? h('span', { 'aria-busy': 'true' }, STATUS.thinking) : STATUS[c.status])),
    imgs.length > 0 && h('ul', { class: 'distil-imgs' }, imgs.slice(0, 12).map((im) => h('li', {},
      h('a', { href: `#/b/${encodeURIComponent(im.batch)}/${encodeURIComponent(im.name)}`, title: (im.rating === 'keep' ? 'Up' : 'Down') + (im.why ? `: ${im.why}` : '') },
        h('img', { src: thumbUrl(im.batch, im.name + '.png'), alt: '', loading: 'lazy' }),
        h('span', { class: `mark ${im.rating} saved`, 'aria-hidden': 'true' }, im.rating === 'keep' ? '👍' : '👎')),
      im.why && h('small', {}, im.why)))),
    c.summary && h('p', { class: 'remix-summary' }, h('strong', {}, 'Codex: '), c.summary),
    c.status === 'failed' && h('p', { class: 'small' }, `Codex could not answer: ${c.error}`),
    !decided && fields.length > 0 && fields.map(([f, v]) => h('section', { class: 'field-diff' + (off.has(f) ? ' is-off' : '') },
      h('div', { class: 'field-head' }, h('label', { class: 'nr-check' },
        h('input', { type: 'checkbox', checked: !off.has(f), 'data-focus': `${k}-${f}`,
          onChange: (e) => { e.target.checked ? off.delete(f) : off.add(f); draw(); } }),
        h('strong', {}, FIELDS[f] || f))),
      diffValue(c.before?.[f], v))),
    h('div', { class: 'distil-actions' },
      c.status === 'ready' && h('button', { class: 'small-btn', 'data-focus': `${k}-apply`, disabled: fields.every(([f]) => off.has(f)),
        onClick: () => decide(k, 'apply', Object.fromEntries(fields.filter(([f]) => !off.has(f)))) }, 'Apply to the style'),
      ['ready', 'nothing', 'failed'].includes(c.status) && h('button', { class: 'secondary outline small-btn', 'data-focus': `${k}-skip`,
        onClick: () => decide(k, 'skip') }, c.status === 'ready' ? 'Skip' : 'OK'),
      c.status === 'applied' && [h('span', { class: 'small' }, 'Applied: the next images in this style use it. '),
        h('button', { class: 'ghost small', onClick: () => undoEdit({ id: c.edit }, async () => { await refreshStyles(); toast('Undone; the proposal is gone, the style is as before.'); }) }, 'Undo')],
      h('a', { class: 'small', href: '#/taste/' + encodeURIComponent(k) }, 'The style on the Taste page')));
}

async function ask() {
  try {
    state = await api('distil/run', { method: 'POST', body: {} });
    draw();
  } catch (err) { showError(err); }
}

async function decide(style, action, changes) {
  try {
    state = await api('distil/decide', { method: 'POST', body: { style, action, changes } });
    if (action === 'apply') { await refreshStyles(); all = await styles(); toast(`${all[style]?.name || style} updated: the next images use it.`); }
    draw();
  } catch (err) { showError(err); }
}

async function mark() {
  const open = Object.values(state.run?.styles || {}).filter((c) => ['ready', 'nothing', 'failed'].includes(c.status)).length;
  if (!confirm(`Mark the distil done?\n\nThe next distil starts after these ${state.total} ratings.` + (open ? `\n${plural(open, 'proposal')} not decided will be dropped.` : ''))) return;
  try {
    state = await api('distil/mark', { method: 'POST', body: {} });
    skip = {};
    toast('Distil marked done. New ratings start the next one.');
    draw();
  } catch (err) { showError(err); }
}
