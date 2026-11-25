// Large view: one image at full size, its details, and the marks. A modal <dialog>, so focus stays
// inside it, the page behind is inert, and Esc closes it.
import { store, item, styleName, kindOf, onChange, changed, visible } from './store.js';
import { toggleMark, setWhy, flushWhy, ignoreWithUndo, markButtons, setKept, keepButton, setPublished, publishButton } from './marks.js';
import { openVariations } from './variations.js';
import { openRemix } from './remix.js';
import { openNote } from './notes.js';
import { openStyleEdit } from './styleedit.js';
import { similarRow } from './similar.js';
import { historySection } from './history.js';
import { h, imgUrl, thumbUrl, batchHref, batchTitle, shortDate, RATING_LABELS, ratingForKey, markBadge, isTyping, toast, downloadLink, fullscreenButton, toggleFullscreen } from './ui.js';

// What each variation type keeps and changes (scripts/variations.py).
const CHANGES = {
  palette: 'Palette and light pulled to the style; subject and framing kept.',
  subject: 'New subject; palette, light and framing kept.',
  composition: 'New framing; palette and subject kept.',
  mood: 'Other time of day; subject and framing kept.',
};

let dlg, img, seedTag, bar, panel, prevBtn, nextBtn, canvas;
let order = [];        // names to step through: the grid's list when the view opened
let index = 0;
let fit = true;        // fit to the window, or 1:1 pixels
let skipCancel = false;

export const viewerHref = (name) =>
  `#/b/${encodeURIComponent(store.data.batch)}/${encodeURIComponent(name)}?show=${store.show}`;
const current = () => item(order[index]);

function build() {
  canvas = h('div', { class: 'canvas fit', onClick: toggleFit },
    img = h('img', { alt: '' }),
    seedTag = h('span', { class: 'seed-tag', hidden: true }, 'Seed'));
  dlg = h('dialog', { class: 'viewer', 'aria-label': 'Large view', tabindex: '-1' },
    h('div', { class: 'stage' },
      bar = h('div', { class: 'stage-bar' }),
      canvas,
      prevBtn = h('button', { class: 'nav prev', 'aria-label': 'Previous image', onClick: () => go(-1) }, '‹'),
      nextBtn = h('button', { class: 'nav next', 'aria-label': 'Next image', onClick: () => go(1) }, '›')),
    panel = h('aside', { class: 'panel', 'aria-label': 'Details and rating' }));
  dlg.addEventListener('cancel', (e) => {   // Esc
    e.preventDefault();
    if (skipCancel) { skipCancel = false; return; }
    requestClose();
  });
  // Keys are heard on the whole window while the view is open, so they work wherever the focus is.
  window.addEventListener('keydown', (e) => { if (dlg.open) onKey(e); });
  window.addEventListener('keyup', (e) => { if (dlg.open && e.key.toLowerCase() === 's') showSeed(false); });
  window.addEventListener('blur', () => showSeed(false));
  document.body.append(dlg);
}

// push: true when opened from the grid, so the browser's Back button closes the view.
export function openViewer(name, { push = false } = {}) {
  if (!item(name)) return;
  if (!dlg) build();
  if (push) history.pushState({ viewer: true }, '', viewerHref(name));
  if (!dlg.open || !order.includes(name)) {
    const names = visible().map((im) => im.name);
    order = names.includes(name) ? names : store.data.items.map((im) => im.name);   // not in this filter: step through the whole batch
  }
  index = order.indexOf(name);
  const opening = !dlg.open;
  if (opening) dlg.showModal();
  draw();
  if (opening) dlg.focus();   // the dialog itself, not a button that the next draw may replace
}

// refocus: false when leaving for another page, so the grid behind does not scroll to the tile.
// Returns true when the view was open.
export function closeViewer({ refocus = true } = {}) {
  if (!dlg?.open) return false;
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  const name = order[index];
  flushWhy();
  showSeed(false);
  dlg.close();
  if (refocus) document.querySelector(`.tile[data-name="${CSS.escape(name)}"]`)?.focus({ preventScroll: false });
  return true;
}

function requestClose() {
  if (history.state?.viewer) history.back();   // the router then calls closeViewer()
  else {
    history.replaceState(null, '', batchHref(store.data.batch, store.show));
    closeViewer();
  }
}

function go(step) {
  const next = Math.max(0, Math.min(order.length - 1, index + step));
  if (next === index) return;
  flushWhy();
  index = next;
  history.replaceState(history.state, '', viewerHref(order[index]));
  draw();
}

// ------------------------------------------------------------------ drawing

