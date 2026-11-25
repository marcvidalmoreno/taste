// "How it got here" (25 Nov 2026): the versions an image came from, oldest first, ending with itself, in both
// large views. Each step says how it was made (batch, remix, variations…) and what was asked. A click opens that
// version in the Gallery large view, stepping through the chain with ← →, so the changes can be flicked through
// in place. Hidden when the image has no earlier version: a fresh image needs no history line.
import { api, allStyles } from './api.js';
import { h, thumbUrl, batchTitle, shortDate, RATING_LABELS } from './ui.js';
import { KIND } from './job.js';
import { openLarge } from './gallery.js';

const cache = new Map();   // "batch/name" -> steps

// What each variation type changed (scripts/variations.py), in a few words.
const CHANGE_WORDS = { palette: 'new palette and light', subject: 'new subject', composition: 'new framing', mood: 'other time of day' };

export function historySection(im, batch) {
  const box = h('section', { class: 'lineage', 'aria-label': 'How it got here', hidden: true });
  const k = `${batch}/${im.name}`;
  const show = (steps, names) => {
    if (steps.length < 2) { box.hidden = true; return; }
    // The versions that open in the Gallery large view, this image last, so ← → walk the whole chain.
    const openable = steps.filter((s) => !s.given && !s.missing && !s.ignored);
    box.replaceChildren(
      h('div', { class: 'lineage-head' }, h('strong', {}, 'How it got here'),
        h('span', { class: 'muted small' }, steps.length === 2 ? '1 step' : `${steps.length - 1} steps, oldest first`)),
      h('ol', { class: 'lineage-list' }, steps.map((s, i) => stepRow(s, i === steps.length - 1, openable, names))));
    box.hidden = false;
  };
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
