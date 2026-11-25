// New run: make images with my styles from the page instead of from chat.
//   #/new                     a batch: one or more styles, N images each, fresh subjects
//   #/new?mode=one            one image (or a few) from one style and a subject I write
//   #/new?style=a,b           start with exactly these styles picked (from the Taste page or a batch)
//   Palette only (24 Nov 2026): One image without a style: pick a palette, write what you want, Codex writes the prompt
//   Experimental (23 Nov 2026): a batch switch for bolder subjects, new palettes and a wildcard on all but the first image
// The form survives leaving the page (sessionStorage), so a look at another batch never loses a half-made run.
// Nothing spends until "Start": the preview prints the exact prompts for free, the cost is always in view.
import { api, styles, refreshStyles } from './api.js';
import { allowance, costBlock, route, routeBlocker } from './cost.js';
import { job, enqueueRun, onJob } from './job.js';
import { h, plural, toast, showError } from './ui.js';

const KEY = 'taste-newrun';
const RATIOS = { mixed: 'Mixed', wide: 'Wide', portrait: 'Portrait', square: 'Square' };
const RATIO_HINT = {
  mixed: 'Wide, portrait, square, wide in turn: one batch shows how the style holds up in each shape.',
  wide: '16:9, desktop and Teams backgrounds.', portrait: '4:5, LinkedIn posts and phones.', square: '1:1, LinkedIn posts.',
};
const fresh = () => ({ mode: 'batch', styles: [], n: 4, ratio: 'mixed', wildcards: true, experimental: false, useKept: true, subjects: {}, hints: {}, name: '',
  one: { style: '', subject: '', ratio: 'wide', n: 1, palOnly: false, palette: [], palFrom: '', text: '', prompt: '', summary: '' } });
const PAL = '__palette';

let kept = {};   // style -> how many images are kept as examples
let state, all, view, alw = null, filter = '', writing = {}, unsub = null, composing = false;

export async function renderNewRun(el, query) {
  view = el;
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Loading the styles…'));
  all = await styles();
  try { state = { ...fresh(), ...JSON.parse(sessionStorage.getItem(KEY) || '{}') }; } catch { state = fresh(); }
  state.one = { ...fresh().one, ...state.one };
  if (query.get('mode') === 'one' || query.get('mode') === 'batch') state.mode = query.get('mode');
  // Coming from a style ("New run" on Taste, a batch, a new style): start with exactly those styles, in view.
  // A key the cached list doesn't know yet means the list is stale: read it again once.
  let pre = (query.get('style') || '').split(',').filter(Boolean);
  if (pre.some((k) => !all[k])) all = await refreshStyles();
  pre = pre.filter((k) => all[k]);
  // The saved form can name a style that was since renamed or deleted: drop it, or the form can't draw (25 Nov 2026).
  const before = state.styles.length;
  state.styles = state.styles.filter((k) => all[k]);
  if (!all[state.one.style]) state.one.style = '';
  if (state.styles.length !== before) save();
  if (pre.length) {
    filter = '';
    if (state.mode === 'one') state.one.style = pre[0];
    else state.styles = pre;
    save();
  }
  if (!state.one.style) state.one.style = state.styles[0] || Object.keys(all)[0];
  document.title = 'New run · taste';
  kept = await api('kept').then((d) => d.counts).catch(() => ({}));
  draw();
  allowance().then((a) => { alw = a; }).catch((e) => { alw = { error: e.message }; }).finally(drawSummary);
  unsub?.();
  unsub = onJob(() => { if (!view.isConnected || !view.querySelector('.newrun')) { unsub?.(); unsub = null; return; } drawStart(); });
}

const save = () => sessionStorage.setItem(KEY, JSON.stringify(state));
const total = () => (state.mode === 'one' ? state.one.n : state.styles.length * state.n);
const lines = (s) => (state.subjects[s] || '').split('\n').map((x) => x.trim()).filter(Boolean);

