// Taste: the styles as written in taste/styles/*.json, each with my own images as evidence.
// "New style from images…" starts one from reference images (newstyle.js, 21 Nov 2026).
// Kept images next to rejected ones (with the reason): the contrast says more than the description.
//   #/taste            all styles
//   #/taste/<style>    the same page, scrolled to one style
import { h, thumbUrl, plural, RATING_LABELS, showError, toast } from './ui.js';
import { loadGallery, openLarge, galleryHref } from './gallery.js';
import { openNote } from './notes.js';
import { openStyleEdit, undoEdit, diffValue, FIELDS } from './styleedit.js';
import { api, refreshStyles } from './api.js';
import { openNewStyle } from './newstyle.js';
import { setKept } from './marks.js';

const FACTS = [['light', 'Light'], ['composition', 'Composition'], ['camera_or_medium', 'Medium'],
  ['mood', 'Mood'], ['texture_detail', 'Detail'], ['prefer', 'Lean towards']];
const USES = { teams: 'Teams background', desktop: 'Desktop', phone: 'Phone', post: 'Post' };

export async function renderTaste(view, focus) {
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading the styles…'));
  let images, styles, archived;
  try {
    ({ images, styles, archived } = await loadGallery());
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not load the styles.'));
    return showError(err);
  }
  document.title = 'Taste · taste';
  leanings = api('leaning').then((d) => d.leaning).catch(() => ({}));
  // Styles with the most images first: where the evidence is.
  const keys = Object.keys(styles).sort((a, b) =>
    images.filter((im) => im.style === b).length - images.filter((im) => im.style === a).length
    || styles[a].name.localeCompare(styles[b].name));

  view.replaceChildren(
    h('div', { class: 'page-head taste-head' },
      h('hgroup', {}, h('h1', {}, 'Taste'),
        h('p', {}, `${plural(keys.length, 'style')}, most found in about 1,000 wallpapers I saved, each with the images I made in it.`)),
      h('button', { class: 'secondary outline small-btn', onClick: () => openNewStyle({
        onCreated: (key) => renderTaste(document.getElementById('view'), key || undefined) }) }, 'New style from images…')),
    h('nav', { class: 'style-index', 'aria-label': 'Styles' },
      keys.map((k) => h('a', { href: '#/taste/' + encodeURIComponent(k) },
        h('span', { class: 'mini-swatch', 'aria-hidden': 'true' }, styles[k].palette.slice(0, 4).map((c) => h('i', { style: { background: c } }))),
        styles[k].name))),
    ...keys.map((k) => styleCard(k, styles[k], images.filter((im) => im.style === k))),
    archivedBox(archived, images, focus));

  if (focus) document.getElementById('style-' + focus)?.scrollIntoView({ block: 'start' });
}

