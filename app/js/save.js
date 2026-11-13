// Save: the one moment marks become ratings. A bar says how many marks are waiting; a short review
// lists them before anything is written, because saved ratings can't be changed here afterwards.
import { api } from './api.js';
import { store, onChange, changed } from './store.js';
import { flushWhy } from './marks.js';
import { h, thumbUrl, plural, RATINGS, markBadge, toast, showError } from './ui.js';

const drafts = () => (store.data?.items || []).filter((im) => im.status === 'draft');

export function renderSaveBar() {
  const slot = document.getElementById('save-slot');
  if (!slot) return;
  const n = drafts().length;
  slot.replaceChildren(n ? h('div', { class: 'save-bar' },
    h('span', {}, h('strong', {}, plural(n, 'mark')), ' not saved yet',
      h('span', { class: 'muted' }, ' · kept on this computer until you save')),
    h('button', { onClick: review }, 'Review and save…')) : '');
}

function review() {
  const list = drafts();
  const dlg = h('dialog', { class: 'review' });
  const close = () => { dlg.close(); dlg.remove(); };
  const saveBtn = h('button', { onClick: () => save(saveBtn, close) }, `Save ${plural(list.length, 'rating')}`);
  dlg.append(h('article', {},
    h('header', {}, h('h3', {}, `Save ${plural(list.length, 'rating')} to ratings.csv?`)),
    h('ul', { class: 'review-list' }, list.map((im) => h('li', {},
      h('img', { src: thumbUrl(store.data.batch, im.file, im.mtime), alt: '' }),
      h('span', { class: 'num' }, im.number),
      markBadge(im),
      h('span', {}, h('strong', {}, RATINGS[im.draft.rating].label),
        im.draft.why ? ` – ${im.draft.why}` : h('span', { class: 'muted' }, ' – no reason given'))))),
    h('p', { class: 'muted small' },
      'Ignored images are left out. Once saved, a rating is read-only here, so distil.py can trust its place in the file.'),
    h('footer', {},
      h('button', { class: 'secondary', onClick: close }, 'Keep editing'),
      saveBtn)));
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
}

async function save(btn, close) {
  btn.setAttribute('aria-busy', 'true');
  btn.disabled = true;
  try {
    await flushWhy();   // a "why" typed a moment ago must be in the draft before it is saved
    const r = await api('save', { method: 'POST', body: { batch: store.data.batch } });
    close();
    const left = r.due - r.since_last;
    toast(`${plural(r.saved, 'rating')} saved · ` +
      (left > 0 ? `${left} more until a distil is due` : 'a distil is due: see Overview'), { timeout: 7000 });
    changed(null, 'saved');   // the grid reads the batch again
  } catch (err) {
    btn.removeAttribute('aria-busy');
    btn.disabled = false;
    showError(err);
  }
}

onChange((name, kind) => { if (kind !== 'why') renderSaveBar(); });
