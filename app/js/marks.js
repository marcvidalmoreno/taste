// Marking and ignoring. Optimistic: the screen changes at once, the server is told in the background,
// and if it refuses, the change is rolled back with a message. Rating stays as fast as the key press.
import { api } from './api.js';
import { store, item, changed } from './store.js';
import { h, RATINGS, showError, toast } from './ui.js';

const statusOf = (im) => (im.status === 'rated' || im.status === 'ignored') ? im.status
  : im.draft?.rating ? 'draft' : 'new';

function sendDraft(im) {
  return api('draft', { method: 'PUT', body: {
    batch: store.data.batch, name: im.name, rating: im.draft?.rating ?? null, why: im.draft?.why ?? '' } });
}

// Same mark again clears it, so every mark can be undone with the key that made it.
export async function toggleMark(name, rating) {
  const im = item(name);
  if (!im || im.status === 'rated') return;
  const before = { draft: im.draft, status: im.status };
  const next = im.draft?.rating === rating ? null : rating;
  im.draft = next || im.draft?.why ? { rating: next, why: im.draft?.why || '' } : null;
  im.status = statusOf(im);
  changed(name, 'mark');
  try {
    await sendDraft(im);
  } catch (err) {
    Object.assign(im, before);
    changed(name, 'mark');
    showError(err);
  }
}

// The "why" text is sent 400 ms after the last key, not on every key.
const pending = new Map();
export function setWhy(name, why) {
  const im = item(name);
  if (!im || im.status === 'rated') return;
  im.draft = { rating: im.draft?.rating ?? null, why };
  changed(name, 'why');
  clearTimeout(pending.get(name));
  pending.set(name, setTimeout(() => { pending.delete(name); sendDraft(im).catch(showError); }, 400));
}

// Send any waiting "why" now (before saving, or when leaving an image).
export async function flushWhy() {
  const jobs = [...pending.keys()].map((name) => {
    clearTimeout(pending.get(name));
    pending.delete(name);
    return sendDraft(item(name));
  });
  await Promise.all(jobs).catch(showError);
}

export async function setIgnored(name, ignored) {
  const im = item(name);
  if (!im || im.status === 'rated') return;
  const before = im.status;
  im.status = ignored ? 'ignored' : 'new';
  im.status = statusOf(im);
  changed(name, 'ignore');
  try {
    await api('ignore', { method: 'POST', body: { batch: store.data.batch, name, ignored } });
  } catch (err) {
    im.status = before;
    changed(name, 'ignore');
    showError(err);
  }
}

// Ignore or restore, with an Undo in the toast: a slip of the I key costs one click.
export function ignoreWithUndo(name) {
  const im = item(name);
  if (!im || im.status === 'rated') return;
  const ignoring = im.status !== 'ignored';
  setIgnored(name, ignoring);
  toast(ignoring ? `#${im.number} ignored: hidden and left out of ratings` : `#${im.number} back in the batch`,
    { action: 'Undo', onAction: () => setIgnored(name, !ignoring) });
}

// Up / Down buttons, the same in the large view and under each grid tile.
// In the grid they stay out of the Tab order (tabindex -1): the keyboard already marks the focused tile with U / D.
export function markButtons(im, { inGrid = false } = {}) {
  const r = im.draft?.rating;
  return h('div', { role: 'group', class: `marks${inGrid ? ' tile-marks' : ''}`,
                    'aria-label': inGrid ? `Mark image ${im.number}` : 'Mark' },
    Object.entries(RATINGS).map(([key, m]) => h('button', {
      type: 'button', class: `mark-btn ${key}`, 'aria-pressed': String(r === key),
      disabled: im.status === 'ignored', tabindex: inGrid ? '-1' : null,
      onClick: () => toggleMark(im.name, key),
    }, h('span', { 'aria-hidden': 'true' }, m.glyph), ' ', m.label, ' ', h('kbd', {}, m.key.toUpperCase()))));
}
