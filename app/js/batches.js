// Batches view: every folder in generated/codex/, newest first, with what is left to rate.
import { api } from './api.js';
import { h, thumbUrl, batchHref, batchTitle, shortDate, plural, showError } from './ui.js';

export async function renderBatches(view) {
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading batches…'));
  let batches;
  try {
    ({ batches } = await api('batches'));
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not load the batches.'));
    return showError(err);
  }
  document.title = 'Batches · taste';

  if (!batches.length) {
    view.replaceChildren(h('section', { class: 'empty' },
      h('h1', {}, 'No batches yet'),
      h('p', {}, 'Images made with codex_run.py or variations.py land in generated/codex/ and show up here.')));
    return;
  }

  const left = batches.reduce((n, b) => n + b.to_rate, 0);
  view.replaceChildren(
    h('hgroup', { class: 'page-head' },
      h('h1', {}, 'Batches'),
      h('p', {}, left ? `${plural(left, 'image')} to rate` : 'Everything is rated')),
    h('ul', { class: 'batch-list' }, batches.map(batchRow)),
  );
}

function batchRow(b) {
  const done = b.to_rate === 0;
  // One link per row: the whole row is the target (Fitts), and Tab stops once per batch.
  return h('li', {},
    h('a', { href: batchHref(b.batch), class: 'batch-row' + (done ? ' is-done' : '') },
      h('div', { class: 'strip', 'aria-hidden': 'true' },
        b.preview.map((f) => h('img', { src: thumbUrl(b.batch, f, b.newest), alt: '', loading: 'lazy' }))),
      h('div', { class: 'batch-text' },
        h('strong', {}, batchTitle(b.batch)),
        h('small', {}, [shortDate(b.date), plural(b.images, 'image'), b.seed && 'variations of a seed']
          .filter(Boolean).join(' · '))),
      h('div', { class: 'batch-counts' },
        done ? h('span', { class: 'count muted' }, 'rated')
          : h('span', { class: 'count todo' }, `${b.to_rate} to rate`),
        b.drafts > 0 && h('span', { class: 'count draft' }, `${b.drafts} not saved`),
        b.ignored > 0 && h('span', { class: 'count muted' }, `${b.ignored} ignored`))));
}