// ---------------------------------------------------------------- layout

let form, summary, startBtn, previewBtn;

function draw() {
  form = h('div', { class: 'newrun-form' });
  summary = h('aside', { class: 'newrun-summary', 'aria-label': 'This run' });
  view.replaceChildren(h('div', { class: 'newrun' },
    h('header', { class: 'grid-head' },
      h('hgroup', {}, h('h1', {}, 'New run'),
        h('p', {}, 'Runs wait in a queue and go one at a time. Nothing is spent until you press Start.')),
      h('nav', { class: 'filters', 'aria-label': 'Kind of run' },
        h('a', { href: '#/new?mode=batch', 'aria-current': state.mode === 'batch' ? 'page' : null }, 'Batch'),
        h('a', { href: '#/new?mode=one', 'aria-current': state.mode === 'one' ? 'page' : null }, 'One image'))),
    h('div', { class: 'newrun-cols' }, form, summary)));
  drawForm();
  drawSummary();
  view.querySelector('.newrun').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !startBtn.disabled) { e.preventDefault(); start(); }
  });
}

function drawForm(focusSel) {
  const keep = focusSel || selectorOf(document.activeElement);
  form.replaceChildren(...(state.mode === 'one' ? oneForm() : batchForm()).filter(Boolean));   // no stray "null" when a part is hidden
  if (keep) form.querySelector(keep)?.focus();
}

// Redraws replace the nodes: remember which control had the focus by a stable selector.
function selectorOf(el) {
  if (!el || !form?.contains(el)) return null;
  if (el.dataset.focus) return `[data-focus="${CSS.escape(el.dataset.focus)}"]`;
  return null;
}

// ---------------------------------------------------------------- kept examples

// Shown only when one of the styles has images kept as examples (the star in the large view and on Taste).
function keptTick(keys) {
  const withKept = keys.filter((k) => kept[k]);
  if (!withKept.length) return null;
  const list = withKept.map((k) => `${all[k].name} (${kept[k]})`).join(', ');
  return h('label', { class: 'nr-block nr-check kept-tick' },
    h('input', { type: 'checkbox', checked: state.useKept, 'data-focus': 'use-kept', onChange: (e) => { state.useKept = e.target.checked; save(); } }),
    h('span', {}, `Send my kept examples along as references: ${list}. `,
      h('small', { class: 'muted' }, 'Up to 2 go with each image. No extra images are spent; the result stays closer to the examples.')));
}

// ---------------------------------------------------------------- batch