function styleCard(key, s, imgs) {
  const by = (r) => imgs.filter((im) => im.rating === r);
  const kept = imgs.filter((im) => im.kept), keep = by('keep').filter((im) => !im.kept), almost = by('almost'), no = by('no');
  const unrated = imgs.filter((im) => !im.rating).length;
  const examples = (list, label, max, pill) => list.length > 0 && h('div', { class: 'examples' },
    h('h3', {}, h('span', { class: pill || `rating-pill ${list[0].rating}` }, label), ' ', h('small', { class: 'muted' }, list.length)),
    h('div', { class: 'ex-row' }, list.slice(0, max).map((im) => h('figure', { class: 'ex-fig' },
      h('button', { class: 'ex', onClick: () => openLarge(imgs.indexOf(im), imgs),
        'aria-label': `${label}${im.why ? ': ' + im.why : ''}` },
        h('img', { src: thumbUrl(im.batch, im.file, im.mtime), alt: '', loading: 'lazy' })),
      h('button', { class: 'star-btn', 'aria-pressed': String(!!im.kept), title: im.kept ? 'Kept as an example: click to stop' : 'Keep as an example of this style',
        'aria-label': im.kept ? 'Stop keeping as example' : 'Keep as example',
        onClick: () => setKept(im, im.batch, !im.kept).then(() => document.getElementById('style-' + key)?.replaceWith(styleCard(key, s, imgs))).catch(() => {}) },
      im.kept ? '★' : '☆'),
      im.why && h('figcaption', {}, im.why)))));

  return h('article', { class: 'card style-card', id: 'style-' + key },
    h('header', {},
      h('div', { class: 'style-title' },
        h('h2', {}, s.name),
        h('a', { href: '#/new?mode=batch&style=' + encodeURIComponent(key), role: 'button', class: 'secondary outline small-btn' }, 'New run'),
        h('a', { href: '#/new?mode=one&style=' + encodeURIComponent(key), class: 'small' }, 'One image'),
        h('button', { class: 'secondary outline small-btn', onClick: () => openStyleEdit({ style: key, onApplied: () => renderTaste(document.getElementById('view'), key) }) }, 'Change this style…'),
        h('button', { class: 'ghost small', onClick: () => openNote({ style: key }) }, 'Note for Claude…')),
      editsSlot(key),
      leanSlot(key),
      h('p', {}, s.description),
      s.refs?.length > 0 && h('div', { class: 'ref-strip small-refs', role: 'list', 'aria-label': 'Started from these references' },
        h('span', { class: 'muted small' }, 'Started from'),
        s.refs.map((f) => h('a', { role: 'listitem', href: `/ref/${encodeURIComponent(key)}/${encodeURIComponent(f)}`, target: '_blank', rel: 'noopener' },
          h('img', { src: `/ref/${encodeURIComponent(key)}/${encodeURIComponent(f)}`, alt: 'Reference image', loading: 'lazy' })))),
      h('div', { class: 'swatches', role: 'list', 'aria-label': 'Palette' },
        s.palette.map((c) => h('span', { role: 'listitem', title: c }, h('i', { style: { background: c } }), h('code', {}, c))))),
    h('div', { class: 'style-body' },
      h('dl', { class: 'facts' }, FACTS.filter(([k]) => s[k]).map(([k, label]) => [h('dt', {}, label), h('dd', {}, Array.isArray(s[k]) ? h('ul', { class: 'plain fact-list' }, s[k].map((x) => h('li', {}, x))) : s[k])]),
        s.avoid?.length && [h('dt', {}, 'Avoid'), h('dd', {}, h('ul', { class: 'chips' }, s.avoid.map((a) => h('li', {}, a))))],
        s.use?.length && [h('dt', {}, 'Good for'), h('dd', {}, s.use.map((u) => USES[u] || u).join(' · '))]),
      h('div', { class: 'evidence' },
        imgs.length
          ? [examples(kept, '★ Kept as examples', 8, 'rating-pill kept'), examples(keep, RATING_LABELS.keep.label, 8), examples(no, RATING_LABELS.no.label, 4), examples(almost, RATING_LABELS.almost.label, 4),
             h('p', { class: 'muted small' },
               unrated ? `${plural(unrated, 'image')} not rated yet. ` : '',
               h('a', { href: galleryHref({ style: key }) }, `All ${plural(imgs.length, 'image')} in the gallery`))]
          : h('p', { class: 'muted' }, 'No images made in this style yet.'))));
}

// Styles switched off (Styles page): folded at the bottom, each with a way back
function archivedBox(archived, images, focus) {
  const keys = Object.keys(archived).sort((a, b) => archived[a].name.localeCompare(archived[b].name));
  if (!keys.length) return null;
  return h('details', { class: 'archived-box', open: keys.includes(focus) ? true : null },
    h('summary', {}, `Archived (${keys.length})`),
    keys.map((k) => h('article', { class: 'card style-card is-off', id: 'style-' + k },
      h('div', { class: 'style-title' },
        h('span', { class: 'mini-swatch', 'aria-hidden': 'true' }, archived[k].palette.slice(0, 4).map((c) => h('i', { style: { background: c } }))),
        h('h2', {}, archived[k].name),
        h('button', { class: 'secondary outline small-btn', onClick: async () => {
          try { await api('styles/switch', { method: 'POST', body: { style: k, on: true } }); await refreshStyles(); toast(`${archived[k].name} is back on.`); }
          catch (err) { return showError(err); }
          renderTaste(document.getElementById('view'), k);
        } }, 'Switch back on'),
        h('a', { class: 'small', href: '#/styles/' + encodeURIComponent(k) }, 'History')),
      h('p', { class: 'muted small' }, archived[k].description),
      h('a', { class: 'small', href: galleryHref({ style: k }) }, plural(images.filter((im) => im.style === k).length, 'image') + ' in the gallery'))));
}

