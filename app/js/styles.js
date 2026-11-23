// Styles: every style on one page, with an on / off switch, its runs and how well it does (👍 rate).
//   #/styles            the list
//   #/styles/<style>    the same page with that style's history open under its row (one at a time, linkable)
// Off = the style file moves to taste/styles/archived/ (scripts/app.py set_archived): New run, Suggestions and the
// style guesses stop offering it; its images stay in the Gallery. Switching acts at once and says Undo.
import { api, refreshStyles } from './api.js';
import { h, batchHref, shortDate, plural, toast, showError } from './ui.js';
import { galleryHref } from './gallery.js';

let filter = '';
const enc = encodeURIComponent;
const MIN_N = 5;   // under this many rated images the 👍 rate is a hint, not a result: shown greyed

const pct = (r) => `${Math.round(r * 100)} %`;

// "73 % of 11": the rate always comes with n, greyed when n is small
function rateText(d) {
  if (!d || !d.n) return h('span', { class: 'muted' }, '–');
  return h('span', { class: d.n < MIN_N ? 'rate faint' : 'rate', title: `${d.up} 👍 · ${d.down} 👎${d.n < MIN_N ? ` (under ${MIN_N} rated: only a hint)` : ''}` },
    `👍 ${pct(d.rate)}`, ' ', h('small', { class: 'muted' }, `n ${d.n}`));
}

