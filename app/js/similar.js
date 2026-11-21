// "More like this": the nearest existing images by colour and framing (scripts/similar.py). Free: no images spent.
// A row under the actions in both large views. A click opens the neighbour in the Gallery large view, stepping
// through the row with the arrows; that view has its own row, so a look can be followed from image to image.
import { api } from './api.js';
import { h, thumbUrl, showError } from './ui.js';
import { openLarge } from './gallery.js';

const cache = new Map();   // "batch/name/mode" -> items
let sameStyle = false;     // the chip: remembered while the page is open

export function similarRow(im, batch, hasStyle) {
  const box = h('section', { class: 'similar', 'aria-label': 'More like this' });
  const key = () => `${batch}/${im.name}/${sameStyle ? 'same' : 'all'}`;
  const head = () => h('div', { class: 'similar-head' },
    h('strong', {}, 'More like this'), h('span', { class: 'muted small' }, 'by colour and framing'),
    hasStyle && h('button', { type: 'button', class: 'chip-btn small', 'aria-pressed': String(sameStyle),
      onClick: () => { sameStyle = !sameStyle; load(); } }, 'Same style only'));
  const show = (body) => box.replaceChildren(head(), body);
  async function load() {
    const k = key();
    if (!cache.has(k)) {
      show(h('p', { class: 'muted small', 'aria-busy': 'true' }, 'Looking…'));
      try {
        cache.set(k, (await api(`similar/${encodeURIComponent(batch)}/${encodeURIComponent(im.name)}${sameStyle ? '/same' : ''}`)).items);
      } catch (err) { show(h('p', { class: 'muted small' }, 'Could not look: ' + err.message)); return showError(err); }
    }
    const items = cache.get(k);
    if (key() !== k) return;   // the chip moved on while this was loading
    show(items.length
      ? h('div', { class: 'similar-row', role: 'list' }, items.map((x, i) => h('button', { type: 'button', role: 'listitem', class: 'similar-thumb',
          'aria-label': `Open ${x.style || 'image'} from ${x.batch}`, title: x.style || '',
          onClick: () => openLarge(i, items) },
        h('img', { src: thumbUrl(x.batch, x.file, x.mtime), alt: '', loading: 'lazy' }))))
      : h('p', { class: 'muted small' }, sameStyle ? 'No other image of this style yet.' : 'Nothing to compare with yet.'));
  }
  load();
  return box;
}
