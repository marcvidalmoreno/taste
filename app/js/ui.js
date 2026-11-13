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

// The three marks. Letter + word + colour, so the meaning never rests on colour alone.
export const RATINGS = {
  keep: { label: 'Keep', key: 'k' },
  almost: { label: 'Almost', key: 'a' },
  no: { label: 'No', key: 'n' },
};

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
  if (timeout) setTimeout(close, timeout);
  return close;
}

export const showError = (err) => toast(String(err.message || err), { tone: 'error', timeout: 8000 });
