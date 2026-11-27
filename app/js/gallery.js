// Gallery: every generated image in justified rows (like Flickr), filtered by words, style, rating and batch.
// The large view has the same thumbs as the batch view (21 Nov 2026): a mark is saved at once and counts
// for the style's next runs; the same thumb again takes it back. Filters are not re-applied while you mark,
// so nothing jumps away under the pointer.
//   #/gallery?q=<words>&style=<key>[,<key>…]&model=<model>[,<model>…]&rating=keep|no|almost|none (keep = up, no = down, almost = older ratings)&batch=<batch>
//   #/gallery/<batch>/<image>?...   the same, with the large view open on one image (23 Nov 2026): the address
//   follows every step, so an image can be linked and reloaded; Back closes the view (one history entry per opening).
// Find (23 Nov 2026): every word must appear in the prompt, the why, the style name, the batch or the variation.
// Typing redraws only the grid and the count (the field keeps its cursor); the address follows without a reload.
// Rows: each tile grows in proportion to its width / height, so every row fills the width at one shared
// height and no image is cropped. A last invisible filler stops the final row from stretching.
// Size (23 Nov 2026): Small / Medium / Large set the target row height through --row-h, so a change reflows the
// rows without redrawing them; the choice is a view preference, kept in localStorage (not in the address).
// Style tags (24 Nov 2026): one toggle chip per style instead of a dropdown; several can be on at once
// (style=a,b in the address), none on = every style. Size sits at the end of the same filter row.
// Model tags (25 Nov 2026): the same pattern for the model that made each image (model=a,b): ChatGPT, FLUX,
// FLUX local, Z-Image, Playground, and the SDXL fine-tunes (26 Nov 2026).
import { api, styles, archivedStyles, allStyles } from './api.js';
import { openStyleEdit } from './styleedit.js';
import { setKept, keepButton, setPublished, publishButton } from './marks.js';
import { openRemix } from './remix.js';
import { openNote } from './notes.js';
import { similarRow } from './similar.js';
import { historySection } from './history.js';
import { MODELS, modelBadge, modelName, modelTag } from './cost.js';
import { h, imgUrl, thumbUrl, batchHref, batchTitle, shortDate, plural, RATINGS, RATING_LABELS, ratingForKey, showError, isTyping, toast, downloadLink, fullscreenButton, toggleFullscreen } from './ui.js';

// Target row height in px; rows end up a little taller to fill the width. Large stays within the 640 px thumbnails.
const SIZES = [['s', 'Small', 130], ['m', 'Medium', 220], ['l', 'Large', 360]];
const SIZE_KEY = 'taste-gallery-size';
const sizeNow = () => SIZES.find(([k]) => k === localStorage.getItem(SIZE_KEY)) || SIZES[1];
let all = [];        // every image from the server
let stepList = [];   // what the large view steps through: the grid's list, or a "More like this" row
let shown = [];      // after the filters, in page order (the large view steps through these)
let styleMap = {};
allStyles().then((st) => { styleMap = st; });   // names for a large view opened from outside this page
let dlg, index = 0;
let curF = {};        // the filters on screen: kept in the address while the large view is open
let pageKey = null;   // which filters the grid on screen was drawn for (the large view opens without a redraw)
let urlSync = false;  // the large view was opened on the Gallery page, so the address follows the image

// im: also open the large view on that image.
export const galleryHref = (q = {}, im) => {
  const p = new URLSearchParams(Object.entries(q).filter(([, v]) => v));
  return '#/gallery' + (im ? `/${encodeURIComponent(im.batch)}/${encodeURIComponent(im.name)}` : '') + (p.size ? '?' + p : '');
};

export const ratingLabel = (r) => (r ? RATING_LABELS[r].label : 'Not rated');

export async function loadGallery() {
  const [g, st, off] = await Promise.all([api('gallery'), styles(), archivedStyles()]);
  // styles: the ones that are on; archived: switched off; labels: both (an image keeps its style's name)
  return { images: g.images, styles: st, archived: off, labels: { ...off, ...st } };
}

