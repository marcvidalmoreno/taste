// Gallery: every generated image in justified rows (like Flickr), filtered by style, rating and batch.
// The large view has the same thumbs as the batch view (21 Nov 2026): a mark is saved at once and counts
// for the style's next runs; the same thumb again takes it back. Filters are not re-applied while you mark,
// so nothing jumps away under the pointer.
//   #/gallery?style=<key>&rating=keep|no|almost|none (keep = up, no = down, almost = older ratings)&batch=<batch>
// Rows: each tile grows in proportion to its width / height, so every row fills the width at one shared
// height and no image is cropped. A last invisible filler stops the final row from stretching.
import { api, styles } from './api.js';
import { openStyleEdit } from './styleedit.js';
import { setKept, keepButton } from './marks.js';
import { similarRow } from './similar.js';
import { h, imgUrl, thumbUrl, batchHref, batchTitle, shortDate, plural, RATINGS, RATING_LABELS, ratingForKey, showError, isTyping } from './ui.js';

const ROW_H = 220;   // target row height in px; rows end up a little taller to fill the width
let all = [];        // every image from the server
let stepList = [];   // what the large view steps through: the grid's list, or a "More like this" row
let shown = [];      // after the filters, in page order (the large view steps through these)
let styleMap = {};
styles().then((st) => { styleMap = st; });   // names for a large view opened from outside this page
let dlg, index = 0;

export const galleryHref = (q = {}) => {
  const p = new URLSearchParams(Object.entries(q).filter(([, v]) => v));
  return '#/gallery' + (p.size ? '?' + p : '');
};

export const ratingLabel = (r) => (r ? RATING_LABELS[r].label : 'Not rated');

export async function loadGallery() {
  const [g, st] = await Promise.all([api('gallery'), styles()]);
  return { images: g.images, styles: st };
}

export async function renderGallery(view, query) {
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading the gallery…'));
  try {
    ({ images: all, styles: styleMap } = await loadGallery());
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not load the gallery.'));
    return showError(err);
  }
  document.title = 'Gallery · taste';
  const f = { style: query.get('style') || '', rating: query.get('rating') || '', batch: query.get('batch') || '' };
  shown = all.filter((im) =>
    (!f.style || im.style === f.style) &&
    (!f.rating || (f.rating === 'none' ? !im.rating : im.rating === f.rating)) &&
    (!f.batch || im.batch === f.batch));

  if (!all.length) {
    return view.replaceChildren(h('div', { class: 'empty' }, h('h1', {}, 'No images yet'),
      h('p', { class: 'muted' }, 'Images made through Codex show here once a batch exists in generated/codex/.')));
  }

  view.replaceChildren(
    h('hgroup', { class: 'page-head' }, h('h1', {}, 'Gallery'),
      h('p', {}, shown.length === all.length ? plural(all.length, 'image') : `${shown.length} of ${plural(all.length, 'image')}`)),
    filters(f),
    shown.length
      ? h('div', { class: 'justified' }, shown.map(tile), h('span', { class: 'filler', 'aria-hidden': 'true' }))
      : h('p', { class: 'empty muted' }, 'No image matches these filters. ',
          h('a', { href: galleryHref() }, 'Show all'))
  );
}

function filters(f) {
  const set = (k, v) => { location.hash = galleryHref({ ...f, [k]: v }); };
  const count = (pred) => all.filter(pred).length;
  const styleKeys = [...new Set(all.map((im) => im.style).filter(Boolean))]
    .sort((a, b) => (styleMap[a]?.name || a).localeCompare(styleMap[b]?.name || b));
  const batches = [...new Set(all.map((im) => im.batch))].sort().reverse();
  const ratings = [['', 'All'], ['keep', 'Up'], ['no', 'Down'], ['almost', 'Almost (old)'], ['none', 'Not rated']];
  return h('div', { class: 'gallery-filters' },
    h('div', { role: 'group', class: 'rseg', 'aria-label': 'Rating' },
      ratings.map(([v, label]) => h('button', {
        class: `rseg-btn ${v}`, 'aria-pressed': String(f.rating === v), onClick: () => set('rating', v),
      }, label, h('small', {}, ' ', count((im) => !v || (v === 'none' ? !im.rating : im.rating === v)))))),
    h('select', { 'aria-label': 'Style', onChange: (e) => set('style', e.target.value) },
      h('option', { value: '' }, 'All styles'),
      styleKeys.map((k) => h('option', { value: k, selected: f.style === k },
        `${styleMap[k]?.name || k} (${count((im) => im.style === k)})`))),
    h('select', { 'aria-label': 'Batch', onChange: (e) => set('batch', e.target.value) },
      h('option', { value: '' }, 'All batches'),
      batches.map((b) => h('option', { value: b, selected: f.batch === b }, `${shortDate(b.slice(0, 10))} · ${batchTitle(b)}`))));
}