function batchForm() {
  const keys = Object.keys(all).sort((a, b) => all[a].name.localeCompare(all[b].name));
  const shown = keys.filter((k) => !filter || all[k].name.toLowerCase().includes(filter.toLowerCase()) || k.includes(filter.toLowerCase()));
  return [
    h('fieldset', { class: 'nr-block' },
      h('legend', {}, 'Styles ', h('span', { class: 'muted' }, state.styles.length ? `· ${state.styles.length} picked` : '· pick one or more')),
      h('div', { class: 'nr-row' },
        h('input', { type: 'search', placeholder: 'Filter styles', value: filter, 'aria-label': 'Filter styles', 'data-focus': 'filter',
          onInput: (e) => { filter = e.target.value; drawForm(); } }),
        // Select all picks every style in view: all of them, or only those the filter shows.
        shown.some((k) => !state.styles.includes(k)) && h('button', { class: 'ghost small', 'data-focus': 'all',
          onClick: () => { state.styles = [...new Set([...state.styles, ...shown])]; save(); drawForm('[data-focus="clear"]'); drawSummary(); } },
          filter && shown.length < keys.length ? `Select the ${shown.length} shown` : 'Select all'),
        state.styles.length > 0 && h('button', { class: 'ghost small', 'data-focus': 'clear',
          onClick: () => { state.styles = []; save(); drawForm('[data-focus="all"]'); drawSummary(); } }, 'Clear')),
      h('div', { class: 'style-picker' },
        shown.map((k) => h('button', {
          type: 'button', class: 'style-chip', 'aria-pressed': String(state.styles.includes(k)), 'data-focus': 'chip-' + k,
          onClick: () => toggleStyle(k) },
        h('span', { class: 'swatches', 'aria-hidden': 'true' }, (all[k].palette || []).slice(0, 5).map((c) => h('i', { style: { background: c } }))),
        h('span', {}, all[k].name))),
        !shown.length && h('p', { class: 'muted small' }, 'No style matches.'))),

    h('label', { class: 'nr-block nr-check nr-exp' + (state.experimental ? ' on' : '') },
      h('input', { type: 'checkbox', role: 'switch', checked: state.experimental, 'data-focus': 'exp',
        onChange: (e) => { state.experimental = e.target.checked; save(); drawForm(); drawSummary(); } }),
      h('span', {}, h('strong', {}, 'Experimental'), ' · try things the style has not done yet. ',
        h('small', { class: 'muted' }, 'Codex writes bolder subjects, each image gets a new palette, your ratings do not steer the picks, and every image after the first pushes one thing to an extreme.'))),

    h('fieldset', { class: 'nr-block' },
      h('legend', {}, 'Images'),
      h('div', { class: 'nr-grid' },
        h('div', {}, h('span', { class: 'nr-label' }, 'Per style'), stepper(state.n, PER_STYLE, (v) => { state.n = v; }, 'n')),
        h('div', {}, h('span', { class: 'nr-label' }, 'Shape'), ratioSeg(state.ratio, RATIOS, (v) => { state.ratio = v; }, 'ratio'))),
      h('p', { class: 'muted small' }, RATIO_HINT[state.ratio]),
      h('label', { class: 'nr-check' },
        h('input', { type: 'checkbox', checked: state.experimental || state.wildcards, disabled: state.n < 2 || state.experimental, 'data-focus': 'wild',
          onChange: (e) => { state.wildcards = e.target.checked; save(); } }),
        h('span', {}, state.experimental ? 'Wildcards: on for every image after the first (Experimental)'
          : 'Wildcard: the last image of each style pushes one thing to an extreme (light, framing, palette, scale, detail or mood)'))),

    keptTick(state.styles),
    h('fieldset', { class: 'nr-block' },
      h('legend', {}, 'Subjects'),
      state.styles.length
        ? [h('p', { class: 'muted small' }, 'One subject per line. Lines you leave empty are written by Codex when the run starts (about 15 s per style), avoiding subjects used before.'),
           state.styles.map(subjectCard)]
        : h('p', { class: 'muted small' }, 'Pick a style first.')),

    h('label', { class: 'nr-block nr-name' }, h('span', { class: 'nr-label' }, 'Name (optional)'),
      h('input', { type: 'text', value: state.name, maxlength: 60, placeholder: state.styles.slice(0, 2).join('-') || 'e.g. winter-test',
        'data-focus': 'name', onInput: (e) => { state.name = e.target.value; save(); } }),
      h('small', { class: 'muted' }, 'Becomes the folder name, after the date.')),
  ];
}

function toggleStyle(k) {
  state.styles = state.styles.includes(k) ? state.styles.filter((s) => s !== k) : [...state.styles, k];
  save();
  drawForm();
  drawSummary();
}

