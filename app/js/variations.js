// "Variations": a few images from one, each changing one thing. Spends Codex allowance, so the dialog shows,
// before anything runs: the style (guessed, then confirmed by Marc), what will change, and what it costs now.
// Runs join the queue (one image run at a time), so a busy queue never blocks the button.
import { api, styles } from './api.js';
import { job, enqueueRun } from './job.js';
import { allowance, costBlock, makeLabel, model, setModel, MODELS, LOCAL, isLocalOnly, preselect, resetPreselect, multiCost } from './cost.js';
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
  resetPreselect();
  const state = { style: null, changes: ['palette', 'subject', 'composition'], subject: '', note: '', guess: null, allowance: null,
    models: [model()], touched: false };   // models: one set of variations per model (25 Nov 2026)
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
    if (state.style && !state.touched) { preselect(state.style); state.models = [model()]; }   // the style's default model
    body.replaceChildren(styleSection(), changeSection(), modelSection(), costSection());
    if (focus) body.querySelector(focus)?.focus();
    const a = state.allowance;
    const n = state.changes.length;
    const k = state.models.length;
    const blocked = !state.style ? 'Pick a style first.' : !n ? 'Pick at least one change.' : !k ? 'Pick at least one model.'
      : !a ? 'Reading the allowance…'
      : state.models.includes('cloudflare') && !a.error && !a.cloudflare?.connected ? 'Connect Cloudflare first (New run, Made with: FLUX).' : '';
    startBtn.disabled = !!blocked;
    startBtn.title = blocked;
    startBtn.textContent = a?.dry_run ? `Dry run: make nothing (${n * k})`
      : k > 1 ? `Make ${plural(k, 'set')} · ${plural(n * k, 'image')}`
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

  // Made with: one or more models, or All; each makes its own set, in its own batch.
  const SEED = { edit: 'edits the seed', img2img: 'starts from the seed', prompt: "from the seed's prompt: it can't take an image" };
  function modelSection() {
    const keys = isLocalOnly() ? LOCAL : Object.keys(MODELS);
    state.models = state.models.filter((m) => keys.includes(m));
    const allOn = keys.every((m) => state.models.includes(m));
    const set = (list) => { state.models = keys.filter((m) => list.includes(m)); state.touched = true; if (state.models.length === 1) setModel(state.models[0]); };
    return h('fieldset', {},
      h('legend', {}, 'Made with ', h('span', { class: 'muted small' }, '· one set per model')),
      h('div', { class: 'change-opts model-opts' },
        h('label', { class: 'style-opt' + (allOn ? ' is-on' : '') },
          h('input', { type: 'checkbox', value: 'all', checked: allOn, onChange: (e) => { set(e.target.checked ? keys : [model()]); draw('.model-opts input[value="all"]'); } }),
          h('span', { class: 'style-name' }, 'All'), h('small', { class: 'muted' }, `${keys.length} sets, to compare`)),
        keys.map((m) => h('label', { class: 'style-opt' + (state.models.includes(m) ? ' is-on' : '') },
          h('input', { type: 'checkbox', value: m, checked: state.models.includes(m), onChange: (e) => {
            set(e.target.checked ? [...state.models, m] : state.models.filter((x) => x !== m));
            draw(`.model-opts input[value="${m}"]`);
          } }),
          h('span', { class: 'style-name' }, MODELS[m].badge),
          h('small', { class: 'muted' }, MODELS[m].local ? `free, ${SEED[MODELS[m].seed]}` : m === 'cloudflare' ? 'free, edits the seed' : 'uses the seed as a reference')))),
      isLocalOnly() && h('p', { class: 'muted small' }, 'Local only is on: only the models on this laptop.'));
  }

  function costSection() {
    if (state.models.length > 1) return multiCost(state.allowance, state.changes.length, state.models);
    return costBlock(state.allowance, state.changes.length, { onRoute: () => draw(), seed: true, picker: false });
  }

  async function start() {
    startBtn.setAttribute('aria-busy', 'true');
    startBtn.disabled = true;
    try {
      const k = state.models.length;
      const res = await enqueueRun({ kind: 'variations', models: state.models, model: state.models[0], batch: src.batch, file: src.file, style: state.style, changes: state.changes,
        subject: state.changes.includes('subject') ? state.subject : '', note: state.note });
      dlg.close();
      toast(k > 1 ? `${plural(k, 'set')} of variations of ${src.label} queued, one per model`
        : res.position <= 1 ? `Making ${plural(state.changes.length, 'variation')} of ${src.label}` : `Variations of ${src.label} queued, number ${res.position}`);
    } catch (err) {
      startBtn.removeAttribute('aria-busy');
      draw();
      showError(err);
    }
  }
}