// open: '<batch>/<image>' from the address, or '' for the grid alone.
export async function renderGallery(view, query, open = '') {
  const want = galleryHref(Object.fromEntries(['q', 'style', 'model', 'rating', 'batch', 'pub'].map((k) => [k, query.get(k) || ''])));
  if (want !== pageKey || !view.querySelector('.jgrid')) await drawGallery(view, query);
  else if (Date.now() - loadedAt > 5000) syncMarks();   // the grid on screen was read a while ago
  if (open) openFromUrl(open);
  else if (urlSync && dlg?.open) dlg.close();   // Back from an image: the grid stays as it was
}

async function drawGallery(view, query) {
  pageKey = null;
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading the gallery…'));
  try {
    ({ images: all, labels: styleMap } = await loadGallery());
    loadedAt = Date.now();
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not load the gallery.'));
    return showError(err);
  }
  document.title = 'Gallery · taste';
  const f = { q: query.get('q') || '', style: query.get('style') || '', model: query.get('model') || '', rating: query.get('rating') || '', batch: query.get('batch') || '', pub: query.get('pub') || '' };
  curF = f;
  const picked = new Set(f.style.split(',').filter(Boolean));
  const pickedModels = new Set(f.model.split(',').filter(Boolean));
  const base = all.filter((im) =>
    (!picked.size || picked.has(im.style)) &&
    (!pickedModels.size || pickedModels.has(im.model)) &&
    (!f.rating || (f.rating === 'none' ? !im.rating : im.rating === f.rating)) &&
    (!f.batch || im.batch === f.batch) &&
    (!f.pub || im.published));

  if (!all.length) {
    return view.replaceChildren(h('div', { class: 'empty' }, h('h1', {}, 'No images yet'),
      h('p', { class: 'muted' }, 'Images made through Codex show here once a batch exists in generated/codex/.')));
  }

  const count = h('p', {});
  const grid = h('div', { class: 'jgrid' });
  grid.style.setProperty('--row-h', sizeNow()[2] + 'px');
  const draw = () => {
    shown = base.filter(matcher(f.q));
    count.textContent = shown.length === all.length ? plural(all.length, 'image') : `${shown.length} of ${plural(all.length, 'image')}`;
    grid.replaceChildren(shown.length
      ? h('div', { class: 'justified' }, shown.map(tile), h('span', { class: 'filler', 'aria-hidden': 'true' }))
      : h('p', { class: 'empty muted' }, f.q ? 'No image matches these words. ' : 'No image matches these filters. ',
          h('a', { href: galleryHref() }, 'Show all')));
  };
  const onFind = (q) => {
    f.q = q;
    history.replaceState(null, '', pageKey = galleryHref(f));   // no hashchange: the page is not read again
    draw();
  };
  draw();
  pageKey = galleryHref(f);
  view.replaceChildren(h('hgroup', { class: 'page-head' }, h('h1', {}, 'Gallery'), count),
    filters(f, onFind, sizeControl(grid)), styleTags(f, picked), modelTags(f, pickedModels), grid);
}

// Words in any order, each one somewhere in the image's text; dashes count as spaces (batch names use them).
const norm = (t) => t.toLowerCase().replace(/[-_]/g, ' ');
function matcher(q) {
  const words = norm(q).split(/\s+/).filter(Boolean);
  if (!words.length) return () => true;
  return (im) => {
    const text = norm([im.prompt, im.why, styleMap[im.style]?.name, im.style, batchTitle(im.batch), im.batch, im.change].filter(Boolean).join(' '));
    return words.every((w) => text.includes(w));
  };
}