function subjectCard(k) {
  const s = all[k];
  const have = lines(k).length;
  const left = Math.max(0, state.n - have);
  const busy = writing[k];
  return h('section', { class: 'subject-card' },
    h('header', {},
      h('strong', {}, s.name),
      h('span', { class: 'swatches', 'aria-hidden': 'true' }, (s.palette || []).slice(0, 5).map((c) => h('i', { style: { background: c } }))),
      h('span', { class: 'muted small count-note' },
        have > state.n ? `${have} written, the first ${state.n} are used`
          : left ? `${have} of ${state.n} written · ${left} by Codex at start` : `${state.n} of ${state.n} written`),
      h('button', { class: 'ghost small', 'aria-label': `Remove ${s.name}`, onClick: () => toggleStyle(k) }, 'Remove')),
    h('textarea', { rows: Math.max(2, Math.min(8, state.n)), 'data-focus': 'subjects-' + k, 'aria-label': `Subjects for ${s.name}`,
      placeholder: (s.subjects || []).slice(0, 2).map((x) => `e.g. ${x}`).join('\n'),
      onInput: (e) => { state.subjects[k] = e.target.value; save(); updateCount(e.target, k); drawSummary(); } },
    state.subjects[k] || ''),
    h('div', { class: 'nr-row' },
      h('input', { type: 'text', class: 'hint', maxlength: 200, value: state.hints[k] || '', 'data-focus': 'hint-' + k,
        placeholder: 'Direction for Codex (optional): e.g. winter, at night', 'aria-label': `Direction for Codex, ${s.name}`,
        onInput: (e) => { state.hints[k] = e.target.value; save(); } }),
      h('button', { class: 'secondary outline small-btn', disabled: !!busy || !left, 'aria-busy': busy ? 'true' : null,
        'data-focus': 'write-' + k, onClick: () => writeSubjects(k),
        title: left ? `Codex writes ${left} now, so you can read and edit them before the run` : 'Every line is written' },
      busy ? `Writing… ${busy}` : left ? `Write ${left} now` : 'All written'),
      h('button', { class: 'ghost small', disabled: !left, 'data-focus': 'examples-' + k, onClick: () => useExamples(k),
        title: "Fill the empty lines with the style's own example subjects" }, 'Use examples')));
}

function updateCount(textarea, k) {
  const have = lines(k).length, left = Math.max(0, state.n - have);
  const note = textarea.closest('.subject-card').querySelector('.count-note');
  note.textContent = have > state.n ? `${have} written, the first ${state.n} are used`
    : left ? `${have} of ${state.n} written · ${left} by Codex at start` : `${state.n} of ${state.n} written`;
  const btns = textarea.closest('.subject-card').querySelectorAll('.nr-row button');
  if (!writing[k]) { btns[0].disabled = !left; btns[0].textContent = left ? `Write ${left} now` : 'All written'; }
  btns[1].disabled = !left;
}

async function writeSubjects(k) {
  const left = Math.max(0, state.n - lines(k).length);
  if (!left) return;
  const t0 = Date.now();
  writing[k] = '0 s';
  drawForm(`[data-focus="write-${k}"]`);
  const tick = setInterval(() => { writing[k] = `${Math.round((Date.now() - t0) / 1000)} s`; const b = form.querySelector(`[data-focus="write-${k}"]`); if (b) b.textContent = `Writing… ${writing[k]}`; }, 1000);
  try {
    const r = await api('text/subjects', { method: 'POST', body: { style: k, n: left, hint: state.hints[k] || '', experimental: state.experimental } });
    state.subjects[k] = [...lines(k), ...r.subjects].join('\n');
    save();
    toast(`${plural(r.subjects.length, 'subject')} for ${all[k].name}${r.dry_run ? ' (dry run stand-ins)' : `, in ${r.seconds} s`}. Edit any line you don't like.`);
  } catch (err) {
    showError(err);
  } finally {
    clearInterval(tick);
    delete writing[k];
    drawForm(`[data-focus="subjects-${k}"]`);
    drawSummary();
  }
}

function useExamples(k) {
  const have = lines(k);
  const pool = (all[k].subjects || []).filter((x) => !have.includes(x));
  state.subjects[k] = [...have, ...pool.slice(0, Math.max(0, state.n - have.length))].join('\n');
  save();
  drawForm(`[data-focus="subjects-${k}"]`);
  drawSummary();
}

