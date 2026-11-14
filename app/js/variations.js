// "Make variations": the only button here that spends Codex allowance. So the dialog shows, before
// anything runs: the style (guessed, then confirmed by Marc), what will change, and what it costs now.
import { api, styles } from './api.js';
import { job, startJob } from './job.js';
import { h, thumbUrl, plural, showError } from './ui.js';

// What one image costs (README "Allowance", measured 13 Nov 2026): ~116k tokens with a reference image,
// about a minute, 0.25–0.75 % of the five-hour window.
const COST = { tokens: 116_000, minutes: 1, fiveLow: 0.25, fiveHigh: 0.75 };
const MADE = ['palette', 'subject', 'composition', 'mood'];

// src: {batch, file, label, style}  (label like "#3" or "the seed")
export async function openVariations(src) {
  const all = await styles();
  const state = { style: null, n: 3, subject: '', note: '', guess: null, allowance: null };
  const dlg = h('dialog', { class: 'variations' });
  const body = h('div');
  const startBtn = h('button', { onClick: start });
  dlg.append(h('article', {},
    h('header', { class: 'var-head' },
      h('img', { src: thumbUrl(src.batch, src.file), alt: '' }),
      h('hgroup', {}, h('h3', {}, 'Make variations'), h('p', {}, `of ${src.label}, each changing one thing`))),
    body,
    h('footer', {}, h('button', { class: 'secondary', onClick: () => dlg.close() }, 'Cancel'), startBtn)));
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  draw();

  // Both questions go out at once; each part of the dialog fills in when its answer arrives.
  api('guess', { method: 'POST', body: { batch: src.batch, file: src.file } })
    .then((g) => { state.guess = g; }).catch((e) => { state.guess = { error: e.message }; }).finally(draw);
  api('allowance').then((a) => { state.allowance = a; }).catch((e) => { state.allowance = { error: e.message }; }).finally(draw);

  // Redraw the body; keep the focus on the control that caused it (keyboard users don't lose their place).
  function draw(focus) {
    body.replaceChildren(styleSection(), changeSection(), costSection());
    if (focus) body.querySelector(focus)?.focus();
    const a = state.allowance;
    const blocked = job.running ? 'A variation job is running: one at a time.'
      : !state.style ? 'Pick a style first.' : !a ? 'Reading the allowance…' : '';
    startBtn.disabled = !!blocked;
    startBtn.title = blocked;
    startBtn.textContent = a?.dry_run ? `Dry run: make nothing (${state.n})`
      : `Spend allowance: make ${plural(state.n, 'image')}`;
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
      h('legend', {}, 'What changes'),
      h('div', { role: 'group', class: 'count' }, [3, 4].map((n) => h('button', {
        class: state.n === n ? '' : 'secondary outline', 'aria-pressed': String(state.n === n),
        onClick: () => { state.n = n; draw('.count [aria-pressed=true]'); } }, `${n}: ${MADE.slice(0, n).join(', ')}`))),
      h('label', { class: 'small' }, 'New subject for the "subject" variation (optional)',
        h('input', { type: 'text', value: state.subject, maxlength: 200,
          placeholder: 'empty: one from the style\'s subjects', onInput: (e) => { state.subject = e.target.value; } })),
      h('label', { class: 'small' }, 'In every variation (optional): add or remove something',
        h('input', { type: 'text', value: state.note, maxlength: 200,
          placeholder: 'e.g. no planet in the sky', onInput: (e) => { state.note = e.target.value; } })));
  }

  function costSection() {
    const a = state.allowance;
    const n = state.n;
    if (!a) return h('section', { class: 'cost', 'aria-busy': 'true' }, 'Reading the allowance…');
    if (a.error) return h('section', { class: 'cost' }, `Allowance unknown: ${a.error}`);
    const over = a.week_images + n > a.week_budget;
    return h('section', { class: 'cost' },
      a.dry_run && h('p', { class: 'notice' }, 'Dry run: the app was started with --dry-run. Nothing will be generated or spent.'),
      a.now ? h('div', { class: 'meters' },
        meter('Five-hour window', a.now.five_hour), meter('This week', a.now.weekly),
        h('p', { class: 'muted small' }, `Used, from Codex's own log as of ${a.now.as_of.slice(11)} on ${a.now.as_of.slice(0, 10)}.`))
        : h('p', { class: 'small' }, `Allowance unknown: ${a.unknown_reason || 'no reading'}`),
      h('p', { class: 'small' },
        h('strong', {}, `This run: ${plural(n, 'image')}`),
        `, about ${n * COST.minutes} min and ~${Math.round(n * COST.tokens / 1000)}k tokens, ` +
        `≈ ${(n * COST.fiveLow).toFixed(1)}–${(n * COST.fiveHigh).toFixed(1)} % of the five-hour window.`),
      h('p', { class: 'small' + (over ? ' over' : ' muted') },
        `Images in the last 7 days: ${a.week_images}, budget ~${a.week_budget}` +
        (over ? ` – this run goes over the budget.` : '.')));
  }

  async function start() {
    startBtn.setAttribute('aria-busy', 'true');
    startBtn.disabled = true;
    try {
      await startJob({ batch: src.batch, file: src.file, style: state.style, n: state.n, subject: state.subject, note: state.note });
      dlg.close();
    } catch (err) {
      startBtn.removeAttribute('aria-busy');
      draw();
      showError(err);
    }
  }
}

// A used-percentage meter: one thin bar, the number written next to it (never colour alone).
function meter(label, used) {
  const pct = Math.max(0, Math.min(100, Number(used) || 0));
  return h('div', { class: 'meter' },
    h('span', {}, label),
    h('span', { class: 'bar', role: 'meter', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': pct,
                'aria-label': `${label}: ${pct} % used` }, h('i', { style: { width: pct + '%' } })),
    h('span', { class: 'num' }, `${pct} % used`));
}