// Edits made from the page to this style, newest first, each with Undo (while nothing later changed the same field).
function editsSlot(key) {
  const box = h('div', { class: 'style-edits' });
  api('style/edits/' + encodeURIComponent(key)).then(({ edits }) => {
    if (!edits.length) return;
    box.replaceChildren(h('details', {},
      h('summary', { class: 'small' }, (() => { const on = edits.filter((e) => !e.undone).length, off = edits.length - on;
        return `Changed from the app: ${plural(on, 'edit')}${off ? ` (${off} undone)` : ''}`; })()),
      h('ul', { class: 'plain' }, edits.map((e) => h('li', { class: e.undone ? 'is-undone' : '' },
        h('div', { class: 'edit-line' },
          h('span', {}, h('strong', {}, `“${e.change}”`), ' ', h('span', { class: 'muted small' },
            `${e.at.slice(8, 10)}/${e.at.slice(5, 7)} ${e.at.slice(11)} · ${{ codex: 'Codex edit', new: 'created from references' }[e.how] || 'your words'}${e.undone ? ' · undone' : ''}`)),
          !e.undone && h('button', { class: 'ghost small', onClick: () => undoEdit(e, () => renderTaste(document.getElementById('view'), key)) }, 'Undo')),
        e.how === 'new' ? (e.summary && h('p', { class: 'muted small' }, e.summary))
          : h('details', { class: 'small' }, h('summary', {}, e.summary || Object.keys(e.after).map((k) => FIELDS[k] || k).join(', ')),
            Object.keys(e.after).map((k) => [h('p', { class: 'muted' }, FIELDS[k] || k), diffValue(e.before[k], e.after[k])])))))));
  }).catch(() => {});
  return box;
}

// How the thumbs steer this style's next runs (scripts/leaning.py): the options rated up come up more often,
// the ones rated down less, every option keeps a chance. Shown so the score is never a hidden mechanism.
let leanings = Promise.resolve({});
const AXES = { light: 'Light', composition: 'Framing', mood: 'Mood', palette: 'Palette', detail: 'Detail' };
function leanSlot(key) {
  const box = h('div', { class: 'leaning' });
  leanings.then((all) => {
    const l = all[key];
    const rows = l ? Object.entries(l.axes).flatMap(([axis, opts]) => opts.length < 2 ? []
      : opts.filter((o) => o.up || o.down).map((o) => ({ axis, ...o }))) : [];
    if (!rows.length) return;
    rows.sort((a, b) => b.weight - a.weight);
    const odds = (w) => (w >= 1 ? `${w.toFixed(1)}× as likely` : `${(1 / w).toFixed(1)}× less likely`);
    box.replaceChildren(h('details', {},
      h('summary', { class: 'small' }, `How new runs lean, from ${plural(l.ratings, 'rating')}`),
      h('ul', { class: 'plain lean-list' }, rows.map((o) => h('li', { class: o.weight > 1 ? 'up' : o.weight < 1 ? 'down' : '' },
        h('span', { class: 'lean-odds' }, o.weight === 1 ? 'even' : odds(o.weight)),
        h('span', {}, h('span', { class: 'muted' }, `${AXES[o.axis] || o.axis} · `), o.text.replace(/^[A-Za-z]+: /, '').replace(/\.$/, '')),
        h('span', { class: 'muted small' }, `👍 ${o.up} · 👎 ${o.down}`)))),
      l.liked_subjects.length > 0 && h('p', { class: 'small' }, h('span', { class: 'muted' }, 'Subjects you liked (Codex writes new ones in this direction): '),
        l.liked_subjects.slice(0, 4).join('; '))));
  });
  return box;
}
