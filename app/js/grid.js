// One batch: thumbnails with filters. The large view (viewer.js) opens on top of it.
import { api, styles } from './api.js';
import { store, item, styleName, kindOf, FILTERS, visible, onChange } from './store.js';
import { toggleMark, ignoreWithUndo } from './marks.js';
import { openViewer, closeViewer, viewerHref } from './viewer.js';
import { renderSaveBar } from './save.js';
import { job } from './job.js';
import { h, thumbUrl, batchHref, batchTitle, shortDate, plural, RATINGS, markBadge, isTyping, showError } from './ui.js';

let view;

export async function renderBatch(el, batch, show, open) {
  view = el;
  show = FILTERS[show] ? show : 'to-rate';
  const fresh = store.data?.batch !== batch || !view.querySelector('.grid-page');
  if (fresh) {
    view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading the batch…'));
    try {
      [store.data, store.styles] = await Promise.all([api('batch/' + encodeURIComponent(batch)), styles()]);
    } catch (err) {
      view.replaceChildren(h('p', {}, 'Could not open this batch. ', h('a', { href: '#/' }, 'Back to batches')));
      return showError(err);
    }
  }
  if (fresh || show !== store.show) {
    store.show = show;
    draw();
  }
  if (open) openViewer(open);
  else closeViewer();
}

// Read the batch again (after saving, or when new images arrive) and keep the focus where it was.
export async function reloadBatch() {
  if (!store.data) return;
  store.data = await api('batch/' + encodeURIComponent(store.data.batch));
  if (view?.querySelector('.grid-page')) draw();
}

// ------------------------------------------------------------------ drawing