function filters(f, onFind, size) {
  const set = (k, v) => { location.hash = galleryHref({ ...f, [k]: v }); };
  const count = (pred) => all.filter(pred).length;
  const batches = [...new Set(all.map((im) => im.batch))].sort().reverse();
  const ratings = [['', 'All'], ['keep', 'Up'], ['no', 'Down'], ['almost', 'Almost (old)'], ['none', 'Not rated']];
  return h('div', { class: 'gallery-filters' },
    h('input', { type: 'search', class: 'find', placeholder: 'Find words in prompts, notes, styles', value: f.q,
      'aria-label': 'Find images', onInput: (e) => onFind(e.target.value) }),
    h('div', { role: 'group', class: 'rseg', 'aria-label': 'Rating' },
      ratings.map(([v, label]) => h('button', {
        class: `rseg-btn ${v}`, 'aria-pressed': String(f.rating === v), onClick: () => set('rating', v),
      }, label, h('small', {}, ' ', count((im) => !v || (v === 'none' ? !im.rating : im.rating === v)))))),
    h('button', { class: 'rseg-btn pub-filter', 'aria-pressed': String(!!f.pub), onClick: () => set('pub', f.pub ? '' : '1'),
      title: 'Only the images picked for the public gallery site' }, '◉ Published', h('small', {}, ' ', count((im) => im.published))),
    h('select', { 'aria-label': 'Batch', onChange: (e) => set('batch', e.target.value) },
      h('option', { value: '' }, 'All batches'),
      batches.map((b) => h('option', { value: b, selected: f.batch === b }, `${shortDate(b.slice(0, 10))} · ${batchTitle(b)}`))),
    size);
}

// One chip per style, with its palette and image count: press to show it, press again to take it away.
// Several can be on; "All styles" clears them. Alphabetical, so a chip never moves when pressed.
function styleTags(f, picked) {
  const keys = [...new Set(all.map((im) => im.style).filter(Boolean))]
    .sort((a, b) => (styleMap[a]?.name || a).localeCompare(styleMap[b]?.name || b));
  if (keys.length < 2) return '';
  const go = (next) => { location.hash = galleryHref({ ...f, style: [...next].join(',') }); };
  const toggle = (k) => { const n = new Set(picked); n.has(k) ? n.delete(k) : n.add(k); go(n); };
  return h('div', { role: 'group', class: 'style-tags', 'aria-label': 'Styles' },
    h('button', { class: 'tag', 'aria-pressed': String(!picked.size), onClick: () => go([]) }, 'All styles'),
    keys.map((k) => h('button', { class: 'tag', 'aria-pressed': String(picked.has(k)), onClick: () => toggle(k) },
      h('span', { class: 'mini-swatch', 'aria-hidden': 'true' }, (styleMap[k]?.palette || []).slice(0, 4).map((c) => h('i', { style: { background: c } }))),
      styleMap[k]?.name || k,
      h('small', {}, ' ', all.filter((im) => im.style === k).length))));
}

// One chip per model that made images here, in the Models page's order; several can be on, "All models" clears.
function modelTags(f, picked) {
  const have = new Set(all.map((im) => im.model).filter(Boolean));
  const keys = [...Object.keys(MODELS).filter((k) => have.has(k)), ...(have.has('local') ? ['local'] : [])];
  if (keys.length < 2) return '';
  const go = (next) => { location.hash = galleryHref({ ...f, model: [...next].join(',') }); };
  const toggle = (k) => { const n = new Set(picked); n.has(k) ? n.delete(k) : n.add(k); go(n); };
  return h('div', { role: 'group', class: 'style-tags model-tags', 'aria-label': 'Models' },
    h('button', { class: 'tag', 'aria-pressed': String(!picked.size), onClick: () => go([]) }, 'All models'),
    keys.map((k) => h('button', { class: 'tag', 'aria-pressed': String(picked.has(k)), onClick: () => toggle(k), title: modelName(k) },
      modelBadge(k), h('small', {}, ' ', all.filter((im) => im.model === k).length))));
}

// Small / Medium / Large: more images at a glance, or bigger ones to judge. Reflows at once, no reload.
function sizeControl(grid) {
  const pick = (k, px, group) => {
    localStorage.setItem(SIZE_KEY, k);
    grid.style.setProperty('--row-h', px + 'px');
    group.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.size === k)));
  };
  const group = h('div', { role: 'group', class: 'rseg size-seg', 'aria-label': 'Image size' });
  const now = sizeNow()[0];
  group.append(...SIZES.map(([k, label, px]) => h('button', {
    class: 'rseg-btn', dataset: { size: k }, 'aria-pressed': String(now === k), onClick: () => pick(k, px, group),
  }, label)));
  return group;
}

