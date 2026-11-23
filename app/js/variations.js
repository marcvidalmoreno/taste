// "Variations": a few images from one, each changing one thing. Spends Codex allowance, so the dialog shows,
// before anything runs: the style (guessed, then confirmed by Marc), what will change, and what it costs now.
// Runs join the queue (one image run at a time), so a busy queue never blocks the button.
import { api, styles } from './api.js';
import { job, enqueueRun } from './job.js';
import { allowance, costBlock, makeLabel, route, routeBlocker } from './cost.js';
import { h, thumbUrl, plural, showError, toast } from './ui.js';

// What each variation keeps and changes (scripts/variations.py); any mix of them since 21 Nov 2026.
const MADE = {
  palette: 'Palette and light pulled to the style; subject and framing kept',
  subject: 'New subject; palette, light and framing kept',
  composition: 'New framing; palette and subject kept',
  mood: 'Other time of day; subject and framing kept',
};

// src: {batch, file, label, style}  (label like "#3" or "the seed")
export async function openVariations(src) {
  const all = await styles();
  const state = { style: null, changes: ['palette', 'subject', 'composition'], subject: '', note: '', guess: null, allowance: null };
  const dlg = h('dialog', { class: 'variations' });
  const body = h('div');
  const startBtn = h('button', { onClick: start });
  dlg.append(h('article', {},
    h('header', { class: 'var-head' },
      h('img', { src: thumbUrl(src.batch, src.file), alt: '' }),
      h('hgroup', {}, h('h3', {}, 'Variations'), h('p', {}, `of ${src.label}, each changing one thing`))),
    body,
    h('footer', {}, h('button', { class: 'secondary', onClick: () => dlg.close() }, 'Cancel'), startBtn)));
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  draw();

  // Both questions go out at once; each part of the dialog fills in when its answer arrives.
  api('guess', { method: 'POST', body: { batch: src.batch, file: src.file } })
    .then((g) => { state.guess = g; }).catch((e) => { state.guess = { error: e.message }; }).finally(draw);
  allowance().then((a) => { state.allowance = a; }).catch((e) => { state.allowance = { error: e.message }; }).finally(draw);

  // Redraw the body; keep the focus on the control that caused it (keyboard users don't lose their place).
  function draw(focus) {
    body.replaceChildren(styleSection(), changeSection(), costSection());
    if (focus) body.querySelector(focus)?.focus();
    const a = state.allowance;
    const n = state.changes.length;
    const blocked = !state.style ? 'Pick a style first.' : !n ? 'Pick at least one change.' : !a ? 'Reading the allowance…' : routeBlocker(a);
    startBtn.disabled = !!blocked;
    startBtn.title = blocked;
    startBtn.textContent = a?.dry_run ? `Dry run: make nothing (${n})`
      : job.running || job.queue?.length ? `Add to queue · ${plural(n, 'image')}` : makeLabel(n);
  }

  function styleSection() {
    const g = state.guess;
    const option = (key, note) => h('label', { class: 'style-opt' + (state.style === key ? ' is-on' : '') },
      h('input', { type: 'radio', name: 'style', value: key, checked: state.style === key,
                   onChange: () => { state.style = key; draw(`input[value="${key}"]`); } }),
      h('span', { class: 'style-name' }, all[key]?.name || key),
      h('span', { class: 'swatches', 'aria-hidden': 'true' }, (all[key]?.palette || []).map((c) => h('i', { style: { background: c } }))),
      note && h('small', { class: 'muted' }, note));
    const guessed = g?.top?.map((t) => t.style).filter((k) => all[k]) || [];
    const own = src.style && all[src.style] && !guessed.includes(src.style) ? src.style : null;
    const others = Object.keys(all).filter((k) => !guessed.includes(k) && k !== own);
    return h('fieldset', {},
      h('legend', {}, 'Style'),
      h('p', { class: 'muted small' }, 'The guess reads colour and composition only and is right first time about a third of the time. Look at the image and pick.'),
      !g ? h('p', { 'aria-busy': 'true', class: 'small' }, 'Guessing (the first time takes a few seconds)…')
        : g.error ? h('p', { class: 'small' }, `No guess: ${g.error}`)
        : h('div', { class: 'style-opts' },
          guessed.map((k, i) => option(k, i === 0 ? (g.far ? 'closest, but far from all' : 'closest') : `guess ${i + 1}`)),
          own && option(own, 'made with')),
      h('label', { class: 'small other' }, 'Another style',
        h('select', { onChange: (e) => { state.style = e.target.value || null; draw('.other select'); } },
          h('option', { value: '' }, '—'),
          others.map((k) => h('option', { value: k, selected: state.style === k }, all[k].name)))));
  }

  function changeSection() {
    return h('fieldset', {},
      h('legend', {}, 'What changes ', h('span', { class: 'muted small' }, '· one image per change')),
      h('div', { class: 'change-opts' }, Object.entries(MADE).map(([k, what]) => h('label', { class: 'style-opt' + (state.changes.includes(k) ? ' is-on' : '') },
        h('input', { type: 'checkbox', value: k, checked: state.changes.includes(k), onChange: (e) => {
          state.changes = e.target.checked ? [...state.changes, k] : state.changes.filter((c) => c !== k);
          draw(`.change-opts input[value="${k}"]`);
        } }),
        h('span', { class: 'style-name' }, k[0].toUpperCase() + k.slice(1)),
        h('small', { class: 'muted' }, what)))),
      state.changes.includes('subject') && h('label', { class: 'small' }, 'New subject for the "subject" variation (optional)',
        h('input', { type: 'text', value: state.subject, maxlength: 200,
          placeholder: "empty: one from the style's subjects", onInput: (e) => { state.subject = e.target.value; } })),
      h('label', { class: 'small' }, 'In every variation (optional): add or remove something',
        h('input', { type: 'text', value: state.note, maxlength: 200,
          placeholder: 'e.g. no planet in the sky', onInput: (e) => { state.note = e.target.value; } })));
  }

  function costSection() {
    return costBlock(state.allowance, state.changes.length, { onRoute: () => draw() });
  }

  async function start() {
    startBtn.setAttribute('aria-busy', 'true');
    startBtn.disabled = true;
    try {
      const res = await enqueueRun({ kind: 'variations', route: route(), batch: src.batch, file: src.file, style: state.style, changes: state.changes,
        subject: state.changes.includes('subject') ? state.subject : '', note: state.note });
      dlg.close();
      toast(res.position <= 1 ? `Making ${plural(state.changes.length, 'variation')} of ${src.label}` : `Variations of ${src.label} queued, number ${res.position}`);
    } catch (err) {
      startBtn.removeAttribute('aria-busy');
      draw();
      showError(err);
    }
  }
}