function draw() {
  const im = current();
  if (!im) return requestClose();
  const d = store.data;
  img.src = imgUrl(d.batch, im.file, im.mtime);
  img.alt = `${im.number}. ${styleName(im.style)}, ${kindOf(im)}`;
  canvas.className = `canvas ${fit ? 'fit' : 'actual'}`;
  prevBtn.disabled = index === 0;
  nextBtn.disabled = index === order.length - 1;
  bar.replaceChildren(...[   // replaceChildren would print "null": drop the empty parts first
    h('a', { class: 'home', href: '#/' }, 'Batches'),   // the header is hidden behind the view: the way home
    h('span', { class: 'muted', 'aria-hidden': 'true' }, '›'),
    h('button', { class: 'ghost batch-name', onClick: requestClose, title: 'Back to the batch (Esc)' }, batchTitle(d.batch)),
    h('span', { class: 'muted' }, `${index + 1} of ${order.length}`),
    h('span', { class: 'spacer' }),
    d.seed && h('span', { class: 'muted small' }, 'Hold ', h('kbd', {}, 'S'), ' to see the seed'),
    downloadLink(d.batch, im.file),
    // One steady label with a pressed state: "Fit" named the state, so it read like an action that did nothing.
    h('button', { class: 'ghost', onClick: toggleFit, 'aria-pressed': String(!fit),
                  title: '1: real pixels (scroll to look around); press again to fit' }, '1 : 1'),
    fullscreenButton()].filter(Boolean));
  drawPanel(im);
  // Load the neighbours now, so the next arrow press shows the image at once.
  for (const j of [index - 1, index + 1]) {
    const n = item(order[j]);
    if (n) new Image().src = imgUrl(d.batch, n.file, n.mtime);
  }
}

function drawPanel(im) {
  panel.replaceChildren(
    h('header', { class: 'panel-head' },
      h('span', { class: 'num' }, im.number), h('h2', {}, styleName(im.style)),
      h('span', { class: 'kind', title: kindOf(im) }, kindOf(im))),
    markSection(im),
    actions(im),
    similarRow(im, store.data.batch, !!im.style),
    historySection(im, store.data.batch),
    details(im),
    h('footer', { class: 'keys muted small' },
      h('kbd', {}, '←'), h('kbd', {}, '→'), ' move  ', h('kbd', {}, 'U'), h('kbd', {}, 'D'),
      ' up / down  ', h('kbd', {}, 'Enter'), ' why  ', h('kbd', {}, 'I'), ' ignore  ', h('kbd', {}, 'R'), ' remix  ', h('kbd', {}, 'V'), ' variations  ',
      h('kbd', {}, 'X'), ' keep as example  ', h('kbd', {}, 'P'), ' publish  ', h('kbd', {}, 'E'), ' change style  ', h('kbd', {}, 'C'), ' note  ', h('kbd', {}, '1'), ' real pixels  ',
      h('kbd', {}, 'F'), ' full screen  ', h('kbd', {}, 'Esc'), ' close'));
}

function markSection(im) {
  if (im.saved) {
    return h('section', { class: 'mark-box' },
      h('p', { class: 'saved-note' }, markBadge(im), ' ',
        h('strong', {}, RATING_LABELS[im.saved.rating].label), im.saved.why && ` – ${im.saved.why}`),
      h('p', { class: 'muted small' }, `Saved on ${shortDate(im.saved.date)}. Saved ratings are read-only.`));
  }
  const r = im.draft?.rating;
  const st = styleName(im.style);
  const parts = { light: 'light', composition: 'framing', mood: 'mood', palette: 'palette', detail: 'detail' };
  const moved = (im.moves || []).map((k) => parts[k] || k);
  const list = moved.length > 1 ? `${moved.slice(0, -1).join(', ')} and ${moved.at(-1)}` : moved[0];
  const status = im.status === 'ignored' ? 'Ignored: hidden from the grid and left out of ratings.'
    : !r ? 'Not marked yet. A mark counts at once and steers the next runs of this style.'
    : (r === 'keep' ? 'Saved. ' : 'Saved. ') + (list
      ? `New ${st} runs lean ${r === 'keep' ? 'toward' : 'away from'} this image's ${list}, and its subject.`
      : `Counts for ${st}. Press the same thumb again to take it back.`);
  return h('section', { class: 'mark-box' },
    markButtons(im),
    h('input', {
      type: 'text', class: 'why', value: im.draft?.why || '', maxlength: 300, 'aria-label': 'Why',
      placeholder: 'Why? a few words (optional)', disabled: im.status === 'ignored',
      onInput: (e) => setWhy(im.name, e.target.value),
      onKeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); go(1); } },
    }),
    h('p', { class: 'muted small status' }, status));
}

function actions(im) {
  return h('section', { class: 'actions' },
    keepButton(im, () => keepOf(im)),
    publishButton(im, () => publishOf(im)),
    h('button', { class: 'secondary outline', onClick: () => remixOf(im), title: 'Say what should change; Codex rewrites the prompt' }, 'Remix… ', h('kbd', {}, 'R')),
    h('button', { class: 'secondary outline', onClick: () => variationsOf(im) }, 'Variations… ', h('kbd', {}, 'V')),
    im.style && h('button', { class: 'secondary outline', onClick: () => styleOf(im), title: 'Say what should change in this style; it applies to the next images' }, 'Change the style… ', h('kbd', {}, 'E')),
    h('button', { class: 'secondary outline', onClick: () => noteOn(im), title: 'Feedback for Claude: on this image or its style' }, 'Note for Claude… ', h('kbd', {}, 'C')),
    !im.draft?.rating && h('button', { class: 'secondary outline', onClick: () => ignoreAndMove(im.name) },
      im.status === 'ignored' ? 'Restore' : 'Ignore', ' ', h('kbd', {}, 'I')));
}