function ratio(im) {
  const w = +im.width, hh = +im.height;
  return w && hh ? w / hh : 16 / 9;
}

function tile(im, i) {
  const r = ratio(im);
  return h('button', {
    class: 'jtile', dataset: { key: keyOf(im), i: String(i) }, style: { flex: `${r} 1 calc(${r.toFixed(4)} * var(--row-h, 220px))`, aspectRatio: String(r) },
    'aria-label': `${styleMap[im.style]?.name || 'No style'}, ${ratingLabel(im.rating)}${im.kept ? ', kept as example' : ''}${im.published ? ', in the public gallery' : ''}${im.model ? ', made with ' + modelBadge(im.model) : ''}${im.why ? ': ' + im.why : ''}`,
    onClick: () => openLarge(i),
  },
  h('img', { src: thumbUrl(im.batch, im.file, im.mtime), alt: '', loading: 'lazy', decoding: 'async' }),
  im.rating && h('span', { class: `mark ${im.rating} saved`, 'aria-hidden': 'true' }, RATING_LABELS[im.rating].glyph),
  im.published && h('span', { class: 'pub-dot', title: 'In the public gallery', 'aria-hidden': 'true' }, '◉'),
  im.kept && h('span', { class: 'kept-star', title: 'Kept as an example', 'aria-hidden': 'true' }, '★'),
  im.model && h('span', { class: 'route-badge on-image', 'aria-hidden': 'true' }, modelBadge(im.model)));
}

const keyOf = (im) => `${im.batch}/${im.name}`;

// Fresh marks (27 Nov 2026): the grid reads every image once and keeps that list while the tab stays open, so an
// image marked, kept or published in another tab or on its batch page still showed its old state here ("it lost
// the data") until a reload. Now the marks are read again quietly when the Gallery is entered again or the tab
// comes back; only tiles that changed are swapped, nothing reflows. A change made on this page after the read
// started, or a why still being typed, wins over what the server sent.
const LIVE = ['rating', 'why', 'kept', 'published'];
let loadedAt = 0;              // when `all` was last read from the server
const localAt = new Map();     // key -> when this page last changed that image
const touch = (im) => localAt.set(keyOf(im), Date.now());
let syncing = null;

function syncMarks() {
  if (!all.length || syncing) return syncing;
  const started = Date.now();
  syncing = api('gallery').then(({ images }) => {
    loadedAt = Date.now();
    const fresh = new Map(images.map((x) => [keyOf(x), x]));
    for (const im of new Set([...all, ...stepList])) {
      const k = keyOf(im), x = fresh.get(k);
      if (!x || (localAt.get(k) || 0) >= started || pendingWhy.has(k)) continue;
      if (LIVE.every((f) => (im[f] || null) === (x[f] || null))) continue;
      const open = dlg?.open && stepList[index] === im;
      if (open && isTyping({ target: document.activeElement || document.body })) continue;   // never redraw the why field under the cursor
      LIVE.forEach((f) => { im[f] = x[f]; });
      refreshTile(im);
      if (open) { drawMarks(im); drawKeep(im); }
    }
  }).catch(() => {}).finally(() => { syncing = null; });
  return syncing;
}

const onGallery = () => location.hash.startsWith('#/gallery') || dlg?.open;
const backAgain = () => { if (!document.hidden && onGallery() && Date.now() - loadedAt > 5000) syncMarks(); };
document.addEventListener('visibilitychange', backAgain);
window.addEventListener('focus', backAgain);   // another window was in front: no visibilitychange

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
  touch(im);
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
  touch(im);
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
  touch(im);
  setKept(im, im.batch, !im.kept).then(() => { refreshTile(im); if (dlg?.open && stepList[index] === im) drawKeep(im); }).catch(() => {});
}

