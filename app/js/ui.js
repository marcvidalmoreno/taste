// Small helpers shared by every view. No framework.

// h('a', {href: '#/', class: 'x', onClick: fn}, 'text', child) -> an element.
// Building nodes (instead of HTML strings) means prompts and names are always shown as text, never as markup.
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c != null && c !== false) el.append(c instanceof Node ? c : String(c));
  }
  return el;
}

const enc = encodeURIComponent;
// ?v=<mtime>: the server lets the browser keep images; a changed file gets a new URL.
export const imgUrl = (batch, file, v = 0) => `/img/${enc(batch)}/${enc(file)}?v=${v}`;
// Download links (23 Nov 2026). Same origin, so the "download" attribute names the saved file:
// '<batch>-<file>', unique across batches. A zip holds the files given, or the whole batch.
export const downloadLink = (batch, file, text = 'Download', cls = 'ghost') =>
  h('a', { class: cls, href: `/img/${enc(batch)}/${enc(file)}`, download: `${batch}-${file}`, title: 'Save the full-size image' }, text);
export const zipUrl = (batch, files) => `/zip/${enc(batch)}${files ? '?files=' + files.map(enc).join(',') : ''}`;
export const thumbUrl = (batch, file, v = 0) => `/thumb/${enc(batch)}/${enc(file)}?v=${v}`;
export const batchHref = (batch, show) => `#/b/${enc(batch)}${show ? '?show=' + show : ''}`;

// '2026-11-13-linkedin-handshake' -> 'linkedin handshake'
export const batchTitle = (b) => (/^\d{4}-\d\d-\d\d-/.test(b) ? b.slice(11) : b).replace(/-/g, ' ');

// '2026-11-13' -> '13 Nov'
export function shortDate(iso) {
  const d = new Date(iso + 'T12:00');
  return isNaN(d) ? iso : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

export const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;

// The two marks (thumbs up / down since 18 Nov 2026). Stored values stay 'keep' and 'no', so older ratings
// read the same. Glyph + word + colour, so the meaning never rests on colour alone. K and N still work.
export const RATINGS = {
  keep: { label: 'Up', glyph: '👍', key: 'u', alt: 'k' },
  no: { label: 'Down', glyph: '👎', key: 'd', alt: 'n' },
};
// For showing saved ratings: the two marks plus 'almost', which older ratings (before 18 Nov 2026) may have.
export const RATING_LABELS = { ...RATINGS, almost: { label: 'Almost (old)', glyph: 'A' } };
export const ratingForKey = (k) => Object.keys(RATINGS).find((r) => RATINGS[r].key === k || RATINGS[r].alt === k);

// Small 👍 / 👎 badge on a marked image (every mark is saved at once since 21 Nov 2026).
export function markBadge(im) {
  const r = im.saved?.rating || im.draft?.rating;
  if (!r) return null;
  return h('span', { class: `mark ${r} saved`, title: `${RATING_LABELS[r].label} (saved)` }, RATING_LABELS[r].glyph);
}

// Full screen for the large views (24 Nov 2026): F, like most video and photo viewers. The whole page goes full
// screen (Chrome refuses a <dialog> itself); the open view already covers it, so stepping and redraws keep it.
// CSS hides the side panel there. The browser's own Esc leaves it.
export const toggleFullscreen = () =>
  (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch(() => {});
const fsLabel = () => (document.fullscreenElement ? 'Exit full screen' : 'Full screen');
export const fullscreenButton = () =>
  h('button', { class: 'ghost fs-btn', onClick: toggleFullscreen, title: 'F: full screen (Esc leaves it)' }, fsLabel());
document.addEventListener('fullscreenchange', () =>
  document.querySelectorAll('.fs-btn').forEach((b) => b.replaceChildren(fsLabel())));

// A key press in a text field is typing, not a shortcut.
export const isTyping = (e) => !!e.target.closest?.('input, textarea, select, [contenteditable]');

// Toasts stay clickable over a modal dialog (23 Nov 2026): an open modal makes everything outside it inert, the
// top layer included, so toasts showed on top but their buttons did nothing. The toast area moves into the open
// modal and back to the page when it closes (or is removed).
const toastBox = document.getElementById('toasts');
function placeToasts() {
  const host = [...document.querySelectorAll('dialog[open]')].filter((d) => d.matches(':modal')).at(-1) || document.body;
  if (toastBox.parentElement === host && toastBox.isConnected) return;
  host.append(toastBox);   // moving it closes the popover: open it again if it holds toasts
  if (toastBox.children.length && !toastBox.matches(':popover-open')) toastBox.showPopover();
}
new MutationObserver(() => { placeToasts(); addCloseButtons(); })
  .observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['open'] });

