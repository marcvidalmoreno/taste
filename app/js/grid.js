// One batch: thumbnails with filters. The large view (viewer.js) opens on top of it.
import { api, styles } from './api.js';
import { store, item, styleName, kindOf, FILTERS, visible, onChange } from './store.js';
import { toggleMark, ignoreWithUndo, markButtons } from './marks.js';
import { openViewer, closeViewer, viewerHref } from './viewer.js';
import { job, enqueueRun, KIND } from './job.js';
import { api as call } from './api.js';
import { openStyleEdit } from './styleedit.js';
import { h, thumbUrl, batchHref, batchTitle, shortDate, plural, ratingForKey, markBadge, isTyping, showError, toast } from './ui.js';

let view;

export async function renderBatch(el, batch, show, open) {
  view = el;
  show = FILTERS[show] ? show : 'to-rate';
  const fresh = store.data?.batch !== batch || !view.querySelector('.grid-page');
  if (fresh) {
    store.justRated = new Set();
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
        h('p', {}, [KIND[d.kind]?.label, shortDate(d.date), plural(d.items.length, 'image'), d.seed && d.kind !== 'variations' && 'with a seed']
          .filter(Boolean).join(' · '))),
      filters()),
    batchMeta(d),
    // A new variations batch has no images yet, only placeholders: still a grid, not "nothing to rate".
    list.length || pendingTiles().length || failedTiles().length
      ? h('ul', { class: 'grid', onKeydown: onGridKey },
          store.show === 'to-rate' && d.seed && seedTile(d), list.map(tile), pendingTiles(), failedTiles())
      : h('p', { class: 'empty-filter' }, FILTERS[store.show].empty),
    store.show === 'ignored' && list.length > 0 &&
      h('p', { class: 'muted small hint' }, 'To bring one back, open it and choose Restore, or press I on it here.'),
  ));
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

// Images the running job hasn't made yet: a placeholder each, replaced as they land.
// Names are "1-palette" (variations) or "fern-3" (batch.py): split into number and kind either way.
function splitName(n) {
  let m = n.match(/^(\d+)-(.+)$/);
  if (m) return { num: m[1], kind: m[2] };
  m = n.match(/^(.+)-(\d+)$/);
  return m ? { num: m[2], kind: m[1] } : { num: '', kind: n };
}

function pendingTiles() {
  if (!job.running || job.batch !== store.data.batch || store.show !== 'to-rate') return [];
  const have = new Set(store.data.items.map((im) => im.name));
  const failed = new Set(job.failed || []);
  const left = job.expected.filter((n) => !have.has(n) && !failed.has(n));
  const now = job.current?.name || left[0];
  return left.map((n) => {
    const { num, kind } = splitName(n);
    const making = n === now;
    return h('li', { class: 'pending-tile' },
      h('div', { class: 'frame' }, h('span', { 'aria-busy': making ? 'true' : null }, making ? 'Making…' : 'Waiting'),
        making && job.current?.subject ? h('small', { class: 'subject' }, job.current.subject) : null),
      h('div', { class: 'caption' }, h('span', { class: 'num' }, num),
        h('span', { class: 'muted' }, job.dry_run ? 'dry run' : 'about a minute each'),
        h('span', { class: 'kind' }, kind)));
  });
}

// Where the batch is on disk, where it came from, how it was made and what was made from it.
// Answers "where did my images go?" and "what was this?" without leaving the page.
function batchMeta(d) {
  const p = d.parent;
  const parentHref = p && (p.file.startsWith('seed.') ? batchHref(p.batch)
    : `#/b/${encodeURIComponent(p.batch)}/${encodeURIComponent(p.file.replace(/\.[^.]+$/, ''))}`);
  const styles = [...new Set(d.items.map((im) => im.style).filter(Boolean))];
  return h('section', { class: 'batch-meta' },
    h('div', { class: 'meta-row' },
      h('span', { class: 'muted small' }, 'Folder'),
      h('code', { class: 'path', title: d.path }, d.rel_path),
      h('button', { class: 'ghost small', onClick: () => navigator.clipboard.writeText(d.path).then(() => toast('Folder path copied', { timeout: 2000 })) }, 'Copy path'),
      h('button', { class: 'ghost small', onClick: () => call('reveal', { method: 'POST', body: { batch: d.batch } }).catch(showError) }, 'Open folder'),
      h('span', { class: 'spacer' }),
      styles.length === 1 && h('button', { class: 'ghost small', onClick: () => openStyleEdit({ style: styles[0] }) }, 'Change the style…'),
      styles.length > 0 && h('a', { class: 'small', href: '#/new?mode=batch&style=' + styles.map(encodeURIComponent).join(',') },
        styles.length > 1 ? 'New run with these styles' : 'New run with this style')),
    p && h('a', { class: 'made-from', href: parentHref },
      h('img', { src: thumbUrl(p.batch, p.file), alt: '' }),
      h('span', {}, 'Made from ', h('strong', {}, p.file.replace(/\.[^.]+$/, '')), ' in ', batchTitle(p.batch),
        d.run?.change && h('span', { class: 'muted' }, ` · asked: “${d.run.change}”`))),
    d.run && runDetails(d.run),
    d.children?.length > 0 && h('div', { class: 'children' },
      h('span', { class: 'muted small' }, 'Made from images here'),
      h('ul', { class: 'child-list' }, d.children.map((c) => h('li', {},
        h('a', { href: batchHref(c.batch), title: batchTitle(c.batch) },
          c.preview ? h('img', { src: thumbUrl(c.batch, c.preview), alt: '' }) : h('span', { class: 'no-img' }),
          h('span', { class: 'small' }, `${KIND[c.kind]?.label || c.kind} of ${c.file.replace(/\.[^.]+$/, '')}`, h('br'),
            h('span', { class: 'muted' }, plural(c.images, 'image')))))))));
}

