// Large view: one image at full size, its details, and the marks. A modal <dialog>, so focus stays
// inside it, the page behind is inert, and Esc closes it.
import { store, item, styleName, kindOf, onChange, visible } from './store.js';
import { toggleMark, setWhy, flushWhy, ignoreWithUndo } from './marks.js';
import { h, imgUrl, thumbUrl, batchHref, batchTitle, shortDate, RATINGS, markBadge, isTyping, toast } from './ui.js';

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
    order = names.includes(name) ? names : [name];
  }
  index = order.indexOf(name);
  const opening = !dlg.open;
  if (opening) dlg.showModal();
  draw();
  if (opening) dlg.focus();   // the dialog itself, not a button that the next draw may replace
}

export function closeViewer() {
  if (!dlg?.open) return;
  const name = order[index];
  flushWhy();
  showSeed(false);
  dlg.close();
  document.querySelector(`.tile[data-name="${CSS.escape(name)}"]`)?.focus({ preventScroll: false });
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
  bar.replaceChildren(
    h('button', { class: 'ghost', onClick: requestClose }, '← ', batchTitle(d.batch)),
    h('span', { class: 'muted' }, `${index + 1} of ${order.length}`),
    h('span', { class: 'spacer' }),
    d.seed && h('span', { class: 'muted small' }, 'Hold ', h('kbd', {}, 'S'), ' to see the seed'),
    h('button', { class: 'ghost', onClick: toggleFit, 'aria-pressed': String(!fit),
                  title: 'F: fit to the window or show real pixels' }, fit ? 'Fit' : '1 : 1'));
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
      h('span', { class: 'kind' }, kindOf(im))),
    markSection(im),
    actions(im),
    details(im),
    h('footer', { class: 'keys muted small' },
      h('kbd', {}, '←'), h('kbd', {}, '→'), ' move  ', h('kbd', {}, 'K'), h('kbd', {}, 'A'), h('kbd', {}, 'N'),
      ' mark  ', h('kbd', {}, 'Enter'), ' why  ', h('kbd', {}, 'I'), ' ignore  ', h('kbd', {}, 'F'), ' 1:1  ',
      h('kbd', {}, 'Esc'), ' close'));
}

function markSection(im) {
  if (im.saved) {
    return h('section', { class: 'mark-box' },
      h('p', { class: 'saved-note' }, markBadge(im), ' ',
        h('strong', {}, RATINGS[im.saved.rating].label), im.saved.why && ` – ${im.saved.why}`),
      h('p', { class: 'muted small' }, `Saved on ${shortDate(im.saved.date)}. Saved ratings are read-only.`));
  }
  const r = im.draft?.rating;
  const status = im.status === 'ignored' ? 'Ignored: hidden from the grid and left out of ratings.'
    : r ? 'Draft: kept on this computer until you save the batch.' : 'Not marked yet.';
  return h('section', { class: 'mark-box' },
    h('div', { role: 'group', class: 'marks', 'aria-label': 'Mark' },
      Object.entries(RATINGS).map(([key, m]) => h('button', {
        class: `mark-btn ${key}`, 'aria-pressed': String(r === key), disabled: im.status === 'ignored',
        onClick: () => toggleMark(im.name, key),
      }, h('kbd', {}, m.key.toUpperCase()), m.label))),
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
    !im.saved && h('button', { class: 'secondary outline', onClick: () => ignoreAndMove(im.name) },
      im.status === 'ignored' ? 'Restore' : 'Ignore', ' ', h('kbd', {}, 'I')));
}

function details(im) {
  const st = store.styles[im.style];
  const rows = [
    ['Style', h('span', {}, styleName(im.style), st && h('span', { class: 'swatches', 'aria-hidden': 'true' },
      st.palette.map((c) => h('i', { style: { background: c } }))))],
    ['Change', im.change ? h('span', {}, h('strong', {}, im.change), h('br'), h('small', { class: 'muted' }, CHANGES[im.change] || '')) : '–'],
    ['Made as', im.mode || '–'],
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
  if (isTyping(e)) {
    // Esc in the field leaves the field, not the view. (Some browsers still fire "cancel"; skip that one.)
    if (e.key === 'Escape') { skipCancel = true; e.target.blur(); setTimeout(() => { skipCancel = false; }, 0); }
    return;
  }
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const im = current();
  const rating = Object.keys(RATINGS).find((r) => RATINGS[r].key === key);
  if (rating) toggleMark(im.name, rating);
  else if (key === 'ArrowRight') go(1);
  else if (key === 'ArrowLeft') go(-1);
  else if (key === 'Home') go(-index);
  else if (key === 'End') go(order.length);
  else if (key === 'i') { if (!im.saved) ignoreAndMove(im.name); }
  else if (key === 'f') toggleFit();
  else if (key === 's') { if (!e.repeat) showSeed(true); }
  else if (key === 'Enter' && !e.target.closest('button, a')) panel.querySelector('.why:not([disabled])')?.focus();
  else return;
  e.preventDefault();
}
