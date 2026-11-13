// Overview: what the saved ratings say per style, and when the next distil is due.
// The chart is a stacked bar per style (keep / almost / no), one shared scale, so both the mix inside a
// style and the amount of evidence behind it can be read at a glance. A table holds the same numbers.
import { api, styles } from './api.js';
import { h, batchHref, batchTitle, plural, RATINGS, showError } from './ui.js';

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
  const draw = () => view.replaceChildren(
    h('hgroup', { class: 'page-head' }, h('h1', {}, 'Overview'),
      h('p', {}, `${plural(o.total, 'saved rating')} in total`)),
    h('div', { class: 'overview' },
      distilCard(o),
      unsavedCard(o),
      chartCard(o, all, draw)));
  draw();
}

function distilCard(o) {
  const n = o.since_last;
  const due = n >= o.due;
  const out = h('div');
  return h('article', { class: 'card distil' },
    h('h2', {}, 'Next distil'),
    h('p', { class: 'big' }, due ? 'Due now' : `${o.due - n} ratings to go`),
    h('div', { class: 'meter' },
      h('span', { class: 'bar', role: 'meter', 'aria-valuemin': 0, 'aria-valuemax': o.due, 'aria-valuenow': Math.min(n, o.due),
                  'aria-label': `${n} of ${o.due} ratings since the last distil` },
        h('i', { style: { width: Math.min(100, (n / o.due) * 100) + '%' } })),
      h('span', { class: 'num' }, `${n} / ${o.due}`)),
    h('p', { class: 'muted small' }, o.marked ? `Ratings since the last distil (marked ${o.marked}).` : 'No distil yet: every rating counts.'),
    h('p', { class: 'small' }, 'To distil, ask Claude Code to "distil my ratings": it reads the summary, proposes style edits, and you approve them.'),
    n > 0 && h('button', { class: 'secondary outline', onClick: async (e) => {
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

function unsavedCard(o) {
  const entries = Object.entries(o.unsaved);
  const n = entries.reduce((s, [, k]) => s + k, 0);
  return h('article', { class: 'card' },
    h('h2', {}, 'Not saved yet'),
    n ? [h('p', { class: 'big' }, plural(n, 'mark')),
      h('p', { class: 'muted small' }, 'Drafts count only once saved. Open a batch to review and save:'),
      h('ul', { class: 'plain' }, entries.map(([b, k]) => h('li', {}, h('a', { href: batchHref(b) }, batchTitle(b)), ` · ${k}`)))]
      : [h('p', { class: 'big' }, 'Nothing'), h('p', { class: 'muted small' }, 'Every mark is saved.')],
    o.ignored > 0 && h('p', { class: 'muted small' }, `${plural(o.ignored, 'image')} ignored (left out of ratings).`));
}

function chartCard(o, all, redraw) {
  const rows = Object.entries(o.styles)
    .map(([key, v]) => ({ key, ...v[scope], total: v[scope].keep + v[scope].almost + v[scope].no }))
    .filter((r) => r.total > 0)
    .sort((a, b) => b.total - a.total || b.keep - a.keep);
  const max = Math.max(1, ...rows.map((r) => r.total));
  const series = Object.keys(RATINGS);
  return h('article', { class: 'card chart-card' },
    h('div', { class: 'chart-head' },
      h('h2', {}, 'Per style'),
      h('nav', { class: 'filters', 'aria-label': 'Which ratings' },
        [['since', 'Since last distil'], ['all', 'All ratings']].map(([k, label]) => h('a', {
          href: '#/overview', 'aria-current': scope === k ? 'page' : null,
          onClick: (e) => { e.preventDefault(); scope = k; redraw(); } }, label)))),
    // Legend: always shown for the three series, in the same order as the segments.
    h('ul', { class: 'legend' }, series.map((s) => h('li', {}, h('i', { class: `sw ${s}` }), RATINGS[s].label))),
    rows.length ? h('div', { class: 'bars', role: 'img', 'aria-label': 'Ratings per style; the same numbers are in the table below' },
      rows.map((r) => h('div', { class: 'bar-row' },
        h('span', { class: 'label', title: r.key }, all[r.key]?.name || r.key,
          !all[r.key] && h('small', { class: 'muted' }, ' (old style)')),
        h('span', { class: 'track' },
          h('span', { class: 'stack', style: { width: (r.total / max) * 100 + '%' } },
            series.filter((s) => r[s]).map((s) => h('span', {
              class: `seg ${s}`, style: { flexGrow: r[s] },
              title: `${all[r.key]?.name || r.key}: ${r[s]} ${RATINGS[s].label.toLowerCase()} of ${r.total}`,
            }, r[s])))),
        h('span', { class: 'total' }, r.total))))
      : h('p', { class: 'muted' }, scope === 'since' ? 'No ratings since the last distil.' : 'No saved ratings yet.'),
    rows.length > 0 && h('details', { class: 'table-view' },
      h('summary', {}, 'As a table'),
      h('table', {},
        h('thead', {}, h('tr', {}, h('th', {}, 'Style'), series.map((s) => h('th', {}, RATINGS[s].label)), h('th', {}, 'Total'))),
        h('tbody', {}, rows.map((r) => h('tr', {}, h('td', {}, all[r.key]?.name || r.key),
          series.map((s) => h('td', {}, r[s])), h('td', {}, r.total)))))));
}
