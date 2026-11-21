// Overview: what the saved ratings say per style, and when the next distil is due.
// The chart is a stacked bar per style (up / down, plus "almost" from older ratings), one shared scale, so both the mix inside a
// style and the amount of evidence behind it can be read at a glance. A table holds the same numbers.
import { api, styles } from './api.js';
import { h, batchHref, batchTitle, plural, RATING_LABELS, showError } from './ui.js';
import { notesCard } from './notes.js';

let scope = 'since';   // 'since' the last distil (what the distil will read) or 'all'

export async function renderOverview(view) {
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading the ratings…'));
  let o, all;
  try {
    [o, all] = await Promise.all([api('overview'), styles()]);
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not load the ratings.'));
    return showError(err);
  }
  document.title = 'Overview · taste';
  const notes = await notesCard();   // built once: its own redraws don't touch the chart
  const draw = () => view.replaceChildren(
    h('hgroup', { class: 'page-head' }, h('h1', {}, 'Overview'),
      h('p', {}, `${plural(o.total, 'saved rating')} in total`)),
    h('div', { class: 'overview' },
      distilCard(o),
      notes,
      chartCard(o, all, draw)));
  draw();
}

function distilCard(o) {
  const n = o.since_last;
  const due = n >= o.due;
  const out = h('div');
  return h('article', { class: 'card distil' },
    h('h2', {}, 'Style suggestions'),
    h('p', { class: 'big' }, due ? 'Codex is on it' : `Next look in ${o.due - n} ratings`),
    h('div', { class: 'meter' },
      h('span', { class: 'bar', role: 'meter', 'aria-valuemin': 0, 'aria-valuemax': o.due, 'aria-valuenow': Math.min(n, o.due),
                  'aria-label': `${n} of ${o.due} ratings since the last distil` },
        h('i', { style: { width: Math.min(100, (n / o.due) * 100) + '%' } })),
      h('span', { class: 'num' }, `${n} / ${o.due}`)),
    h('p', { class: 'muted small' }, o.marked ? `Ratings since the last distil (marked ${o.marked}).` : 'No distil yet: every rating counts.'),
    h('p', { class: 'small' }, 'Every 20 ratings Codex looks at your styles and suggests edits; a chip in the header says when one waits.'),
    h('a', { href: '#/suggestions', class: 'small' }, 'Suggestions'), ' ',
    n > 0 && h('button', { class: 'ghost small', onClick: async (e) => {
      e.target.setAttribute('aria-busy', 'true');
      try {
        const r = await api('distil');
        out.replaceChildren(h('pre', { class: 'log' }, r.output || '(nothing)'),
          h('p', { class: 'muted small' }, 'Preview only: nothing was marked or changed.'));
      } catch (err) { showError(err); }
      e.target.removeAttribute('aria-busy');
    } }, 'Preview the distil summary'),
    out);
}

function chartCard(o, all, redraw) {
  const rows = Object.entries(o.styles)
    .map(([key, v]) => ({ key, ...v[scope], total: v[scope].keep + v[scope].almost + v[scope].no }))
    .filter((r) => r.total > 0)
    .sort((a, b) => b.total - a.total || b.keep - a.keep);
  const max = Math.max(1, ...rows.map((r) => r.total));
  // Up and down; 'almost' only while older ratings in this view still have it.
  const series = ['keep', 'no', ...(rows.some((r) => r.almost) ? ['almost'] : [])];
  return h('article', { class: 'card chart-card' },
    h('div', { class: 'chart-head' },
      h('h2', {}, 'Per style'),
      h('nav', { class: 'filters', 'aria-label': 'Which ratings' },
        [['since', 'Since last distil'], ['all', 'All ratings']].map(([k, label]) => h('a', {
          href: '#/overview', 'aria-current': scope === k ? 'page' : null,
          onClick: (e) => { e.preventDefault(); scope = k; redraw(); } }, label)))),
    // Legend: always shown for the series, in the same order as the segments.
    h('ul', { class: 'legend' }, series.map((s) => h('li', {}, h('i', { class: `sw ${s}` }), RATING_LABELS[s].label))),
    rows.length ? h('div', { class: 'bars', role: 'img', 'aria-label': 'Ratings per style; the same numbers are in the table below' },
      rows.map((r) => h('div', { class: 'bar-row' },
        h('span', { class: 'label', title: r.key }, all[r.key]?.name || r.key,
          !all[r.key] && h('small', { class: 'muted' }, ' (old style)')),
        h('span', { class: 'track' },
          h('span', { class: 'stack', style: { width: (r.total / max) * 100 + '%' } },
            series.filter((s) => r[s]).map((s) => h('span', {
              class: `seg ${s}`, style: { flexGrow: r[s] },
              title: `${all[r.key]?.name || r.key}: ${r[s]} ${RATING_LABELS[s].label.toLowerCase()} of ${r.total}`,
            }, r[s])))),
        h('span', { class: 'total' }, r.total))))
      : h('p', { class: 'muted' }, scope === 'since' ? 'No ratings since the last distil.' : 'No saved ratings yet.'),
    rows.length > 0 && h('details', { class: 'table-view' },
      h('summary', {}, 'As a table'),
      h('table', {},
        h('thead', {}, h('tr', {}, h('th', {}, 'Style'), series.map((s) => h('th', {}, RATING_LABELS[s].label)), h('th', {}, 'Total'))),
        h('tbody', {}, rows.map((r) => h('tr', {}, h('td', {}, all[r.key]?.name || r.key),
          series.map((s) => h('td', {}, r[s])), h('td', {}, r.total)))))));
}