// ---------------------------------------------------------------- one image

function oneForm() {
  const o = state.one;
  const keys = Object.keys(all).sort((a, b) => all[a].name.localeCompare(all[b].name));
  const st = all[o.style];
  return [
    h('fieldset', { class: 'nr-block' },
      h('legend', {}, 'Style'),
      h('div', { class: 'nr-row' },
        h('select', { 'data-focus': 'one-style', 'aria-label': 'Style', onChange: (e) => {
          o.palOnly = e.target.value === PAL;
          if (!o.palOnly) o.style = e.target.value;
          save(); drawForm(); drawSummary(); } },
          h('option', { value: PAL, selected: o.palOnly }, 'No style · palette only'),
          keys.map((k) => h('option', { value: k, selected: !o.palOnly && k === o.style }, all[k].name))),
        !o.palOnly && st && h('span', { class: 'swatches big', 'aria-hidden': 'true' }, (st.palette || []).map((c) => h('i', { style: { background: c } })))),
      o.palOnly ? h('p', { class: 'muted small' }, 'No style rules: Codex writes the whole prompt from your words, in the palette you pick.')
        : st?.description && h('p', { class: 'muted small' }, st.description)),
    ...(o.palOnly ? paletteParts() : [keptTick(o.style ? [o.style] : []),
    h('fieldset', { class: 'nr-block' },
      h('legend', {}, 'Subject'),
      h('textarea', { rows: 3, maxlength: 200, 'data-focus': 'one-subject', 'aria-label': 'Subject',
        placeholder: (st?.subjects || []).slice(0, 1).map((x) => `e.g. ${x}`).join('') || 'What the image shows',
        onInput: (e) => { o.subject = e.target.value; save(); drawStart(); } }, o.subject),
      st?.subjects?.length > 0 && h('details', { class: 'small' },
        h('summary', {}, "The style's example subjects"),
        h('ul', { class: 'plain examples-list' }, st.subjects.map((x) => h('li', {},
          h('button', { class: 'ghost small', onClick: () => { o.subject = x; save(); drawForm('[data-focus="one-subject"]'); drawStart(); } }, x))))))]),
    h('fieldset', { class: 'nr-block' },
      h('legend', {}, 'Images'),
      h('div', { class: 'nr-grid' },
        h('div', {}, h('span', { class: 'nr-label' }, 'How many'), stepper(o.n, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], (v) => { o.n = v; }, 'one-n')),
        h('div', {}, h('span', { class: 'nr-label' }, 'Shape'),
          ratioSeg(o.ratio, { wide: 'Wide', portrait: 'Portrait', square: 'Square' }, (v) => { o.ratio = v; }, 'one-ratio'))),
      h('p', { class: 'muted small' }, RATIO_HINT[o.ratio] + (o.n > 1 ? ' Same prompt each time: Codex varies the result on its own.' : ''))),
  ];
}

