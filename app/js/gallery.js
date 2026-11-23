// Gallery: every generated image in justified rows (like Flickr), filtered by words, style, rating and batch.
// The large view has the same thumbs as the batch view (21 Nov 2026): a mark is saved at once and counts
// for the style's next runs; the same thumb again takes it back. Filters are not re-applied while you mark,
// so nothing jumps away under the pointer.
//   #/gallery?q=<words>&style=<key>&rating=keep|no|almost|none (keep = up, no = down, almost = older ratings)&batch=<batch>
// Find (23 Nov 2026): every word must appear in the prompt, the why, the style name, the batch or the variation.
// Typing redraws only the grid and the count (the field keeps its cursor); the address follows without a reload.
// Rows: each tile grows in proportion to its width / height, so every row fills the width at one shared
// height and no image is cropped. A last invisible filler stops the final row from stretching.
import { api, styles } from './api.js';
import { openStyleEdit } from './styleedit.js';
import { setKept, keepButton } from './marks.js';
import { openRemix } from './remix.js';
import { openVariations } from './variations.js';
import { openNote } from './notes.js';
import { similarRow } from './similar.js';
import { h, imgUrl, thumbUrl, batchHref, batchTitle, shortDate, plural, RATINGS, RATING_LABELS, ratingForKey, showError, isTyping, toast } from './ui.js';

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
  const f = { q: query.get('q') || '', style: query.get('style') || '', rating: query.get('rating') || '', batch: query.get('batch') || '' };
  const base = all.filter((im) =>
    (!f.style || im.style === f.style) &&
    (!f.rating || (f.rating === 'none' ? !im.rating : im.rating === f.rating)) &&
    (!f.batch || im.batch === f.batch));

  if (!all.length) {
    return view.replaceChildren(h('div', { class: 'empty' }, h('h1', {}, 'No images yet'),
      h('p', { class: 'muted' }, 'Images made through Codex show here once a batch exists in generated/codex/.')));
  }

  const count = h('p', {});
  const grid = h('div', {});
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
    history.replaceState(null, '', galleryHref(f));   // no hashchange: the page is not read again
    draw();
  };
  draw();
  view.replaceChildren(h('hgroup', { class: 'page-head' }, h('h1', {}, 'Gallery'), count), filters(f, onFind), grid);
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

