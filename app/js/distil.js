// Suggestions (the distil, 21 Nov 2026): Codex reads the ratings since the last look and suggests edits to a style's
// words. It runs by itself every 20 ratings (scripts/app.py maybe_auto_distil); the header shows a chip only when a
// suggestion waits; Apply or Skip here, and the round closes on its own once nothing waits. Tech out of sight.
//   #/suggestions (also #/distil)
// One button asks Codex about every style with enough new ratings (3 at a time, ~10-30 s each, medium reasoning).
// Each style's card shows the images rated (ups and downs, with the why), Codex's reading, and its proposed edit
// field by field; untick what you don't want, Apply or Skip. Nothing changes until Apply; each apply can be undone.
// When done, "Mark the distil done" starts the next round after these ratings. The leaning (thumbs re-weighting
// options) runs on its own; this is where new words enter a style.
import { api, styles, refreshStyles } from './api.js';
import { FIELDS, diffValue, undoEdit } from './styleedit.js';
import { h, thumbUrl, batchHref, shortDate, plural, toast, showError } from './ui.js';

const STATUS = { waiting: 'Waiting', thinking: 'Codex is reading…', ready: 'Suggestion', nothing: 'Fine as it is',
  applied: 'Applied', skipped: 'Skipped', failed: 'Failed' };
let view, timer, state, all, skip = {};

export async function renderDistil(el) {
  view = el;
  clearTimeout(timer);
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Reading the ratings…'));
  document.title = 'Suggestions · taste';
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
  const cards = run ? Object.entries(run.styles).sort((a, b) => b[1].n - a[1].n) : [];
  const waiting = cards.filter(([, c]) => c.status === 'ready');
  const decided = cards.filter(([, c]) => c.status === 'applied' || c.status === 'skipped');
  const fine = cards.filter(([, c]) => c.status === 'nothing');
  const failed = cards.filter(([, c]) => c.status === 'failed');
  const eligible = Object.entries(state.since).filter(([, d]) => d.n >= state.min);
  const toGo = Math.max(0, state.due - state.total);
  const focusKey = document.activeElement?.dataset?.focus;
  const name = (k) => all[k]?.name || k;

  view.replaceChildren(h('div', { class: 'distil-page' },
    h('header', { class: 'grid-head' },
      h('hgroup', {}, h('h1', {}, 'Suggestions for your styles'),
        h('p', {}, run?.running ? 'Codex is looking at your latest ratings…'
          : waiting.length ? `${plural(waiting.length, 'suggestion')} from your latest ratings. Apply what you agree with.`
          : 'Nothing waiting for you.'))),
    state.dry_run && h('p', { class: 'notice' }, 'Dry run: Codex is not asked; each suggestion is a stand-in line.'),
    run?.running && h('p', { class: 'distil-progress', 'aria-live': 'polite' }, h('span', { class: 'pulse', 'aria-hidden': 'true' }),
      ' Suggestions appear here as they come; you can start with the first ones.'),
    waiting.length > 0 && h('div', { class: 'distil-cards' }, waiting.map(([k, c]) => card(k, c))),
    decided.length > 0 && h('div', { class: 'distil-cards' }, decided.map(([k, c]) => card(k, c))),
    (fine.length > 0 || failed.length > 0) && h('details', { class: 'distil-fine' },
      h('summary', {}, fine.length ? `Fine as they are: ${fine.map(([k]) => name(k)).join(', ')}` : '',
        failed.length ? `${fine.length ? ' · ' : ''}Not checked this time: ${failed.map(([k]) => name(k)).join(', ')}` : ''),
      h('ul', { class: 'plain' }, [...fine, ...failed].map(([k, c]) => h('li', { class: 'small' },
        h('strong', {}, name(k)), h('span', { class: 'muted' }, ` · 👍 ${c.up} · 👎 ${c.down} · `), c.summary || c.error || '')))),
    !run && lastRound(),
    !run && h('p', { class: 'muted small distil-next' },
      `Codex looks at your styles by itself every ${state.due} ratings` + (toGo ? `: the next check comes after ${plural(toGo, 'more rating')}.` : '.'),
      ' Downs and a few “why” words give it the most to work with.',
      eligible.length > 0 && toGo > 0 && [' ', h('button', { class: 'ghost small', 'data-focus': 'ask', onClick: ask }, 'Look now')])));
  if (focusKey) view.querySelector(`[data-focus="${CSS.escape(focusKey)}"]`)?.focus();
  if (run?.running) timer = setTimeout(refresh, 2000);
}

// The round that just closed: what changed, so the end of a review never feels like nothing happened.
function lastRound() {
  const l = state.last;
  if (!l) return null;
  const cards = Object.entries(l.styles);
  const applied = cards.filter(([, c]) => c.status === 'applied');
  const fine = cards.filter(([, c]) => c.status === 'nothing').length;
  return h('section', { class: 'card distil-last' },
    h('h2', {}, `Last look, ${shortDate(l.started.slice(0, 10))}`),
    h('p', {}, applied.length ? `${plural(applied.length, 'style')} changed: ${applied.map(([k]) => all[k]?.name || k).join(', ')}.` : 'No style changed.',
      fine ? ` ${plural(fine, 'style')} fine as they are.` : ''),
    applied.length > 0 && h('p', { class: 'small' }, 'Each change can be undone from its style on the ', h('a', { href: '#/taste' }, 'Taste page'), '.'));
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
        onClick: () => decide(k, 'apply', Object.fromEntries(fields.filter(([f]) => !off.has(f)))) }, 'Apply'),
      c.status === 'ready' && h('button', { class: 'secondary outline small-btn', 'data-focus': `${k}-skip`,
        onClick: () => decide(k, 'skip') }, 'Skip'),
      c.status === 'skipped' && h('span', { class: 'small muted' }, 'Skipped.'),
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
    if (!state.run) toast('All done. Codex looks again after your next 20 ratings.');
    draw();
  } catch (err) { showError(err); }
}
