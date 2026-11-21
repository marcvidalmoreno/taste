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

// A key press in a text field is typing, not a shortcut.
export const isTyping = (e) => !!e.target.closest?.('input, textarea, select, [contenteditable]');

// Toasts: one line, optional action button (e.g. Undo). Calm: they leave on their own.
export function toast(message, { action, onAction, timeout = 5000, tone = '' } = {}) {
  const box = document.getElementById('toasts');
  const close = () => el.remove();
  const el = h('div', { class: `toast ${tone}` },
    h('span', {}, message),
    action && h('button', { class: 'secondary outline', onClick: () => { close(); onAction(); } }, action));
  box.append(el);
  // The toast area is a popover: shown again on each toast, it sits in the top layer above any open dialog.
  if (box.matches(':popover-open')) box.hidePopover();
  box.showPopover();
  if (timeout) setTimeout(close, timeout);
  return close;
}

export const showError = (err) => toast(String(err.message || err), { tone: 'error', timeout: 8000 });