// Popups close the same way everywhere (26 Nov 2026): a × at the top right (one known place, instead of a
// Cancel that moved between footers), Esc (the browser's own), and a click outside. The large views (.viewer)
// are full-screen pages with their own Back, so they keep their own rules.
// A click outside with text typed in the popup does not close it: a stray click should never lose writing;
// a toast says how to close it on purpose.
const POPUP = 'dialog:not(.viewer)';
function addCloseButtons() {
  for (const dlg of document.querySelectorAll(POPUP)) {
    const art = dlg.querySelector(':scope > article');
    if (!art || art.querySelector(':scope > .dlg-x')) continue;
    art.prepend(h('button', { type: 'button', class: 'dlg-x', 'aria-label': 'Close', title: 'Close (Esc)', onClick: () => dlg.close() }, '×'));
  }
}
document.addEventListener('input', (e) => { const d = e.target.closest?.(POPUP); if (d && isTyping(e)) d.dataset.typed = '1'; }, true);
let downOn = null;   // a drag that starts inside (selecting text) and ends outside is not a click outside
document.addEventListener('pointerdown', (e) => { downOn = e.target; }, true);
document.addEventListener('click', (e) => {
  const dlg = e.target;
  if (!(dlg instanceof HTMLDialogElement) || !dlg.open || !dlg.matches(POPUP) || downOn !== dlg) return;
  const box = dlg.querySelector(':scope > article')?.getBoundingClientRect();
  if (box && e.clientX >= box.left && e.clientX <= box.right && e.clientY >= box.top && e.clientY <= box.bottom) return;
  if (dlg.dataset.typed) return toast('Kept open so your text is not lost: × or Esc closes it.', { timeout: 3500 });
  dlg.close();
});

// Toasts: one line, optional action button (e.g. Undo). Calm: most leave on their own; every one has a × to close it.
// onClose runs however it closes (×, its button, timeout, or the close function this returns).
export function toast(message, { action, onAction, onClose, timeout = 5000, tone = '' } = {}) {
  placeToasts();
  const box = toastBox;
  let done = false;
  const close = () => {
    if (done) return;
    done = true;
    el.remove();
    if (!box.children.length && box.matches(':popover-open')) box.hidePopover();
    onClose?.();
  };
  const el = h('div', { class: `toast ${tone}` },
    h('span', {}, message),
    action && h('button', { class: 'secondary outline', onClick: () => { close(); onAction(); } }, action),
    h('button', { class: 'toast-close', 'aria-label': 'Close this message', title: 'Close', onClick: close }, '×'));
  box.append(el);
  // The toast area is a popover: shown again on each toast, it sits in the top layer above any open dialog
  // (and inside a modal one, see placeToasts, so its buttons work there).
  if (box.matches(':popover-open')) box.hidePopover();
  box.showPopover();
  if (timeout) setTimeout(close, timeout);
  return close;
}

export const showError = (err) => toast(String(err.message || err), { tone: 'error', timeout: 8000 });

// Character counter (27 Nov 2026). Every text box with a limit of 150+ characters (Change the style 400, the prompt
// boxes 4000…) shows "368 / 400" once the text fills 60 % of it, amber from 90 %. A paste that does not fit says so
// ("cut at 400: 37 didn't fit"), because the browser drops the rest without a word. One listener for the whole app,
// so new dialogs get it without code of their own; the counter sits under the field's right edge.
const COUNT_MIN = 150;
const counted = (el) => el && el.maxLength >= COUNT_MIN && (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && el.type === 'text'));

function counterFor(el) {
  let c = el.nextElementSibling;
  if (c?.classList.contains('char-count')) return c;
  c = h('small', { class: 'char-count', 'aria-live': 'polite', hidden: true });
  const mb = parseFloat(getComputedStyle(el).marginBottom) || 0;
  if (mb >= 12) Object.assign(c.style, { marginTop: `${4 - mb}px`, marginBottom: `${mb - 16}px` });   // sit in the field's own gap
  el.after(c);
  return c;
}

function drawCount(el, cut = 0) {
  const max = el.maxLength, n = el.value.length;
  if (!cut && n < max * 0.6 && !el.nextElementSibling?.classList.contains('char-count')) return;
  const c = counterFor(el);
  c.hidden = !cut && n < max * 0.6;
  c.classList.toggle('near', !!cut || n >= max * 0.9);
  c.textContent = cut ? `${n} / ${max}: cut at ${max}, ${cut} didn't fit` : `${n} / ${max}`;
}

document.addEventListener('input', (e) => {
  const el = e.target;
  if (!counted(el) || (e.inputType === 'insertFromPaste' && el._cut)) return;   // the paste's own redraw says what was cut
  el._cut = 0;
  drawCount(el);
}, true);
document.addEventListener('focusin', (e) => { if (counted(e.target)) drawCount(e.target); });
document.addEventListener('paste', (e) => {
  const el = e.target;
  if (!counted(el)) return;
  const text = e.clipboardData?.getData('text') || '';
  const room = el.maxLength - el.value.length + Math.abs((el.selectionEnd ?? 0) - (el.selectionStart ?? 0));
  const cut = text.length - room;
  if (cut > 0) { el._cut = cut; setTimeout(() => { if (el._cut) drawCount(el, cut); }); }
}, true);