// Palette only: the palettes of my styles to pick from, my own words, and the prompt Codex writes from them.
function paletteParts() {
  const o = state.one;
  const keys = Object.keys(all).filter((k) => (all[k].palette || []).length >= 2).sort((a, b) => all[a].name.localeCompare(all[b].name));
  const shown = keys.filter((k) => !filter || all[k].name.toLowerCase().includes(filter.toLowerCase()));
  const pick = (k) => {
    if (o.palFrom === k) return;
    o.palFrom = k; o.palette = [...all[k].palette]; o.prompt = ''; o.summary = '';   // the old prompt names the old colours
    save(); drawForm(`[data-focus="pal-${k}"]`); drawSummary();
  };
  return [
    h('fieldset', { class: 'nr-block' },
      h('legend', {}, 'Palette ', h('span', { class: 'muted' }, o.palFrom && all[o.palFrom] ? `· from ${all[o.palFrom].name}` : '· pick one')),
      keys.length > 8 && h('div', { class: 'nr-row' },
        h('input', { type: 'search', placeholder: 'Filter palettes by style', value: filter, 'aria-label': 'Filter palettes', 'data-focus': 'filter',
          onInput: (e) => { filter = e.target.value; drawForm(); } })),
      h('div', { class: 'style-picker', role: 'radiogroup', 'aria-label': 'Palette' },
        shown.map((k) => h('button', { type: 'button', class: 'style-chip', role: 'radio', 'aria-checked': String(o.palFrom === k),
          'aria-pressed': String(o.palFrom === k), 'data-focus': 'pal-' + k, onClick: () => pick(k), title: all[k].palette.join(' ') },
        h('span', { class: 'swatches', 'aria-hidden': 'true' }, all[k].palette.slice(0, 7).map((c) => h('i', { style: { background: c } }))),
        h('span', {}, all[k].name))),
        !shown.length && h('p', { class: 'muted small' }, 'No palette matches.'))),
    h('fieldset', { class: 'nr-block' },
      h('legend', {}, 'What you want'),
      h('textarea', { rows: 3, maxlength: 600, 'data-focus': 'pal-text', 'aria-label': 'What the image shows',
        placeholder: 'In your own words: what it shows, and any feel or medium you have in mind',
        onInput: (e) => { o.text = e.target.value; save(); drawStart(); syncWrite(); } }, o.text),
      h('div', { class: 'nr-row' },
        h('button', { class: 'secondary outline small-btn', 'data-focus': 'pal-write', disabled: composing || !o.text.trim() || !o.palette.length,
          'aria-busy': composing ? 'true' : null, onClick: () => compose().catch(showError),
          title: 'Codex writes the prompt now (about 15 s), so you can read and edit it before Start' },
        composing ? 'Writing the prompt…' : o.prompt ? 'Write it again' : 'Write the prompt now'),
        !o.prompt && h('small', { class: 'muted' }, 'Or just press Start: Codex writes it first.'))),
    o.prompt && h('fieldset', { class: 'nr-block' },
      h('legend', {}, 'The prompt ', h('span', { class: 'muted' }, '· edit freely')),
      h('textarea', { rows: 6, maxlength: 4000, 'data-focus': 'pal-prompt', 'aria-label': 'The prompt',
        onInput: (e) => { o.prompt = e.target.value; save(); drawStart(); } }, o.prompt),
      o.summary && h('p', { class: 'muted small' }, `Codex added: ${o.summary}`)),
  ];
}

// Typing never redraws the form (it would steal the caret): only the write button follows the text.
function syncWrite() {
  const b = form.querySelector('[data-focus="pal-write"]');
  if (b) b.disabled = composing || !state.one.text.trim() || !state.one.palette.length;
}

async function compose() {
  const o = state.one;
  composing = true;
  drawForm('[data-focus="pal-write"]');
  drawStart();
  try {
    const r = await api('text/compose', { method: 'POST', body: { text: o.text, palette: o.palette, ratio: o.ratio } });
    o.prompt = r.prompt; o.summary = r.summary || '';
    save();
    return r;
  } finally {
    composing = false;
    drawForm(o.prompt ? '[data-focus="pal-prompt"]' : '[data-focus="pal-write"]');
    drawStart();
  }
}

// ---------------------------------------------------------------- small controls

// Steps through a list of allowed values (one at a time up to 8, then bigger jumps).
const PER_STYLE = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24];
function stepper(value, steps, set, id) {
  const i = steps.indexOf(value) >= 0 ? steps.indexOf(value) : steps.findIndex((x) => x > value);
  const change = (up) => { set(steps[Math.max(0, Math.min(steps.length - 1, up ? i + 1 : i - 1))]); save(); drawForm(`[data-focus="${id}-${up ? 'up' : 'down'}"]`); drawSummary(); };
  return h('div', { class: 'stepper', role: 'group', 'aria-label': 'How many' },
    h('button', { type: 'button', class: 'secondary outline', disabled: i <= 0, 'aria-label': 'Fewer', 'data-focus': `${id}-down`, onClick: () => change(false) }, '−'),
    h('output', { 'aria-live': 'polite' }, value),
    h('button', { type: 'button', class: 'secondary outline', disabled: i < 0 || i >= steps.length - 1, 'aria-label': 'More', 'data-focus': `${id}-up`, onClick: () => change(true) }, '+'));
}

