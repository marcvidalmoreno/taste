// "How it got here" (25 Nov 2026): the versions an image came from, oldest first, ending with itself, in both
// large views. Each step says how it was made (batch, remix, variations…) and what was asked. A click opens that
// version in the Gallery large view, stepping through the chain with ← →, so the changes can be flicked through
// in place. An image with no earlier version gets one muted line instead (25 Nov 2026), so "no history" reads
// differently from "feature missing".
// The style's part of the story (25 Nov 2026): under the versions, how the image's style came to be what it was
// when the image was made (created, your edits, distils), the image's place in that line, and what changed since,
// with a link to the full history on the Styles page. Reads api/styles/history, the same data as that page.
import { api, allStyles } from './api.js';
import { h, thumbUrl, batchTitle, shortDate, plural, RATING_LABELS } from './ui.js';
import { KIND } from './job.js';
import { openLarge } from './gallery.js';

const cache = new Map();   // "batch/name" -> steps

// What each variation type changed (scripts/variations.py), in a few words.
const CHANGE_WORDS = { palette: 'new palette and light', subject: 'new subject', composition: 'new framing', mood: 'other time of day' };

export function historySection(im, batch) {
  const box = h('section', { class: 'lineage', 'aria-label': 'How it got here', hidden: true });
  const k = `${batch}/${im.name}`;
  const styleBox = h('div', { class: 'lineage-style', hidden: true });
  const show = (steps, names) => {
    if (steps.length < 2) { box.replaceChildren(freshLine(steps[0], names), styleBox); box.hidden = false; return; }
    // The versions that open in the Gallery large view, this image last, so ← → walk the whole chain.
    const openable = steps.filter((s) => !s.given && !s.missing && !s.ignored);
    box.replaceChildren(
      h('div', { class: 'lineage-head' }, h('strong', {}, 'How it got here'),
        h('span', { class: 'muted small' }, steps.length === 2 ? '1 step' : `${steps.length - 1} steps, oldest first`)),
      h('ol', { class: 'lineage-list' }, steps.map((s, i) => stepRow(s, i === steps.length - 1, openable, names))), styleBox);
    box.hidden = false;
  };
  if (im.style) styleStory(im, batch, styleBox);
  if (cache.has(k)) allStyles().then((st) => show(cache.get(k), st));
  else {
    Promise.all([api(`history/${encodeURIComponent(batch)}/${encodeURIComponent(im.name)}`), allStyles()])
      .then(([r, st]) => { cache.set(k, r.steps); show(r.steps, st); })
      .catch((err) => {
        // A server started before this feature existed doesn't know the route: say so once, quietly.
        if (err.status === 404 && err.message === 'not found') {
          box.replaceChildren(h('div', { class: 'lineage-head' }, h('strong', {}, 'How it got here')),
            h('p', { class: 'muted small' }, 'Shows up the next time the app starts.'));
          box.hidden = false;
        }
      });
  }
  return box;
}

// One quiet line for an image that starts its own chain: how it was made, and that nothing came before.
// A remix or seeded image whose source can't be found says so instead of "made fresh".
function freshLine(s, names) {
  const style = s && s.kind !== 'remix' && s.kind !== 'variations' ? names[s.style]?.name || s.style : '';
  const kind = s && s.kind !== 'batch' ? KIND[s.kind]?.label || s.kind : '';
  const what = [kind, style].filter(Boolean).join(' · ');
  const ref = s?.seed || '';
  const lost = s && (s.kind === 'remix' || s.kind === 'variations' || (ref && !ref.startsWith('kept ')));
  const text = lost ? `${what || 'Made from an earlier image'}, earlier version not found`
    : `made fresh in this batch${what ? ` (${what})` : ''}, no earlier versions`;
  return h('div', { class: 'lineage-head' }, h('strong', {}, 'How it got here'), h('span', { class: 'muted small' }, text));
}