// Small trend of the 👍 rate over the last batches that were rated (decoration: the number beside it says it)
function spark(values) {
  const v = values.filter((x) => x != null);
  if (v.length < 2) return h('span', { class: 'muted small' }, v.length ? '1 batch' : '');
  const W = 64, H = 18, step = W / (v.length - 1);
  const pts = v.map((x, i) => `${(i * step).toFixed(1)},${(H - 2 - x * (H - 4)).toFixed(1)}`).join(' ');
  return h('span', { class: 'spark', role: 'img', 'aria-label': `👍 rate over the last ${plural(v.length, 'rated batch', 'rated batches')}: ${v.map(pct).join(', ')}` },
    svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, 'aria-hidden': 'true' },
      svg('polyline', { points: pts, fill: 'none', stroke: 'var(--keep)', 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' })));
}

function svg(tag, attrs = {}, ...kids) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  el.append(...kids.flat().filter(Boolean));
  return el;
}

export async function renderStyles(view, focus) {
  if (!view.querySelector('.styles-page')) view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading the styles…'));
  let rows;
  try {
    ({ styles: rows } = await api('styles/overview'));
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not load the styles.'));
    return showError(err);
  }
  document.title = 'Styles · taste';
  const on = rows.filter((r) => r.on).sort((a, b) => (b.last || '').localeCompare(a.last || '') || a.name.localeCompare(b.name));
  const off = rows.filter((r) => !r.on).sort((a, b) => a.name.localeCompare(b.name));
  const list = h('div', { class: 'style-list' });
  const archived = h('details', { class: 'archived-box' });
  const draw = () => {
    const q = filter.trim().toLowerCase();
    const keep = (r) => !q || r.name.toLowerCase().includes(q) || r.key.includes(q);
    const a = on.filter(keep), b = off.filter(keep);
    list.replaceChildren(...(a.length ? a.map((r) => rowFor(r, focus, redo)) : [h('p', { class: 'muted' }, q ? 'No style matches.' : 'No style is on.')]));
    archived.hidden = !off.length;
    archived.open = archived.open || (q && b.length > 0) || off.some((r) => r.key === focus);
    archived.replaceChildren(h('summary', {}, `Archived (${off.length})`),
      h('p', { class: 'muted small' }, 'Switched off: not offered in New run, suggestions or guesses. Their images stay in the Gallery.'),
      ...b.map((r) => rowFor(r, focus, redo)));
  };
  const redo = () => renderStyles(document.getElementById('view'), parseFocus());

  view.replaceChildren(h('div', { class: 'styles-page' },
    h('div', { class: 'page-head' },
      h('hgroup', {}, h('h1', {}, 'Styles'),
        h('p', {}, `${on.length} on${off.length ? ` · ${off.length} archived` : ''}. Switch a style off to stop using it; its history stays here.`)),
      h('input', { type: 'search', class: 'find', placeholder: 'Find a style', value: filter, 'aria-label': 'Find a style',
        onInput: (e) => { filter = e.target.value; draw(); } })),
    list, archived));
  draw();
  const open = view.querySelector('.style-row.is-open');
  if (open) open.scrollIntoView({ block: 'nearest' });
}

const parseFocus = () => decodeURIComponent((location.hash.split('?')[0].split('/')[2]) || '') || undefined;

function rowFor(r, focus, redo) {
  const open = focus === r.key;
  const panel = h('div', { class: 'history', 'aria-live': 'polite' });
  const row = h('section', { class: `style-row${open ? ' is-open' : ''}${r.on ? '' : ' is-off'}`, id: 'row-' + r.key },
    h('div', { class: 'style-line' },
      h('span', { class: 'mini-swatch', 'aria-hidden': 'true' }, r.palette.slice(0, 4).map((c) => h('i', { style: { background: c } }))),
      h('a', { class: 'style-name', href: open ? '#/styles' : '#/styles/' + enc(r.key), 'aria-expanded': String(open),
               title: open ? 'Close its history' : 'Open its history' }, r.name),
      switchFor(r, redo),
      h('span', { class: 'cell', title: `${plural(r.batches, 'batch', 'batches')}` }, plural(r.images, 'image')),
      h('span', { class: 'cell' }, rateText(r)),
      h('span', { class: 'cell', title: 'Kept as examples' }, r.kept ? `★ ${r.kept}` : h('span', { class: 'muted' }, '☆ 0')),
      h('span', { class: 'cell muted small' }, r.last ? `last run ${shortDate(r.last.slice(0, 10))}` : 'never run'),
      h('span', { class: 'cell' }, spark(r.spark))),
    open && panel);
  if (open) loadHistory(r.key, panel);
  return row;
}

function switchFor(r, redo) {
  const blocked = r.on && r.busy;
  const label = r.on ? 'On' : 'Off';
  return h('button', { type: 'button', role: 'switch', class: 'switch', 'aria-checked': String(r.on),
    'aria-label': `${r.name}: ${label}`, disabled: blocked ? true : null,
    title: blocked ? `Cannot switch it off now: ${r.busy}` : r.on ? 'Switch off (archive)' : 'Switch back on',
    onClick: async (e) => {
      const btn = e.currentTarget;
      btn.setAttribute('aria-busy', 'true');
      try {
        await api('styles/switch', { method: 'POST', body: { style: r.key, on: !r.on } });
        await refreshStyles();
        toast(r.on ? `${r.name} is off: New run, suggestions and guesses no longer offer it.` : `${r.name} is back on.`, {
          action: 'Undo', timeout: 8000,
          onAction: async () => {
            try { await api('styles/switch', { method: 'POST', body: { style: r.key, on: r.on } }); await refreshStyles(); } catch (err) { showError(err); }
            redo();
          } });
      } catch (err) { showError(err); }
      redo();
    } }, h('i', { 'aria-hidden': 'true' }), h('span', { class: 'switch-word' }, label));
}

// ---- history panel

const KIND = { created: 'Created', commit: 'Committed', edit: 'Edited in the app', distil: 'Distil applied', off: 'Switched off', on: 'Switched on' };
const when = (at) => `${shortDate(at.slice(0, 10))} ${at.slice(11)}`;

async function loadHistory(key, box) {
  box.replaceChildren(h('p', { 'aria-busy': 'true', class: 'small' }, 'Reading its history…'));
  let d;
  try { d = await api('styles/history/' + enc(key)); } catch (err) { box.replaceChildren(h('p', {}, 'Could not read the history.')); return showError(err); }
  const t = d.total;
  box.replaceChildren(
    h('p', { class: 'small history-top' }, h('span', {}, `${plural(t.images, 'image')} · `), rateText(t), h('span', {}, t.kept ? ` · ★ ${t.kept} kept` : ''), ' · ',
      h('a', { href: '#/taste/' + enc(key) }, 'Its card in Taste'), ' · ', h('a', { href: galleryHref({ style: key }) }, 'Its images in the Gallery')),
    h('div', { class: 'history-cols' },
      h('div', {}, h('h3', {}, 'Evolution'), timeline(d)),
      h('div', {}, h('h3', {}, '👍 rate per batch'), chart(d), runsList(d))));
}

function timeline(d) {
  if (!d.events.length) return h('p', { class: 'muted small' }, 'No recorded changes.');
  const seg = (s) => (s && s.images ? [rateText(s), h('small', { class: 'muted' }, ` · ${plural(s.images, 'image')}`)] : h('span', { class: 'muted' }, 'no images'));
  return h('ol', { class: 'timeline' }, d.events.map((e, i) => h('li', { class: e.undone ? 'is-undone' : '' },
    h('span', { class: 'ev-num', title: 'Marked on the chart with this number' }, i + 1),
    h('div', {}, h('div', {}, h('strong', {}, KIND[e.kind] || e.kind), ' ', h('span', { class: 'muted small' }, `${when(e.at)}${e.undone ? ' · undone' : ''}`)),
      e.title && h('div', { class: 'small' }, e.title),
      e.detail && h('div', { class: 'small muted' }, e.detail),
      e.before && h('div', { class: 'small ba' }, h('span', { class: 'muted' }, 'Before '), seg(e.before), h('span', { class: 'muted' }, '  →  After '), seg(e.after))))));
}

// One series, one hue: the 👍 rate of each batch (rated images only). Events are dashed vertical lines with their
// number from the Evolution list. Hover or focus a dot for the counts; the runs list below holds the same numbers.
function chart(d) {
  const bs = d.batches;
  if (!bs.some((b) => b.n)) return h('p', { class: 'muted small' }, 'No rated images yet: the chart needs 👍 and 👎.');
  const W = 560, H = 170, L = 34, R = 10, T = 20, B = 22, N = bs.length;
  const x = (pos) => L + ((pos + 0.5) / N) * (W - L - R);
  const y = (v) => T + (1 - v) * (H - T - B);
  const g = [0, 0.5, 1].map((v) => svg('g', {},
    svg('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: 'var(--line)', 'stroke-width': 1 }),
    svg('text', { x: L - 6, y: y(v) + 4, 'text-anchor': 'end', fill: 'var(--pico-muted-color)', 'font-size': 10 }, `${v * 100}%`)));
  const seen = bs.map((b, i) => (b.n ? [x(i), y(b.rate)] : null));
  const path = seen.filter(Boolean).map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('');
  const evs = d.events.map((e, i) => {
    if (e.undone) return null;
    const ex = x(e.index - 0.5);
    return svg('g', {}, svg('title', {}, `${i + 1}. ${KIND[e.kind] || e.kind}, ${when(e.at)}`),
      svg('line', { x1: ex, x2: ex, y1: 15, y2: H - B, stroke: 'var(--pico-muted-color)', 'stroke-width': 1, 'stroke-dasharray': '3 3' }),
      svg('text', { x: ex, y: 11, 'text-anchor': 'middle', fill: 'var(--text)', 'font-size': 10, 'font-weight': 600 }, String(i + 1)));
  });
  const dots = bs.map((b, i) => b.n && svg('circle', { cx: x(i), cy: y(b.rate), r: 4.5, fill: 'var(--keep)', stroke: 'var(--surface)', 'stroke-width': 2,
    opacity: b.n < MIN_N ? 0.55 : 1, tabindex: 0,
    'aria-label': `${shortDate(b.date)}: ${b.up} 👍 of ${b.n} rated, ${pct(b.rate)}` },
    svg('title', {}, `${shortDate(b.date)} · ${b.batch}: ${b.up} 👍 of ${b.n} rated (${pct(b.rate)}), ${plural(b.images, 'image')}`)));
  return h('figure', { class: 'hist-chart' },
    svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `👍 rate per batch for ${d.name}, with the numbered events. The runs below hold the same numbers.` },
      g, evs, svg('path', { d: path, fill: 'none', stroke: 'var(--keep)', 'stroke-width': 2, 'stroke-linejoin': 'round' }), dots,
      svg('text', { x: L, y: H - 8, fill: 'var(--pico-muted-color)', 'font-size': 10 }, shortDate(bs[0].date)),
      ),
    h('figcaption', { class: 'muted small' }, 'Fainter dots: under 5 rated images. Dashed lines: the numbered events.'));
}

function runsList(d) {
  if (!d.batches.length) return h('p', { class: 'muted small' }, 'No runs yet.');
  const rows = [...d.batches].reverse();
  return h('details', { class: 'runs-list', open: rows.length <= 12 ? true : null },
    h('summary', {}, `Runs (${rows.length})`),
    h('table', {}, h('thead', {}, h('tr', {}, ['Batch', 'Date', 'Images', '👍', '👎', '★'].map((t) => h('th', {}, t)))),
      h('tbody', {}, rows.map((b) => h('tr', {},
        h('td', {}, h('a', { href: batchHref(b.batch) }, b.batch.replace(/^\d{4}-\d\d-\d\d-/, '').replace(/-/g, ' '))),
        h('td', {}, shortDate(b.date)), h('td', {}, b.images), h('td', {}, b.up), h('td', {}, b.down), h('td', {}, b.kept || ''))))));
}
