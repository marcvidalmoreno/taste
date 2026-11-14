// Gallery: every generated image in justified rows (like Flickr), filtered by style, rating and batch.
// Read-only on purpose: marking stays in the batch view, so this page can be browsed without risk.
//   #/gallery?style=<key>&rating=keep|almost|no|none&batch=<batch>
// Rows: each tile grows in proportion to its width / height, so every row fills the width at one shared
// height and no image is cropped. A last invisible filler stops the final row from stretching.
import { api, styles } from './api.js';
import { h, imgUrl, thumbUrl, batchHref, batchTitle, shortDate, plural, RATINGS, showError, isTyping } from './ui.js';

const ROW_H = 220;   // target row height in px; rows end up a little taller to fill the width
let all = [];        // every image from the server
let shown = [];      // after the filters, in page order (the large view steps through these)
let styleMap = {};
let dlg, index = 0;

export const galleryHref = (q = {}) => {
  const p = new URLSearchParams(Object.entries(q).filter(([, v]) => v));
  return '#/gallery' + (p.size ? '?' + p : '');
};

export const ratingLabel = (r) => (r ? RATINGS[r].label : 'Not rated');

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
  const ratings = [['', 'All'], ['keep', 'Keep'], ['almost', 'Almost'], ['no', 'No'], ['none', 'Not rated']];
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
    class: 'jtile', style: { flex: `${r} 1 ${Math.round(r * ROW_H)}px`, aspectRatio: String(r) },
    'aria-label': `${styleMap[im.style]?.name || 'No style'}, ${ratingLabel(im.rating)}${im.why ? ': ' + im.why : ''}`,
    onClick: () => openLarge(i),
  },
  h('img', { src: thumbUrl(im.batch, im.file, im.mtime), alt: '', loading: 'lazy', decoding: 'async' }),
  im.rating && h('span', { class: `mark ${im.rating} saved`, 'aria-hidden': 'true' }, RATINGS[im.rating].key.toUpperCase()));
}

// ------------------------------------------------------------------ large view (read-only)

function ensureDialog() {
  if (dlg) return;
  dlg = h('dialog', { class: 'glarge', 'aria-label': 'Large view', tabindex: '-1' });
  dlg.addEventListener('keydown', (e) => {
    if (isTyping(e)) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
  });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });  // click on the backdrop
  document.body.append(dlg);
}

export function openLarge(i, list) {
  if (list) shown = list;
  ensureDialog();
  index = i;
  draw();
  if (!dlg.open) dlg.showModal();
  dlg.focus();
}

function step(d) {
  const n = index + d;
  if (n < 0 || n >= shown.length) return;
  index = n;
  draw();
}

function draw() {
  const im = shown[index];
  const st = styleMap[im.style];
  dlg.replaceChildren(
    h('div', { class: 'glarge-img' },
      h('img', { src: imgUrl(im.batch, im.file, im.mtime), alt: `${st?.name || 'No style'}, ${ratingLabel(im.rating)}` })),
    h('aside', { class: 'glarge-side' },
      h('div', { class: 'glarge-nav' },
        h('button', { class: 'secondary outline', onClick: () => step(-1), disabled: index === 0, 'aria-label': 'Previous image' }, '←'),
        h('span', { class: 'muted small' }, `${index + 1} / ${shown.length}`),
        h('button', { class: 'secondary outline', onClick: () => step(1), disabled: index === shown.length - 1, 'aria-label': 'Next image' }, '→'),
        h('button', { class: 'secondary outline close', onClick: () => dlg.close(), 'aria-label': 'Close' }, '✕')),
      h('p', {}, im.rating
        ? h('span', { class: `rating-pill ${im.rating}` }, RATINGS[im.rating].label)
        : h('span', { class: 'rating-pill' }, 'Not rated'),
        im.why && h('span', { class: 'why' }, ' ', im.why)),
      h('dl', {},
        h('dt', {}, 'Style'), h('dd', {}, st ? h('a', { href: '#/taste/' + encodeURIComponent(im.style), onClick: () => dlg.close() }, st.name) : '–'),
        h('dt', {}, 'Batch'), h('dd', {}, h('a', { href: batchHref(im.batch), onClick: () => dlg.close() }, batchTitle(im.batch)),
          ' · ', shortDate(im.date)),
        im.change && [h('dt', {}, 'Variation'), h('dd', {}, `changes the ${im.change}`)]),
      im.prompt && h('details', {}, h('summary', {}, 'Prompt'), h('p', { class: 'prompt' }, im.prompt))));
}