function stepRow(s, isMe, openable, names) {
  const style = names[s.style]?.name || s.style;
  const how = s.given ? 'Reference image you gave'
    : [KIND[s.kind]?.label || s.kind, style && s.kind !== 'remix' && s.kind !== 'variations' ? style : ''].filter(Boolean).join(' · ');
  const asked = s.kind === 'variations' ? CHANGE_WORDS[s.asked] || s.asked : s.asked;
  const mark = s.rating && RATING_LABELS[s.rating];
  const where = isMe ? 'This image' : `${s.number ? '#' + s.number + ' in ' : ''}${batchTitle(s.batch)}`;
  const body = [
    s.missing ? h('span', { class: 'no-img' }) : h('img', { src: thumbUrl(s.batch, s.file, s.mtime || 0), alt: '', loading: 'lazy' }),
    h('span', { class: 'lineage-text' },
      h('span', { class: 'lineage-how' }, h('strong', {}, how), mark && h('span', { class: `lineage-mark ${s.rating}`, title: mark.label }, mark.glyph)),
      asked && h('span', { class: 'lineage-asked', title: asked }, s.kind === 'single' ? asked : `“${asked}”`),
      h('span', { class: 'muted small' }, [where, s.date && shortDate(s.date), s.missing && 'file is gone', s.ignored && 'ignored']
        .filter(Boolean).join(' · ')))];
  const i = openable.indexOf(s);
  return h('li', { class: isMe ? 'me' : '' }, i < 0 || isMe ? h('div', { class: 'lineage-step' }, body)
    : h('button', { type: 'button', class: 'lineage-step', title: 'Open this version (← → step through the chain)',
        onClick: () => openLarge(i, openable) }, body));
}

// ---- the style's story, cut at the moment this image was made

const EVENT = { created: 'Created', fork: 'Made from', commit: 'Edited with Claude', edit: 'Changed in your words',
  distil: 'Distilled from your ratings', off: 'Switched off', on: 'Switched on' };
const EARLIER_SHOWN = 3;   // the changes just before the image; older ones wait behind the full-history link
const when = (at) => `${shortDate(at.slice(0, 10))} ${at.slice(11)}`;

function styleStory(im, batch, box) {
  api(`styles/history/${encodeURIComponent(im.style)}`).then((d) => {
    const made = `${im.date || batch.slice(0, 10)} ${im.time || '23:59'}`;
    const evs = d.events.filter((e) => !e.undone && e.kind !== 'fork-out' && EVENT[e.kind]);
    const before = evs.filter((e) => e.at <= made), after = evs.filter((e) => e.at > made);
    const hidden = Math.max(0, before.length - EARLIER_SHOWN);
    const full = h('a', { href: `#/styles/${encodeURIComponent(im.style)}`, class: 'small' }, 'Full history');
    const rows = [
      hidden && h('li', { class: 'muted small' }, `${plural(hidden, 'earlier change')}…`),
      ...before.slice(hidden).map((e) => eventRow(e)),
      h('li', { class: 'lineage-now' }, h('strong', {}, 'This image'),
        h('span', { class: 'muted small' }, ` ${when(made.replace(' 23:59', ''))}${before.length ? '' : ' · before any recorded change'}`)),
      ...after.map((e) => eventRow(e, true))];
    box.replaceChildren(
      h('div', { class: 'lineage-head' }, h('strong', {}, `The style · ${d.name}`),
        h('span', { class: 'muted small' }, after.length ? `${plural(after.length, 'change')} since this image` : 'unchanged since this image'), full),
      h('ol', { class: 'lineage-events' }, rows.filter(Boolean)));
    box.hidden = false;
  }).catch(() => {});   // a style that's gone, or an older server: the versions above still stand on their own
}

function eventRow(e, later) {
  // Only the edit log (it has an id) holds your words; a commit's subject is a note about many styles at once,
  // so it stays in the tooltip.
  const yours = e.id && !['commit', 'off', 'on'].includes(e.kind) ? e.title : '';
  return h('li', { class: later ? 'later' : '', title: yours ? null : e.title || null },
    h('span', {}, h('strong', {}, EVENT[e.kind], e.of ? ` ${e.of}` : ''), h('span', { class: 'muted small' }, ` ${when(e.at)}${later ? ' · after this image' : ''}`)),
    yours && h('span', { class: 'lineage-asked', title: yours }, `“${yours}”`),
    e.id && e.detail && h('span', { class: 'muted small lineage-detail', title: e.detail }, e.detail));
}