function draw() {
  const d = store.data;
  const focused = document.activeElement?.dataset?.name;
  const list = visible();
  document.title = `${batchTitle(d.batch)} · taste`;
  view.replaceChildren(h('div', { class: 'grid-page' },
    h('nav', { 'aria-label': 'Breadcrumb', class: 'crumbs' },
      h('ul', {}, h('li', {}, h('a', { href: '#/' }, 'Batches')), h('li', {}, batchTitle(d.batch)))),
    h('header', { class: 'grid-head' },
      h('hgroup', {},
        h('h1', {}, batchTitle(d.batch)),
        h('p', {}, [shortDate(d.date), plural(d.items.length, 'image'), d.seed && 'variations of the seed']
          .filter(Boolean).join(' · '))),
      filters()),
    list.length
      ? h('ul', { class: 'grid', onKeydown: onGridKey },
          store.show === 'to-rate' && d.seed && seedTile(d), list.map(tile), pendingTiles())
      : h('p', { class: 'empty-filter' }, FILTERS[store.show].empty),
    store.show === 'ignored' && list.length > 0 &&
      h('p', { class: 'muted small hint' }, 'To bring one back, open it and choose Restore, or press I on it here.'),
    h('div', { id: 'save-slot' }),
  ));
  renderSaveBar();
  if (focused) view.querySelector(`.tile[data-name="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
}

function counts() {
  const c = { 'to-rate': 0, rated: 0, ignored: 0 };
  for (const im of store.data.items) for (const k in FILTERS) if (FILTERS[k].test(im)) c[k]++;
  return c;
}

// Filters as links: each one has an address, so Back returns to the filter you were on.
function filters() {
  const c = counts();
  return h('nav', { class: 'filters', 'aria-label': 'Show' },
    Object.entries(FILTERS).map(([key, f]) => h('a', {
      href: batchHref(store.data.batch, key), 'aria-current': store.show === key ? 'page' : null,
    }, f.label, ' ', h('span', { class: 'n' }, c[key]))));
}

// Images the running variation job hasn't made yet: a placeholder each, replaced as they land.
function pendingTiles() {
  if (!job.running || job.batch !== store.data.batch || store.show !== 'to-rate') return [];
  const have = new Set(store.data.items.map((im) => im.name));
  return job.expected.filter((n) => !have.has(n)).map((n, i) => h('li', { class: 'pending-tile' },
    h('div', { class: 'frame' }, h('span', { 'aria-busy': i === 0 ? 'true' : null },
      i === 0 ? 'Making…' : 'Waiting')),
    h('div', { class: 'caption' }, h('span', { class: 'num' }, n.split('-')[0]),
      h('span', { class: 'muted' }, job.dry_run ? 'dry run' : 'about a minute each'),
      h('span', { class: 'kind' }, n.split('-').slice(1).join('-')))));
}

function seedTile(d) {
  return h('li', { class: 'seed-tile' },
    h('div', { class: 'frame' }, h('img', { src: thumbUrl(d.batch, d.seed), alt: 'Seed image of this batch', loading: 'lazy' })),
    h('div', { class: 'caption' }, h('span', { class: 'num' }, 'S'), h('span', {}, 'Seed'),
      h('span', { class: 'muted' }, 'hold S in the large view to compare')));
}


function tile(im) {
  const why = im.saved?.why || im.draft?.why;
  const label = `${im.number}. ${styleName(im.style)}, ${kindOf(im)}` +
    (im.saved ? `, saved as ${im.saved.rating}` : im.draft?.rating ? `, marked ${im.draft.rating}` : '');
  return h('li', {},
    h('a', { href: viewerHref(im.name), class: 'tile', dataset: { name: im.name }, 'aria-label': label,
             onClick: (e) => { e.preventDefault(); openViewer(im.name, { push: true }); } },
      h('div', { class: 'frame' },
        h('img', { src: thumbUrl(store.data.batch, im.file, im.mtime), alt: '', loading: 'lazy' }),
        markBadge(im)),
      h('div', { class: 'caption' },
        h('span', { class: 'num' }, im.number),
        h('span', { class: 'style' }, styleName(im.style)),
        h('span', { class: 'kind' }, kindOf(im))),
      why && h('div', { class: 'why' }, why)));
}

// Redraw one tile (or remove it if it no longer fits the filter) instead of the whole grid:
// no image reloads, no lost scroll, focus stays put.
onChange((name, kind) => {
  if (kind === 'saved' || kind === 'reload') return reloadBatch().catch(showError);
  if (kind === 'job') {   // progress: only the placeholders change
    const ul = view?.querySelector('.grid');
    if (ul && store.data?.batch === job.batch) { ul.querySelectorAll('.pending-tile').forEach((li) => li.remove()); ul.append(...pendingTiles()); }
    return;
  }
  if (!view?.querySelector('.grid-page') || !name) return;
  const im = item(name);
  const old = view.querySelector(`.tile[data-name="${CSS.escape(name)}"]`)?.closest('li');
  const fits = im && FILTERS[store.show].test(im);
  if (old && fits) {
    const hadFocus = old.contains(document.activeElement);
    const fresh = tile(im);
    old.replaceWith(fresh);
    if (hadFocus) fresh.querySelector('.tile').focus({ preventScroll: true });
  } else if (old && !fits) {
    const next = old.nextElementSibling || old.previousElementSibling;
    const hadFocus = old.contains(document.activeElement);
    old.remove();
    if (hadFocus) next?.querySelector('.tile')?.focus({ preventScroll: true });
    if (!view.querySelector('.grid .tile')) return draw();
  } else if (!old && fits) {
    return draw();
  }
  view.querySelector('.filters')?.replaceWith(filters());
});

// ------------------------------------------------------------------ keyboard in the grid

function onGridKey(e) {
  if (isTyping(e) || e.ctrlKey || e.metaKey || e.altKey) return;
  const el = e.target.closest('.tile');
  if (!el) return;
  const tiles = [...view.querySelectorAll('.grid .tile')];
  const i = tiles.indexOf(el);
  const cols = tiles.filter((t) => t.offsetTop === tiles[0].offsetTop).length || 1;
  const move = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: cols, ArrowUp: -cols }[e.key];
  if (move) {
    e.preventDefault();
    tiles[Math.max(0, Math.min(tiles.length - 1, i + move))].focus();
    return;
  }
  const key = e.key.toLowerCase();
  const name = el.dataset.name;
  const rating = Object.keys(RATINGS).find((r) => RATINGS[r].key === key);
  if (rating) {
    e.preventDefault();
    toggleMark(name, rating);
  } else if (key === 'i') {
    e.preventDefault();
    ignoreWithUndo(name);
  }
}