// ------------------------------------------------------------------ large view
// Same layout, actions and keys as the batch large view (viewer.js, 23 Nov 2026): image on a stage with 1 : 1, full screen,
// the panel with thumbs, Keep, Remix, Variations, Change the style, Note for Claude, More like this and the details.
// It steps through the gallery's own list (or the Taste / "More like this" list it was opened from).
// Not here: Ignore (the gallery leaves ignored images out) and Hold S (images come from many batches).

// What each variation type keeps and changes (scripts/variations.py).
const CHANGES = {
  palette: 'Palette and light pulled to the style; subject and framing kept.',
  subject: 'New subject; palette, light and framing kept.',
  composition: 'New framing; palette and subject kept.',
  mood: 'Other time of day; subject and framing kept.',
};
const kindOf = (im) => im.change || (im.mode === 'text' ? 'from text' : im.mode) || '';
let fit = true;          // fit to the window, or 1:1 pixels
let skipCancel = false;  // Esc in the why field leaves the field, not the view
let trail = [];          // where "More like this" came from: Back (button, Esc, Backspace) returns there first

function ensureDialog() {
  if (dlg) return;
  dlg = h('dialog', { class: 'viewer glarge', 'aria-label': 'Large view', tabindex: '-1' });
  // Keys are heard on the whole window while the view is open (26 Nov 2026): a redraw can remove the focused
  // button (a mark, say), focus falls to the page body and a dialog-only listener went deaf until a click.
  window.addEventListener('keydown', (e) => { if (dlg.open) onKey(e); });
  dlg.addEventListener('cancel', (e) => {
    if (skipCancel) { e.preventDefault(); skipCancel = false; }
    else if (trail.length) { e.preventDefault(); back(); }
  });
  dlg.addEventListener('close', () => { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); flushWhy(); trail = []; if (urlSync) leaveUrl(); urlSync = false; });
  document.body.append(dlg);
}

