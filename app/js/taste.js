// Taste: the 14 styles as written in taste/styles/*.json, each with my own images as evidence.
// Kept images next to rejected ones (with the reason): the contrast says more than the description.
//   #/taste            all styles
//   #/taste/<style>    the same page, scrolled to one style
import { h, thumbUrl, plural, RATING_LABELS, showError } from './ui.js';
import { loadGallery, openLarge, galleryHref } from './gallery.js';
import { openNote } from './notes.js';
import { openStyleEdit, undoEdit, diffValue, FIELDS } from './styleedit.js';
import { api } from './api.js';

const FACTS = [['light', 'Light'], ['composition', 'Composition'], ['camera_or_medium', 'Medium'],
  ['mood', 'Mood'], ['texture_detail', 'Detail'], ['prefer', 'Lean towards']];
const USES = { teams: 'Teams background', desktop: 'Desktop', phone: 'Phone', post: 'Post' };

export async function renderTaste(view, focus) {
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading the styles…'));
  let images, styles;
  try {
    ({ images, styles } = await loadGallery());
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not load the styles.'));
    return showError(err);
  }
  document.title = 'Taste · taste';
  // Styles with the most images first: where the evidence is.
  const keys = Object.keys(styles).sort((a, b) =>
    images.filter((im) => im.style === b).length - images.filter((im) => im.style === a).length
    || styles[a].name.localeCompare(styles[b].name));

  view.replaceChildren(
    h('hgroup', { class: 'page-head' }, h('h1', {}, 'Taste'),
      h('p', {}, `${plural(keys.length, 'style')} found in about 1,000 wallpapers I saved, each with the images I made in it.`)),
    h('nav', { class: 'style-index', 'aria-label': 'Styles' },
      keys.map((k) => h('a', { href: '#/taste/' + encodeURIComponent(k) },
        h('span', { class: 'mini-swatch', 'aria-hidden': 'true' }, styles[k].palette.slice(0, 4).map((c) => h('i', { style: { background: c } }))),
        styles[k].name))),
    ...keys.map((k) => styleCard(k, styles[k], images.filter((im) => im.style === k))));

  if (focus) document.getElementById('style-' + focus)?.scrollIntoView({ block: 'start' });
}

function styleCard(key, s, imgs) {
  const by = (r) => imgs.filter((im) => im.rating === r);
  const keep = by('keep'), almost = by('almost'), no = by('no');
  const unrated = imgs.filter((im) => !im.rating).length;
  const examples = (list, label, max) => list.length > 0 && h('div', { class: 'examples' },
    h('h3', {}, h('span', { class: `rating-pill ${list[0].rating}` }, label), ' ', h('small', { class: 'muted' }, list.length)),
    h('div', { class: 'ex-row' }, list.slice(0, max).map((im) => h('figure', {},
      h('button', { class: 'ex', onClick: () => openLarge(imgs.indexOf(im), imgs),
        'aria-label': `${label}${im.why ? ': ' + im.why : ''}` },
        h('img', { src: thumbUrl(im.batch, im.file, im.mtime), alt: '', loading: 'lazy' })),
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
      h('p', {}, s.description),
      h('div', { class: 'swatches', role: 'list', 'aria-label': 'Palette' },
        s.palette.map((c) => h('span', { role: 'listitem', title: c }, h('i', { style: { background: c } }), h('code', {}, c))))),
    h('div', { class: 'style-body' },
      h('dl', { class: 'facts' }, FACTS.filter(([k]) => s[k]).map(([k, label]) => [h('dt', {}, label), h('dd', {}, Array.isArray(s[k]) ? h('ul', { class: 'plain fact-list' }, s[k].map((x) => h('li', {}, x))) : s[k])]),
        s.avoid?.length && [h('dt', {}, 'Avoid'), h('dd', {}, h('ul', { class: 'chips' }, s.avoid.map((a) => h('li', {}, a))))],
        s.use?.length && [h('dt', {}, 'Good for'), h('dd', {}, s.use.map((u) => USES[u] || u).join(' · '))]),
      h('div', { class: 'evidence' },
        imgs.length
          ? [examples(keep, RATING_LABELS.keep.label, 8), examples(no, RATING_LABELS.no.label, 4), examples(almost, RATING_LABELS.almost.label, 4),
             h('p', { class: 'muted small' },
               unrated ? `${plural(unrated, 'image')} not rated yet. ` : '',
               h('a', { href: galleryHref({ style: key }) }, `All ${plural(imgs.length, 'image')} in the gallery`))]
          : h('p', { class: 'muted' }, 'No images made in this style yet.'))));
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
            `${e.at.slice(8, 10)}/${e.at.slice(5, 7)} ${e.at.slice(11)} · ${e.how === 'codex' ? 'Codex edit' : 'your words'}${e.undone ? ' · undone' : ''}`)),
          !e.undone && h('button', { class: 'ghost small', onClick: () => undoEdit(e, () => renderTaste(document.getElementById('view'), key)) }, 'Undo')),
        h('details', { class: 'small' }, h('summary', {}, e.summary || Object.keys(e.after).map((k) => FIELDS[k] || k).join(', ')),
          Object.keys(e.after).map((k) => [h('p', { class: 'muted' }, FIELDS[k] || k), diffValue(e.before[k], e.after[k])])))))));
  }).catch(() => {});
  return box;
}