function filters(f, onFind) {
  const set = (k, v) => { location.hash = galleryHref({ ...f, [k]: v }); };
  const count = (pred) => all.filter(pred).length;
  const styleKeys = [...new Set(all.map((im) => im.style).filter(Boolean))]
    .sort((a, b) => (styleMap[a]?.name || a).localeCompare(styleMap[b]?.name || b));
  const batches = [...new Set(all.map((im) => im.batch))].sort().reverse();
  const ratings = [['', 'All'], ['keep', 'Up'], ['no', 'Down'], ['almost', 'Almost (old)'], ['none', 'Not rated']];
  return h('div', { class: 'gallery-filters' },
    h('input', { type: 'search', class: 'find', placeholder: 'Find words in prompts, notes, styles', value: f.q,
      'aria-label': 'Find images', onInput: (e) => onFind(e.target.value) }),
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
// Same layout, actions and keys as the batch large view (viewer.js, 23 Nov 2026): image on a stage with Fit / 1 : 1,
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

function ensureDialog() {
  if (dlg) return;
  dlg = h('dialog', { class: 'viewer glarge', 'aria-label': 'Large view', tabindex: '-1' });
  dlg.addEventListener('keydown', onKey);
  dlg.addEventListener('cancel', (e) => { if (skipCancel) { e.preventDefault(); skipCancel = false; } });
  dlg.addEventListener('close', flushWhy);
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
  const n = Math.max(0, Math.min(stepList.length - 1, index + d));
  if (n === index) return;
  flushWhy();
  index = n;
  draw();
}

let markBox, keepBox, canvas, fitBtn;
function drawKeep(im) { keepBox.replaceChildren(keepButton(im, () => keep(im))); }

function draw() {
  const im = stepList[index];
  const st = styleMap[im.style];
  const onGallery = location.hash.startsWith('#/gallery');
  canvas = h('div', { class: `canvas ${fit ? 'fit' : 'actual'}`, onClick: toggleFit },
    h('img', { src: imgUrl(im.batch, im.file, im.mtime), alt: `${st?.name || 'No style'}, ${ratingLabel(im.rating)}` }));
  dlg.replaceChildren(
    h('div', { class: 'stage' },
      h('div', { class: 'stage-bar' },
        h('button', { class: 'ghost', onClick: () => dlg.close() }, '← ', onGallery ? 'Gallery' : 'Back'),
        h('span', { class: 'muted' }, `${index + 1} of ${stepList.length}`),
        h('span', { class: 'spacer' }),
        fitBtn = h('button', { class: 'ghost', onClick: toggleFit, 'aria-pressed': String(!fit),
                               title: 'F: fit to the window or show real pixels' }, fit ? 'Fit' : '1 : 1')),
      canvas,
      h('button', { class: 'nav prev', 'aria-label': 'Previous image', onClick: () => step(-1), disabled: index === 0 }, '‹'),
      h('button', { class: 'nav next', 'aria-label': 'Next image', onClick: () => step(1), disabled: index === stepList.length - 1 }, '›')),
    h('aside', { class: 'panel', 'aria-label': 'Details and rating' },
      h('header', { class: 'panel-head' },
        im.number && h('span', { class: 'num' }, im.number), h('h2', {}, st?.name || im.style || 'no style'),
        h('span', { class: 'kind' }, kindOf(im))),
      markBox = h('section', { class: 'mark-box' }),
      h('section', { class: 'actions' },
        keepBox = h('span', { class: 'keep-box' }),
        h('button', { class: 'secondary outline', onClick: () => remixOf(im), title: 'Say what should change; Codex rewrites the prompt' }, 'Remix… ', h('kbd', {}, 'R')),
        h('button', { class: 'secondary outline', onClick: () => variationsOf(im) }, 'Variations… ', h('kbd', {}, 'V')),
        im.style && h('button', { class: 'secondary outline', onClick: () => styleOf(im), title: 'Say what should change in this style; it applies to the next images' }, 'Change the style… ', h('kbd', {}, 'E')),
        h('button', { class: 'secondary outline', onClick: () => noteOn(im), title: 'Feedback for Claude: on this image or its style' }, 'Note for Claude… ', h('kbd', {}, 'C'))),
      similarRow(im, im.batch, !!im.style),
      details(im, st),
      h('footer', { class: 'keys muted small' },
        h('kbd', {}, '←'), h('kbd', {}, '→'), ' move  ', h('kbd', {}, 'U'), h('kbd', {}, 'D'), ' up / down  ',
        h('kbd', {}, 'Enter'), ' why  ', h('kbd', {}, 'R'), ' remix  ', h('kbd', {}, 'V'), ' variations  ',
        h('kbd', {}, 'X'), ' keep as example  ', h('kbd', {}, 'E'), ' change style  ', h('kbd', {}, 'C'), ' note  ',
        h('kbd', {}, 'F'), ' 1:1  ', h('kbd', {}, 'Esc'), ' close')));
  drawMarks(im);
  drawKeep(im);
  // Load the neighbours now, so the next arrow press shows the image at once.
  for (const n of [stepList[index - 1], stepList[index + 1]]) if (n) new Image().src = imgUrl(n.batch, n.file, n.mtime);
}

const label = (im) => `${batchTitle(im.batch)}${im.number ? ' #' + im.number : ''}`;
const remixOf = (im) => openRemix({ batch: im.batch, file: im.file, label: label(im), style: im.style, prompt: im.prompt });
const variationsOf = (im) => openVariations({ batch: im.batch, file: im.file, label: label(im), style: im.style });
const styleOf = (im) => im.style && openStyleEdit({ style: im.style, batch: im.batch, name: im.name, file: im.file, label: label(im) });
const noteOn = (im) => openNote({ batch: im.batch, name: im.name, file: im.file, label: label(im), style: im.style });

function details(im, st) {
  const rows = [
    ['Style', st ? h('span', {}, h('a', { href: '#/taste/' + encodeURIComponent(im.style), onClick: () => dlg.close() }, st.name),
      h('span', { class: 'swatches', 'aria-hidden': 'true' }, (st.palette || []).map((c) => h('i', { style: { background: c } })))) : '–'],
    ['Batch', h('a', { href: batchHref(im.batch), onClick: () => dlg.close() }, batchTitle(im.batch))],
    ['Change', im.change ? h('span', {}, h('strong', {}, im.change), h('br'), h('small', { class: 'muted' }, CHANGES[im.change] || '')) : '–'],
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
  fitBtn.replaceChildren(fit ? 'Fit' : '1 : 1');
  fitBtn.setAttribute('aria-pressed', String(!fit));
  if (!fit) canvas.scrollTo((canvas.scrollWidth - canvas.clientWidth) / 2, (canvas.scrollHeight - canvas.clientHeight) / 2);
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
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
  else if (key === 'f') toggleFit();
  else if (key === 'r') remixOf(im);
  else if (key === 'v') variationsOf(im);
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