function ratioSeg(value, options, set, id) {
  return h('div', { class: 'rseg', role: 'group', 'aria-label': 'Shape' },
    Object.entries(options).map(([k, label]) => h('button', {
      type: 'button', class: 'rseg-btn', 'aria-pressed': String(value === k), 'data-focus': `${id}-${k}`,
      onClick: () => { set(k); save(); drawForm(`[data-focus="${id}-${k}"]`); } }, label)));
}

// ---------------------------------------------------------------- summary, preview, start

function drawSummary() {
  if (!summary) return;
  const n = total();
  const codexStyles = state.mode === 'batch' ? state.styles.filter((k) => lines(k).length < state.n).length : 0;
  previewBtn = h('button', { class: 'secondary outline', onClick: preview, disabled: state.mode !== 'batch' || !state.styles.length,
    title: state.mode === 'batch' ? 'The exact prompts, printed without running Codex' : 'One image: the prompt is the style block plus your subject' }, 'Preview the prompts (free)');
  startBtn = h('button', { class: 'start', onClick: start });
  summary.replaceChildren(
    h('h2', {}, 'This run'),
    state.mode === 'batch'
      ? h('p', { class: 'small' }, state.styles.length
        ? `${state.experimental ? 'Experimental: ' : ''}${plural(state.styles.length, 'style')} × ${state.n} = ${plural(n, 'image')}, ${RATIOS[state.ratio].toLowerCase()} shapes${state.experimental ? ', new palettes, bolder subjects' : state.wildcards && state.n > 1 ? ', one wildcard each' : ''}.`
        : 'Pick at least one style.')
      : h('p', { class: 'small' }, state.one.palOnly
        ? `${plural(n, 'image')}, palette only${state.one.palFrom && all[state.one.palFrom] ? ` (${all[state.one.palFrom].name})` : ''}, ${state.one.ratio}.`
        : `${plural(n, 'image')} in ${all[state.one.style]?.name || '…'}, ${state.one.ratio}.`),
    costBlock(alw, n, { onRoute: drawSummary, extra: codexStyles ? `Codex writes the missing subjects first: about 15 s for each of ${plural(codexStyles, 'style')}.` : '' }),
    h('p', { class: 'muted small' }, (route() === 'cloudflare' ? 'Images land in generated/codex/<date>-<name>-flux/' : 'Images land in generated/codex/<date>-<name>/') + ' (kept off GitHub). You get a message here, and on your desktop if you allow it, when they are ready.'),
    h('div', { class: 'nr-actions' }, startBtn, state.mode === 'batch' && previewBtn),
    h('p', { class: 'muted small keys' }, h('kbd', {}, 'Ctrl'), ' + ', h('kbd', {}, 'Enter'), ' starts'));
  drawStart();
}

function blocker() {
  if (routeBlocker(alw)) return routeBlocker(alw);
  if (state.mode === 'batch') return !state.styles.length ? 'Pick at least one style.' : '';
  const o = state.one;
  if (o.palOnly) return composing ? 'Writing the prompt…' : !o.palette.length ? 'Pick a palette.' : !o.text.trim() && !o.prompt.trim() ? 'Write what you want.' : '';
  return !o.subject.trim() ? 'Write a subject.' : '';
}