// The address back to the grid: Back over the entry the opening added, or a plain swap after a reload or a link.
function leaveUrl() {
  if (!/^#\/gallery\/[^?]/.test(location.hash)) return;   // already elsewhere (a Style or Batch link)
  if (history.state?.glarge) history.back();
  else history.replaceState(null, '', galleryHref(curF));
}

// From the address (a link, reload, Forward): open on that image without a new history entry.
function openFromUrl(key) {
  let list = shown, i = shown.findIndex((im) => keyOf(im) === key);
  if (i < 0) { list = all; i = all.findIndex((im) => keyOf(im) === key); }   // hidden by the filters: step through every image
  if (i < 0) { history.replaceState(null, '', galleryHref(curF)); return toast('That image is no longer in the gallery.', { timeout: 3000 }); }
  if (dlg?.open && keyOf(stepList[index]) === key) return;
  if (dlg?.open) flushWhy();
  trail = [];
  urlSync = true;
  stepList = list;
  ensureDialog();
  index = i;
  draw();
  if (!dlg.open) dlg.showModal();
  dlg.focus();
}

// Leaving the Gallery for another page (Back past the grid, a header link) closes a view opened there.
export function closeGalleryLarge() {
  if (urlSync && dlg?.open) dlg.close();
}

export function openLarge(i, list) {
  if (dlg?.open) { flushWhy(); trail.push({ list: stepList, index }); }   // a "More like this" click inside the view
  else {
    trail = [];
    urlSync = location.hash.startsWith('#/gallery');
  }
  stepList = list || shown;   // the grid's list, or another one (Taste, "More like this"): the grid keeps its own
  ensureDialog();
  index = i;
  if (urlSync && !dlg.open) history.pushState({ glarge: true }, '', galleryHref(curF, stepList[i]));   // Back closes the view
  draw();
  if (!dlg.open) dlg.showModal();
  dlg.focus();
}

// One step back along the "More like this" trail, or close the view when there is none.
function back() {
  if (!trail.length) return dlg.close();
  flushWhy();
  ({ list: stepList, index } = trail.pop());
  draw();
  dlg.focus();
}

function step(d) {
  const n = Math.max(0, Math.min(stepList.length - 1, index + d));
  if (n === index) return;
  flushWhy();
  index = n;
  draw();
}

let markBox, keepBox, canvas, fitBtn;
function drawKeep(im) { keepBox.replaceChildren(keepButton(im, () => keep(im)), publishButton(im, () => publish(im))); }
function publish(im) {
  touch(im);
  setPublished(im, im.batch, !im.published).then(() => { refreshTile(im); if (dlg?.open && stepList[index] === im) drawKeep(im); }).catch(() => {});
}

function draw() {
  const im = stepList[index];
  const st = styleMap[im.style];
  const onGallery = location.hash.startsWith('#/gallery');
  if (urlSync) history.replaceState(history.state, '', galleryHref(curF, im));   // every step, "More like this" and Previous image
  canvas = h('div', { class: `canvas ${fit ? 'fit' : 'actual'}`, onClick: toggleFit },
    h('img', { src: imgUrl(im.batch, im.file, im.mtime), alt: `${st?.name || 'No style'}, ${ratingLabel(im.rating)}` }));
  dlg.replaceChildren(
    h('div', { class: 'stage' },
      h('div', { class: 'stage-bar' },
        trail.length
          ? h('button', { class: 'ghost', onClick: back, title: 'Esc: back to the image you came from' }, '← Previous image')
          : h('button', { class: 'ghost', onClick: () => dlg.close() }, '← ', onGallery ? 'Gallery' : 'Back'),
        h('span', { class: 'muted' }, `${index + 1} of ${stepList.length}`),
        h('span', { class: 'spacer' }),
        downloadLink(im.batch, im.file),
        fitBtn = h('button', { class: 'ghost', onClick: toggleFit, 'aria-pressed': String(!fit),
                               title: '1: real pixels (scroll to look around); press again to fit' }, '1 : 1'),
        fullscreenButton()),
      canvas,
      h('button', { class: 'nav prev', 'aria-label': 'Previous image', onClick: () => step(-1), disabled: index === 0 }, '‹'),
      h('button', { class: 'nav next', 'aria-label': 'Next image', onClick: () => step(1), disabled: index === stepList.length - 1 }, '›')),
    h('aside', { class: 'panel', 'aria-label': 'Details and rating' },
      h('header', { class: 'panel-head' },
        im.number && h('span', { class: 'num' }, im.number), h('h2', {}, st?.name || im.style || 'no style'),
        h('span', { class: 'kind', title: kindOf(im) }, kindOf(im))),
      markBox = h('section', { class: 'mark-box' }),
      h('section', { class: 'actions' },
        keepBox = h('span', { class: 'keep-box' }),
        h('button', { class: 'secondary outline', onClick: () => remixOf(im), title: 'More images from this one, in its style: pick what changes, how close, how many' }, 'Remix… ', h('kbd', {}, 'R')),
        im.style && h('button', { class: 'secondary outline', onClick: () => styleOf(im), title: 'Say what should change in this style; it applies to the next images' }, 'Change the style… ', h('kbd', {}, 'E')),
        h('button', { class: 'secondary outline', onClick: () => noteOn(im), title: 'Feedback for Claude: on this image or its style' }, 'Note for Claude… ', h('kbd', {}, 'C'))),
      similarRow(im, im.batch, !!im.style),
      historySection(im, im.batch),
      details(im, st),
      h('footer', { class: 'keys muted small' },
        h('kbd', {}, '←'), h('kbd', {}, '→'), ' move  ', h('kbd', {}, 'U'), h('kbd', {}, 'D'), ' up / down  ',
        h('kbd', {}, 'Enter'), ' why  ', h('kbd', {}, 'R'), ' or ', h('kbd', {}, 'V'), ' remix  ',
        h('kbd', {}, 'X'), ' keep as example  ', h('kbd', {}, 'P'), ' publish  ', h('kbd', {}, 'E'), ' change style  ', h('kbd', {}, 'C'), ' note  ',
        h('kbd', {}, '1'), ' real pixels  ', h('kbd', {}, 'F'), ' full screen  ', h('kbd', {}, 'Esc'), trail.length ? ' previous image' : ' close')));
  drawMarks(im);
  drawKeep(im);
  // Load the neighbours now, so the next arrow press shows the image at once.
  for (const n of [stepList[index - 1], stepList[index + 1]]) if (n) new Image().src = imgUrl(n.batch, n.file, n.mtime);
}

const label = (im) => `${batchTitle(im.batch)}${im.number ? ' #' + im.number : ''}`;
const remixOf = (im) => openRemix({ batch: im.batch, file: im.file, label: label(im), style: im.style, prompt: im.prompt });
const styleOf = (im) => im.style && openStyleEdit({ style: im.style, batch: im.batch, name: im.name, file: im.file, label: label(im) });
const noteOn = (im) => openNote({ batch: im.batch, name: im.name, file: im.file, label: label(im), style: im.style });

function details(im, st) {
  const rows = [
    ['Style', st ? h('span', {}, h('a', { href: '#/taste/' + encodeURIComponent(im.style), onClick: () => dlg.close() }, st.name),
      h('span', { class: 'swatches', 'aria-hidden': 'true' }, (st.palette || []).map((c) => h('i', { style: { background: c } })))) : '–'],
    ['Batch', h('a', { href: batchHref(im.batch), onClick: () => dlg.close() }, batchTitle(im.batch))],
    ['Change', im.change ? h('span', {}, h('strong', {}, im.change), h('br'), h('small', { class: 'muted' }, CHANGES[im.change] || '')) : '–'],
    ['Made with', im.model ? h('span', {}, modelTag(im.model), ' ', modelName(im.model)) : '–'],
    ['Made as', im.mode || '–'],
    ['Seed', im.seed || '–'],
    ['Size', im.width ? `${im.width} × ${im.height}` : '–'],
    ['Made', [im.date && shortDate(im.date), im.time, im.seconds && `${im.seconds} s`].filter(Boolean).join(' · ') || '–'],
  ];
  return h('section', { class: 'details' },
    h('dl', {}, rows.map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])),
    h('div', { class: 'prompt-head' }, h('span', {}, 'Prompt'),
      im.prompt && h('button', { class: 'ghost small', onClick: () => copy(im.prompt) }, 'Copy')),
    h('p', { class: 'prompt' }, im.prompt || 'No prompt in runs.csv for this image.'));
}