function runDetails(r) {
  const rows = [
    ['Started', r.started && `${shortDate(r.started.slice(0, 10))} ${r.started.slice(11)} · from the ${r.by || 'web app'}`],
    ['Styles', r.styles?.map(styleName).join(', ')],
    ['Shape', r.ratio],
    ['Wildcard', r.kind === 'batch' ? (r.wildcards ? 'last image of each style' : 'none') : null],
    ['Changes', r.changes?.join(', ')],
    ['Asked for', r.change],
    ['Kept', r.keep?.join(', ')],
    ['Subject', r.subject],
    ['In every image', r.note],
  ].filter(([, v]) => v);
  const subjects = Object.entries(r.subjects || {}).filter(([, list]) => list?.length);
  return h('details', { class: 'run-details' },
    h('summary', { class: 'small' }, 'How it was made'),
    h('dl', {}, rows.map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])),
    subjects.length > 0 && h('div', { class: 'small' }, subjects.map(([st, list]) => [
      h('p', { class: 'muted' }, `Subjects · ${styleName(st)}` + (r.hints?.[st] ? ` (asked: ${r.hints[st]})` : '')),
      h('ol', {}, list.map((x) => h('li', {}, x)))])));
}

// Images that were tried and gave nothing (blocked by the filter, timed out): say so, offer one retry.
function failedTiles() {
  if (store.show !== 'to-rate') return [];
  const waiting = new Set(job.running && job.batch === store.data.batch ? job.expected : []);
  const queued = new Set((job.queue || []).filter((q) => q.batch === store.data.batch).flatMap((q) => q.expected));
  return (store.data.failed || []).filter((f) => !waiting.has(f.name)).map((f) => h('li', { class: 'failed-tile' },
    h('div', { class: 'frame' },
      h('strong', {}, 'No image'),
      h('small', {}, 'Blocked by the filter, or Codex timed out. The log is next to it: ', h('code', {}, `${f.name}.codex.log`)),
      h('div', { class: 'failed-actions' },
        queued.has(f.name) ? h('span', { class: 'small' }, 'Retry queued')
          : h('button', { class: 'secondary outline small-btn', onClick: (e) => retry(f, e.currentTarget) }, 'Retry once'),
        f.prompt && h('button', { class: 'ghost small', onClick: () => navigator.clipboard.writeText(f.prompt).then(() => toast('Prompt copied', { timeout: 2000 })) }, 'Copy prompt'))),
    h('div', { class: 'caption' }, h('span', { class: 'num' }, '–'), h('span', { class: 'style' }, styleName(f.style)),
      h('span', { class: 'kind' }, f.name))));
}

async function retry(f, btn) {
  btn.disabled = true;
  btn.setAttribute('aria-busy', 'true');
  try {
    const res = await enqueueRun({ kind: 'retry', batch: store.data.batch, name: f.name });
    toast(res.position <= 1 ? `Trying ${f.name} again` : `Retry of ${f.name} queued, number ${res.position}`);
  } catch (err) {
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    showError(err);
  }
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
    (im.draft?.rating ? `, marked ${im.draft.rating === 'keep' ? 'up' : 'down'}` : '');
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
      why && h('div', { class: 'why' }, why)),
    // Mark without opening the image. Saved ratings are read-only, ignored images can't be marked.
    !im.saved && im.status !== 'ignored' && markButtons(im, { inGrid: true }));
}

// Redraw one tile (or remove it if it no longer fits the filter) instead of the whole grid:
// no image reloads, no lost scroll, focus stays put.
onChange((name, kind) => {
  if (kind === 'saved' || kind === 'reload') return reloadBatch().catch(showError);
  if (kind === 'job') {   // progress: only the placeholders change
    if (!view?.querySelector('.grid-page')) return;
    const ul = view.querySelector('.grid');
    const here = job.running && store.data?.batch === job.batch;
    // The run for this batch ended while another one took over the header: read the batch once more,
    // so the placeholders give way to the images (or to a "No image" tile).
    if (!here && ul?.querySelector('.pending-tile')) return reloadBatch().catch(showError);
    if (store.data?.batch !== job.batch) return;
    if (!ul) return draw();
    ul.querySelectorAll('.pending-tile').forEach((li) => li.remove());
    ul.querySelector('.failed-tile') ? ul.querySelector('.failed-tile').before(...pendingTiles()) : ul.append(...pendingTiles());
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
  const rating = ratingForKey(key);
  if (rating) {
    e.preventDefault();
    toggleMark(name, rating);
  } else if (key === 'i') {
    e.preventDefault();
    ignoreWithUndo(name);
  }
}