function drawStart() {
  if (!startBtn) return;
  const why = blocker();
  const n = total();
  const busy = job.running || job.queue?.length;
  startBtn.disabled = !!why || startBtn.getAttribute('aria-busy') === 'true';
  startBtn.title = why;
  startBtn.textContent = why ? why
    : alw?.dry_run ? `Dry run: ${plural(n, 'image')}, nothing spent`
    : busy ? `Add to queue · ${plural(n, 'image')}` : `Start${state.mode === 'batch' && state.experimental ? ' experimental' : ''} · make ${plural(n, 'image')}`;
}

function body() {
  if (state.mode === 'one') {
    const o = state.one;
    if (o.palOnly) return { kind: 'single', route: route(), style: '', palette: o.palette, text: o.text, prompt: o.prompt, ratio: o.ratio, n: o.n };
    return { kind: 'single', route: route(), style: o.style, subject: o.subject, ratio: o.ratio, n: o.n, use_kept: state.useKept && !!kept[o.style] };
  }
  return { kind: 'batch', route: route(), styles: state.styles, n: state.n, ratio: state.ratio, wildcards: state.wildcards, experimental: state.experimental, name: state.name, use_kept: state.useKept,
    subjects: Object.fromEntries(state.styles.map((k) => [k, lines(k)])), hints: state.hints };
}

async function start() {
  if (blocker()) return;
  startBtn.setAttribute('aria-busy', 'true');
  startBtn.disabled = true;
  try {
    if (state.mode === 'one' && state.one.palOnly && !state.one.prompt.trim()) {   // Start without a prompt yet: Codex writes it first
      await compose();
      startBtn.setAttribute('aria-busy', 'true');
      startBtn.disabled = true;
    }
    const res = await enqueueRun(body(), { go: '#/' });
    const title = res.queue?.find((q) => q.id === res.queued_id)?.title || res.title || 'the run';
    toast(res.position <= 1 ? `Started: ${title}` : `Queued, number ${res.position} in line: ${title}`);
    // The subjects and name were for this run: clear them, keep the styles and settings for the next one.
    if (state.mode === 'batch') { state.subjects = {}; state.name = ''; } else { state.one.subject = ''; state.one.text = ''; state.one.prompt = ''; state.one.summary = ''; }
    save();
  } catch (err) {
    startBtn.removeAttribute('aria-busy');
    drawStart();
    showError(err);
  }
}

async function preview() {
  const list = h('div', { class: 'preview-list', 'aria-busy': 'true' }, 'Printing the prompts (a few seconds)…');
  const dlg = h('dialog', { class: 'review preview-dialog' }, h('article', {},
    h('header', {}, h('hgroup', {}, h('h3', {}, 'The prompts this run would use'),
      h('p', { class: 'muted small' }, 'Printed by batch.py without running Codex: nothing spent.'))),
    list,
    h('footer', {}, h('button', { class: 'secondary', onClick: () => dlg.close() }, 'Close'))));
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  try {
    const { prompts } = await api('preview', { method: 'POST', body: body() });
    list.removeAttribute('aria-busy');
    list.replaceChildren(h('div', {},
      prompts.some((p) => p.placeholder) && h('p', { class: 'notice' }, 'Rows marked "example subject" use one of the style\'s examples as a stand-in: Codex writes a fresh subject there when the run starts.'),
      h('ul', { class: 'plain' }, prompts.map((p) => h('li', { class: 'preview-item' },
        h('div', { class: 'preview-meta' }, h('strong', {}, p.name), h('code', {}, p.change || ''),
          p.placeholder && h('span', { class: 'count' }, 'example subject'),
          p.refs?.length > 0 && h('span', { class: 'count' }, `★ with ${plural(p.refs.length, 'kept example')}`)),
        h('p', { class: 'prompt' }, p.prompt))))));
  } catch (err) {
    list.removeAttribute('aria-busy');
    list.replaceChildren(h('p', {}, `Could not print the prompts: ${err.message}`));
  }
}
