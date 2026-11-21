// Marking and ignoring. Optimistic: the screen changes at once, the server is told in the background,
// and if it refuses, the change is rolled back with a message. Rating stays as fast as the key press.
// Since 21 Nov 2026 a mark is saved the moment it is made (no drafts, no Save step) and can be changed or taken
// back at any time; each one also moves how the style's next runs lean (scripts/leaning.py).
import { api } from './api.js';
import { store, item, changed } from './store.js';
import { h, RATINGS, showError, toast } from './ui.js';

const statusOf = (im) => (im.status === 'ignored' ? 'ignored' : im.draft?.rating ? 'rated' : 'new');

async function sendMark(im) {
  const res = await api('mark', { method: 'PUT', body: {
    batch: store.data.batch, name: im.name, rating: im.draft?.rating ?? null, why: im.draft?.why ?? '' } });
  im.moves = res.moves;   // which parts of the style's prompt this mark moves: shown under the buttons
  changed(im.name, 'why');
  return res;
}

// Same mark again clears it, so every mark can be undone with the key that made it.
export async function toggleMark(name, rating) {
  const im = item(name);
  if (!im || im.status === 'ignored') return;
  const before = { draft: im.draft, status: im.status };
  const next = im.draft?.rating === rating ? null : rating;
  im.draft = next || im.draft?.why ? { rating: next, why: im.draft?.why || '' } : null;
  im.status = statusOf(im);
  store.justRated.add(name);   // stays in the "To rate" grid until the page is read again: no tile jumps away
  changed(name, 'mark');
  try {
    await sendMark(im);
  } catch (err) {
    Object.assign(im, before);
    changed(name, 'mark');
    showError(err);
  }
}

// The "why" is saved a second after the last key (each save is a row in ratings.csv), or when leaving the image.
// A why without a mark waits on the page until a thumb is pressed.
const pending = new Map();
export function setWhy(name, why) {
  const im = item(name);
  if (!im || im.status === 'ignored') return;
  im.draft = { rating: im.draft?.rating ?? null, why };
  clearTimeout(pending.get(name));
  if (!im.draft.rating) return;
  pending.set(name, setTimeout(() => { pending.delete(name); sendMark(im).catch(showError); }, 1000));
}

// Send any waiting "why" now (before saving, or when leaving an image).
export async function flushWhy() {
  const jobs = [...pending.keys()].map((name) => {
    clearTimeout(pending.get(name));
    pending.delete(name);
    return sendMark(item(name));
  });
  await Promise.all(jobs).catch(showError);
}

export async function setIgnored(name, ignored) {
  const im = item(name);
  if (!im || im.status === 'rated') return toast('Take the mark back first (press its thumb again), then ignore.');
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
  if (!im) return;
  if (im.status === 'rated') return toast('Take the mark back first (press its thumb again), then ignore.');
  const ignoring = im.status !== 'ignored';
  setIgnored(name, ignoring);
  toast(ignoring ? `#${im.number} ignored: hidden and left out of ratings` : `#${im.number} back in the batch`,
    { action: 'Undo', onAction: () => setIgnored(name, !ignoring) });
}

// Keep (or stop keeping) an image as an example of its style (21 Nov 2026). Quiet and reversible: the same
// button again takes it back. New runs of the style send up to 2 kept examples along as references.
export async function setKept(im, batch, kept) {
  const before = im.kept;
  im.kept = kept;
  try {
    const res = await api('keep', { method: 'POST', body: { batch, name: im.name, kept } });
    toast(kept ? `Kept as an example. ${res.count} kept for this style: new runs send up to 2 along. Press the star again to undo.` : 'No longer an example.',
      { timeout: 3500 });
    return res;
  } catch (err) {
    im.kept = before;
    showError(err);
    throw err;
  }
}

export function keepButton(im, onClick) {
  return h('button', { type: 'button', class: 'secondary outline keep-btn', 'aria-pressed': String(!!im.kept), onClick,
    disabled: !im.style, title: im.style ? 'Keep this image as an example of its style: shown first on Taste and sent along as a reference in new runs'
      : 'This image has no style' },
  h('span', { 'aria-hidden': 'true' }, im.kept ? '★' : '☆'), im.kept ? ' Kept as example ' : ' Keep as example ', h('kbd', {}, 'X'));
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