function ratio(im) {
  const w = +im.width, hh = +im.height;
  return w && hh ? w / hh : 16 / 9;
}

function tile(im, i) {
  const r = ratio(im);
  return h('button', {
    class: 'jtile', dataset: { key: keyOf(im), i: String(i) }, style: { flex: `${r} 1 ${Math.round(r * ROW_H)}px`, aspectRatio: String(r) },
    'aria-label': `${styleMap[im.style]?.name || 'No style'}, ${ratingLabel(im.rating)}${im.kept ? ', kept as example' : ''}${im.why ? ': ' + im.why : ''}`,
    onClick: () => openLarge(i),
  },
  h('img', { src: thumbUrl(im.batch, im.file, im.mtime), alt: '', loading: 'lazy', decoding: 'async' }),
  im.rating && h('span', { class: `mark ${im.rating} saved`, 'aria-hidden': 'true' }, RATING_LABELS[im.rating].glyph),
  im.kept && h('span', { class: 'kept-star', title: 'Kept as an example', 'aria-hidden': 'true' }, '★'));
}

const keyOf = (im) => `${im.batch}/${im.name}`;

// After a mark: swap the tile's badge in place (the grid keeps its order and filter until the page is read again).
function refreshTile(im) {
  const el = document.querySelector(`.jtile[data-key="${CSS.escape(keyOf(im))}"]`);
  if (el) el.replaceWith(tile(im, +el.dataset.i));
}

// ------------------------------------------------------------------ marks (saved at once, like the batch view)

const pendingWhy = new Map();   // key -> timer: the "why" is sent a second after the last key, or on leaving

function sendMark(im) {
  return api('mark', { method: 'PUT', body: { batch: im.batch, name: im.name, rating: im.rating || null, why: im.why || '' } });
}

async function toggleMark(im, rating) {
  if (rating === 'almost') return;
  const before = { rating: im.rating, why: im.why };
  im.rating = im.rating === rating ? null : rating;
  clearTimeout(pendingWhy.get(keyOf(im)));
  pendingWhy.delete(keyOf(im));
  redraw(im);
  try {
    await sendMark(im);
  } catch (err) {
    Object.assign(im, before);
    redraw(im);
    showError(err);
  }
}

function setWhy(im, why) {
  im.why = why;
  const k = keyOf(im);
  clearTimeout(pendingWhy.get(k));
  if (!im.rating) return;   // a why without a mark waits until a thumb is pressed
  pendingWhy.set(k, setTimeout(() => { pendingWhy.delete(k); sendMark(im).catch(showError); refreshTile(im); }, 1000));
}

function flushWhy() {
  for (const [k, t] of pendingWhy) {
    clearTimeout(t);
    pendingWhy.delete(k);
    const im = stepList.find((x) => keyOf(x) === k);
    if (im) { sendMark(im).catch(showError); refreshTile(im); }
  }
}

function redraw(im) {
  refreshTile(im);
  if (dlg?.open && stepList[index] === im) drawMarks(im);
}

// Keep as example: the star shows on the tile and on Taste; the grid does not reflow.
function keep(im) {
  setKept(im, im.batch, !im.kept).then(() => { refreshTile(im); if (dlg?.open && stepList[index] === im) drawKeep(im); }).catch(() => {});
}

// ------------------------------------------------------------------ large view

function ensureDialog() {
  if (dlg) return;
  dlg = h('dialog', { class: 'glarge', 'aria-label': 'Large view', tabindex: '-1' });
  dlg.addEventListener('keydown', (e) => {
    if (isTyping(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    const rating = ratingForKey(e.key.toLowerCase());
    if (rating) { e.preventDefault(); toggleMark(stepList[index], rating); }
    if (e.key.toLowerCase() === 'x') { e.preventDefault(); keep(stepList[index]); }
    if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
  });
  dlg.addEventListener('close', flushWhy);
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });  // click on the backdrop
  document.body.append(dlg);
}