async function copy(text) {
  await navigator.clipboard.writeText(text);
  toast('Prompt copied', { timeout: 2000 });
}

function toggleFit() {
  fit = !fit;
  canvas.className = `canvas ${fit ? 'fit' : 'actual'}`;
  fitBtn.setAttribute('aria-pressed', String(!fit));
  if (!fit) canvas.scrollTo((canvas.scrollWidth - canvas.clientWidth) / 2, (canvas.scrollHeight - canvas.clientHeight) / 2);
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if ([...document.querySelectorAll('dialog[open]')].some((d) => d !== dlg && !d.matches('.viewer'))) return;   // a popup on top (remix, note…) has the keys; the batch viewer below doesn't
  if (isTyping(e)) {
    if (e.key === 'Escape') { skipCancel = true; e.target.blur(); setTimeout(() => { skipCancel = false; }, 0); }
    return;
  }
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const im = stepList[index];
  const rating = ratingForKey(key);
  if (rating) toggleMark(im, rating);
  else if (key === 'ArrowRight') step(1);
  else if (key === 'ArrowLeft') step(-1);
  else if (key === 'Home') step(-index);
  else if (key === 'End') step(stepList.length);
  else if (key === 'x') keep(im);
  else if (key === 'p') publish(im);
  else if (key === '1') toggleFit();
  else if (key === 'f') toggleFullscreen();
  else if (key === 'Backspace') back();
  else if (key === 'r') remixOf(im);
  else if (key === 'v') remixOf(im);   // V and R open the same dialog (habit)
  else if (key === 'e') styleOf(im);
  else if (key === 'c') noteOn(im);
  else if (key === 'Enter' && !e.target.closest('button, a')) markBox.querySelector('.why')?.focus();
  else return;
  e.preventDefault();
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