const keepOf = (im) => setKept(im, store.data.batch, !im.kept).then(() => drawPanel(im)).catch(() => {});
// changed() redraws this panel and the grid tile underneath.
const publishOf = (im) => setPublished(im, store.data.batch, !im.published).then(() => changed(im.name, 'publish')).catch(() => {});
const variationsOf = (im) => openVariations({ batch: store.data.batch, file: im.file, label: `#${im.number}`, style: im.style });
const remixOf = (im) => openRemix({ batch: store.data.batch, file: im.file, label: `#${im.number}`, style: im.style, prompt: im.prompt });
const styleOf = (im) => im.style && openStyleEdit({ style: im.style, batch: store.data.batch, name: im.name, file: im.file, label: `#${im.number}` });
const noteOn = (im) => openNote({ batch: store.data.batch, name: im.name, file: im.file, label: `#${im.number}`, style: im.style });

// Batches made from this image (variations, remixes), newest last: where its "children" went.
function madeFromThis(im) {
  const kids = (store.data.children || []).filter((c) => c.file === im.file);
  if (!kids.length) return '–';
  return h('ul', { class: 'plain kid-links' }, kids.map((c) => h('li', {},
    h('a', { href: batchHref(c.batch) }, `${c.kind === 'remix' ? 'Remix' : 'Variations'} · ${batchTitle(c.batch)}`),
    h('small', { class: 'muted' }, ` (${c.images})`))));
}

function details(im) {
  const st = store.styles[im.style];
  const rows = [
    ['Style', h('span', {}, styleName(im.style), st && h('span', { class: 'swatches', 'aria-hidden': 'true' },
      st.palette.map((c) => h('i', { style: { background: c } }))))],
    ['Change', im.change ? h('span', {}, h('strong', {}, im.change), h('br'), h('small', { class: 'muted' }, CHANGES[im.change] || '')) : '–'],
    ['Made as', im.mode || '–'],
    ['Made from this', madeFromThis(im)],
    ['Seed', im.seed ? h('span', { class: 'seed-cell' },
      store.data.seed && h('img', { src: thumbUrl(store.data.batch, store.data.seed), alt: '' }), im.seed) : '–'],
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

// The current item changed (mark, ignore): redraw the panel, but never under the cursor of the "why" field.
onChange((name, kind) => {
  if (!dlg?.open || name !== order[index] || kind === 'why') return;
  drawPanel(current());
});

// ------------------------------------------------------------------ actions and keys

function ignoreAndMove(name) {
  const ignoring = item(name).status !== 'ignored';
  ignoreWithUndo(name);
  if (ignoring && index < order.length - 1) go(1);   // hidden now: move on, the toast offers Undo
}

function toggleFit() {
  fit = !fit;
  draw();
  if (!fit) canvas.scrollTo((canvas.scrollWidth - canvas.clientWidth) / 2, (canvas.scrollHeight - canvas.clientHeight) / 2);
}

// Hold S: the seed replaces the image until the key is released. Flicking between two images in place
// makes differences jump out (change detection), better than looking left and right.
function showSeed(on) {
  const d = store.data;
  if (!dlg?.open || !d?.seed || seedTag.hidden === !on) return;
  seedTag.hidden = !on;
  const im = current();
  img.src = on ? imgUrl(d.batch, d.seed) : imgUrl(d.batch, im.file, im.mtime);
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if ([...document.querySelectorAll('dialog[open]')].some((d) => d !== dlg)) return;   // another dialog on top (or the Gallery large view) has the keys
  if (isTyping(e)) {
    // Esc in the field leaves the field, not the view. (Some browsers still fire "cancel"; skip that one.)
    if (e.key === 'Escape') { skipCancel = true; e.target.blur(); setTimeout(() => { skipCancel = false; }, 0); }
    return;
  }
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const im = current();
  const rating = ratingForKey(key);
  if (rating) toggleMark(im.name, rating);
  else if (key === 'ArrowRight') go(1);
  else if (key === 'ArrowLeft') go(-1);
  else if (key === 'Home') go(-index);
  else if (key === 'End') go(order.length);
  else if (key === 'x') keepOf(im);
  else if (key === 'p') publishOf(im);
  else if (key === 'i') { if (!im.draft?.rating) ignoreAndMove(im.name); }
  else if (key === '1') toggleFit();
  else if (key === 'f') toggleFullscreen();
  else if (key === 'v') variationsOf(im);
  else if (key === 'r') remixOf(im);
  else if (key === 'c') noteOn(im);
  else if (key === 'e') styleOf(im);
  else if (key === 's') { if (!e.repeat) showSeed(true); }
  else if (key === 'Enter' && !e.target.closest('button, a')) panel.querySelector('.why:not([disabled])')?.focus();
  else return;
  e.preventDefault();
}