export function openLarge(i, list) {
  stepList = list || shown;   // the grid's list, or another one (Taste, "More like this"): the grid keeps its own
  ensureDialog();
  index = i;
  draw();
  if (!dlg.open) dlg.showModal();
  dlg.focus();
}

function step(d) {
  const n = index + d;
  if (n < 0 || n >= stepList.length) return;
  flushWhy();
  index = n;
  draw();
}

let markBox, keepBox;
function drawKeep(im) { keepBox.replaceChildren(keepButton(im, () => keep(im))); }

function draw() {
  const im = stepList[index];
  const st = styleMap[im.style];
  dlg.replaceChildren(
    h('div', { class: 'glarge-img' },
      h('img', { src: imgUrl(im.batch, im.file, im.mtime), alt: `${st?.name || 'No style'}, ${ratingLabel(im.rating)}` })),
    h('aside', { class: 'glarge-side' },
      h('div', { class: 'glarge-nav' },
        h('button', { class: 'secondary outline', onClick: () => step(-1), disabled: index === 0, 'aria-label': 'Previous image' }, '←'),
        h('span', { class: 'muted small' }, `${index + 1} / ${stepList.length}`),
        h('button', { class: 'secondary outline', onClick: () => step(1), disabled: index === stepList.length - 1, 'aria-label': 'Next image' }, '→'),
        h('button', { class: 'secondary outline close', onClick: () => dlg.close(), 'aria-label': 'Close' }, '✕')),
      markBox = h('section', { class: 'mark-box' }),
      keepBox = h('div', { class: 'keep-box' }),
      similarRow(im, im.batch, !!im.style),
      h('dl', {},
        h('dt', {}, 'Style'), h('dd', {}, st ? h('a', { href: '#/taste/' + encodeURIComponent(im.style), onClick: () => dlg.close() }, st.name) : '–'),
        h('dt', {}, 'Batch'), h('dd', {}, h('a', { href: batchHref(im.batch), onClick: () => dlg.close() }, batchTitle(im.batch)),
          ' · ', shortDate(im.date)),
        im.change && [h('dt', {}, 'Variation'), h('dd', {}, `changes the ${im.change}`)]),
      st && h('button', { class: 'secondary outline small-btn', onClick: () => openStyleEdit({ style: im.style, batch: im.batch, name: im.name, file: im.file }) },
        `Change the style…`),
      im.prompt && h('details', {}, h('summary', {}, 'Prompt'), h('p', { class: 'prompt' }, im.prompt)),
      h('p', { class: 'keys muted small' }, h('kbd', {}, '←'), h('kbd', {}, '→'), ' move  ',
        h('kbd', {}, 'U'), h('kbd', {}, 'D'), ' up / down  ', h('kbd', {}, 'X'), ' keep as example  ', h('kbd', {}, 'Esc'), ' close')));
  drawMarks(im);
  drawKeep(im);
}

// Thumbs, why and a one-line status. Redrawn alone after a mark, so the why field keeps its cursor otherwise.
function drawMarks(im) {
  const st = styleMap[im.style]?.name || 'this style';
  const r = im.rating;
  const status = r === 'almost' ? 'Almost (old rating). Press Up or Down to replace it.'
    : r ? `Saved. Counts for ${st}; press the same thumb again to take it back.`
    : 'Not marked yet. A mark counts at once and steers the next runs of this style.';
  markBox.replaceChildren(
    h('div', { role: 'group', class: 'marks', 'aria-label': 'Mark' },
      Object.entries(RATINGS).map(([key, m]) => h('button', {
        type: 'button', class: `mark-btn ${key}`, 'aria-pressed': String(r === key), onClick: () => toggleMark(im, key),
      }, h('span', { 'aria-hidden': 'true' }, m.glyph), ' ', m.label, ' ', h('kbd', {}, m.key.toUpperCase())))),
    h('input', {
      type: 'text', class: 'why', value: im.why || '', maxlength: 300, 'aria-label': 'Why',
      placeholder: 'Why? a few words (optional)',
      onInput: (e) => setWhy(im, e.target.value),
      onKeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); step(1); } },
    }),
    h('p', { class: 'muted small status' }, status));
}
