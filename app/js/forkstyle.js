// Fork a style (24 Nov 2026): a new style made from an existing one, opened from a Taste card ("Fork…") or from
// "Change the style" ("As a new style…", with the typed change carried over).
// 1. A name and what should be different. "Propose the fork": Codex writes the variant (read-only, ~30 s);
//    "Copy as it is": the parent as it is, no Codex.
// 2. Every field can be edited; the words that differ from the parent are marked under each field.
// 3. Create fork: taste/styles/<key>.json keeps the parent's shape, with no images or ratings. First run / Undo.
import { api, styles, refreshStyles } from './api.js';
import { fieldEditors, missingFields, createdBlock } from './newstyle.js';
import { undoEdit } from './styleedit.js';
import { h, showError } from './ui.js';
import { isLocalOnly, LOCAL_NOTE } from './cost.js';

const QUICK = ['at night', 'in winter', 'warmer colours', 'cooler colours', 'calmer, fewer elements', 'more playful', 'more melancholy'];

// ctx: {style, change?, onCreated?(key | null)}: null after Undo
export async function openFork(ctx) {
  const parent = (await styles())[ctx.style];
  if (!parent) return showError(new Error('Only a style that is on can be forked: switch it on in Styles first.'));
  const st = { step: 1, name: '', change: ctx.change || '', busy: 0, proposal: null, style: null, rec: null, key: '' };
  const body = h('div');
  const foot = h('footer');
  let mainBtn, hint;
  const done = (key) => (ctx.onCreated ? ctx.onCreated(key) : key ? (location.hash = '#/taste/' + encodeURIComponent(key))
    : window.dispatchEvent(new HashChangeEvent('hashchange')));
  const dlg = h('dialog', { class: 'variations style-edit new-style' }, h('article', {},
    h('header', { class: 'var-head' },
      h('span', { class: 'swatches big', 'aria-hidden': 'true' }, (parent.palette || []).slice(0, 5).map((c) => h('i', { style: { background: c } }))),
      h('hgroup', {}, h('h3', {}, `Fork a style: ${parent.name}`),
        h('p', {}, `A new style that starts as ${parent.name}, with the difference you describe. ${parent.name} stays as it is`))),
    body, foot));
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && mainBtn && !mainBtn.disabled) { e.preventDefault(); mainBtn.click(); } });
  document.body.append(dlg);
  dlg.showModal();
  draw('#fk-name');

  function draw(focus) {
    const steps = { 1: [stepOne, footOne], 2: [stepTwo, footTwo], 3: [stepThree, footThree] }[st.step];
    body.replaceChildren(...steps[0]().filter(Boolean));
    foot.replaceChildren(...steps[1]().filter(Boolean));
    dlg.querySelector(focus)?.focus();
  }

  // ------------------------------------------------------------ step 1: name and what differs

  function stepOne() {
    return [
      h('label', { class: 'nr-label', for: 'fk-name' }, 'Name of the new style'),
      h('input', { id: 'fk-name', maxlength: 60, value: st.name, placeholder: `e.g. Night ${parent.name.toLowerCase()}`,
        onInput: (e) => { st.name = e.target.value; drawFoot(); } }),
      h('label', { class: 'nr-label', for: 'fk-change' }, 'What should be different?'),
      h('textarea', { id: 'fk-change', rows: 3, maxlength: 400, placeholder: 'e.g. after dark: violet and deep blue, warm window lights',
        onInput: (e) => { st.change = e.target.value; drawFoot(); } }, st.change),
      h('div', { class: 'quick', 'aria-label': 'Quick picks: add to the change' }, QUICK.map((q) => h('button', { type: 'button', class: 'chip-btn',
        onClick: () => { st.change = st.change.trim() ? `${st.change.trim().replace(/[,.]$/, '')}, ${q}` : q; draw('#fk-change'); } }, '+ ', q))),
      h('p', { class: 'muted small' }, 'Codex reads the whole style and writes the variant; you check every field before anything is made. The fork starts with no images or ratings.'),
      isLocalOnly() && h('p', { class: 'notice small local-note' }, LOCAL_NOTE, ' Copy as it is still works. ', h('a', { href: '#/models' }, 'Models page')),
    ];
  }

  function footOne() {
    mainBtn = h('button', { onClick: () => propose(false) });
    const copy = h('button', { id: 'fk-copy', class: 'secondary outline', title: 'No Codex: the same style under a new name, to edit yourself', onClick: () => propose(true) }, 'Copy as it is');
    queueMicrotask(drawFoot);
    return [h('button', { class: 'secondary', onClick: () => dlg.close() }, 'Cancel'), h('span', { class: 'spacer' }), copy, mainBtn];
  }

  function drawFoot() {
    if (st.step !== 1 || !mainBtn) return;
    const named = !!st.name.trim();
    mainBtn.disabled = !named || !st.change.trim() || !!st.busy || isLocalOnly();
    mainBtn.title = isLocalOnly() ? LOCAL_NOTE : '';
    mainBtn.setAttribute('aria-busy', st.busy ? 'true' : 'false');
    mainBtn.textContent = st.busy ? `Codex is writing the fork… ${st.busy} s` : 'Propose the fork';
    foot.querySelector('#fk-copy').disabled = !named || !!st.busy;
  }

  async function propose(copy) {
    const t0 = Date.now();
    st.busy = 1;
    drawFoot();
    const tick = setInterval(() => { st.busy = Math.max(1, Math.round((Date.now() - t0) / 1000)); drawFoot(); }, 1000);
    try {
      st.proposal = await api('style/fork/propose', { method: 'POST', body: { style: ctx.style, name: st.name, change: st.change, copy } });
      st.style = structuredClone(st.proposal.style);
      st.step = 2;
    } catch (err) {
      showError(err);
    } finally {
      clearInterval(tick);
      st.busy = 0;
      draw(st.step === 2 ? '#fk-final-name' : null);
    }
  }

  // ------------------------------------------------------------ step 2: check every field

  const sameColours = () => JSON.stringify(st.style.palette) === JSON.stringify(parent.palette);

  function stepTwo() {
    const p = st.proposal, s = st.style;
    return [
      p.copy ? h('p', { class: 'remix-summary' }, h('strong', {}, 'Copied as it is: '), `${parent.name}, to edit yourself.`)
        : p.summary && h('p', { class: 'remix-summary' }, h('strong', {}, 'Codex: '), p.summary, p.dry_run ? '' : h('span', { class: 'muted' }, ` · ${p.seconds} s`)),
      h('p', { class: 'muted small' }, `Nothing is made yet. Changed words are marked against ${parent.name}. In the lists, one line is one option.`),
      h('label', { class: 'nr-label', for: 'fk-final-name' }, 'Name'),
      h('input', { id: 'fk-final-name', maxlength: 60, value: s.name, onInput: (e) => { s.name = e.target.value; drawCreate(); } }),
      h('section', { class: 'field-diff' },
        h('div', { class: 'field-head' }, h('strong', {}, 'Palette'),
          sameColours() ? h('span', { class: 'muted small' }, `as ${parent.name}`)
            : h('button', { type: 'button', class: 'ghost small', onClick: () => { s.palette = [...parent.palette]; if (parent.palettes) s.palettes = structuredClone(parent.palettes); draw(); } },
              `Colours changed · use ${parent.name}'s instead`)),
        h('div', { class: 'swatches ns-palette', role: 'list' }, s.palette.map((c) => h('span', { role: 'listitem', title: c }, h('i', { style: { background: c } }), h('code', {}, c))))),
      ...fieldEditors(s, drawCreate, parent),
    ];
  }

  function footTwo() {
    mainBtn = h('button', { onClick: create }, 'Create fork');
    hint = h('span', { class: 'muted small' });
    queueMicrotask(drawCreate);
    return [h('button', { class: 'secondary', onClick: () => { st.step = 1; draw('#fk-change'); } }, '← Back'),
      h('span', { class: 'spacer' }), hint, mainBtn];
  }

  function drawCreate() {
    if (st.step !== 2 || !mainBtn) return;
    const m = missingFields(st.style);
    mainBtn.disabled = m.length > 0;
    hint.textContent = m.length ? `Needs ${m.join(', ')}` : '';
  }

  async function create() {
    mainBtn.disabled = true;
    mainBtn.setAttribute('aria-busy', 'true');
    try {
      st.rec = await api('style/fork/create', { method: 'POST',
        body: { from: ctx.style, style: st.style, change: st.proposal.copy ? '' : st.change, summary: st.proposal.summary } });
      st.key = st.rec.style;
      await refreshStyles();
      done(st.key);
      st.step = 3;
      draw('#fk-first-run');
    } catch (err) {
      mainBtn.disabled = false;
      mainBtn.removeAttribute('aria-busy');
      showError(err);
    }
  }

  // ------------------------------------------------------------ step 3: created

  function stepThree() {
    return [createdBlock(st.style, `Forked from ${parent.name}. It starts with no images or ratings: a first run shows whether the difference came through.`)];
  }

  function footThree() {
    mainBtn = h('a', { id: 'fk-first-run', role: 'button', href: '#/new?mode=batch&style=' + encodeURIComponent(st.key), onClick: () => dlg.close() }, 'First run');
    return [
      h('button', { class: 'ghost small', onClick: () => { dlg.close(); undoEdit(st.rec, () => done(null)); } }, 'Undo'),
      h('span', { class: 'spacer' }),
      h('button', { class: 'secondary', onClick: () => dlg.close() }, 'Done'), mainBtn];
  }
}
