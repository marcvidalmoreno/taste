// Change a style from where you are looking at its images (viewer, gallery, Taste page, batch).
// Say what should change ("fewer elements, less repetition"); Codex proposes an edit to the style's fields (read-only,
// ~15 s), shown field by field with the changed words marked; untick what you don't want, then apply. Or skip
// Codex and add your words as they are, as a "lean towards" or an "avoid" line. Applying rewrites
// taste/styles/<style>.json, rebuilds taste.json, and every image made after that uses it. Each edit can be undone.
import { api, styles, archivedStyles, refreshStyles } from './api.js';
import { wordDiff } from './remix.js';
import { openFork } from './forkstyle.js';
import { h, thumbUrl, toast, showError } from './ui.js';
import { isLocalOnly, LOCAL_NOTE } from './cost.js';

export const FIELDS = { description: 'Description', light: 'Light', composition: 'Composition', camera_or_medium: 'Medium',
  mood: 'Mood', texture_detail: 'Detail', prefer: 'Lean towards', avoid: 'Avoid', subjects: 'Subjects' };
const QUICK = ['fewer elements, more empty space', 'less repetition of the same motif', 'more variety between images',
  'simpler compositions', 'less busy detail', 'calmer, fewer colours'];

// ctx: {style, batch?, file?, name?, label?, onApplied?}
export async function openStyleEdit(ctx) {
  const all = await styles();
  const s = all[ctx.style];
  if (!s) {
    const off = (await archivedStyles())[ctx.style];
    return showError(new Error(off ? `${off.name} is switched off. Switch it on in Styles to change it.` : 'This image has no style on record.'));
  }
  const st = { step: 1, change: '', busy: 0, proposal: null, how: 'codex', words: 'prefer', skip: new Set() };
  const body = h('div');
  const foot = h('footer');
  let mainBtn;
  const dlg = h('dialog', { class: 'variations style-edit' }, h('article', {},
    h('header', { class: 'var-head' },
      ctx.file ? h('img', { src: thumbUrl(ctx.batch, ctx.file), alt: '' })
        : h('span', { class: 'swatches big', 'aria-hidden': 'true' }, (s.palette || []).slice(0, 5).map((c) => h('i', { style: { background: c } }))),
      h('hgroup', {}, h('h3', {}, `Change the style: ${s.name}`),
        h('p', {}, 'Every image made in this style after you apply it'))),
    body, foot));
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && mainBtn && !mainBtn.disabled) { e.preventDefault(); mainBtn.click(); } });
  document.body.append(dlg);
  dlg.showModal();
  draw('#se-change');

  function draw(focus) {
    body.replaceChildren(...(st.step === 1 ? stepOne() : stepTwo()).filter(Boolean));
    foot.replaceChildren(...(st.step === 1 ? footOne() : footTwo()).filter(Boolean));
    const el = focus && dlg.querySelector(focus);
    if (el) { el.focus(); if (el.setSelectionRange) el.setSelectionRange(el.value.length, el.value.length); }
  }

  // ------------------------------------------------------------ step 1: what should change

  function stepOne() {
    return [
      h('label', { class: 'nr-label', for: 'se-change' }, `What should change in ${s.name}?`),
      h('textarea', { id: 'se-change', rows: 3, maxlength: 400, placeholder: 'e.g. fewer elements in the frame, less repetition of the same tower',
        onInput: (e) => { st.change = e.target.value; drawFoot(); } }, st.change),
      h('div', { class: 'quick', 'aria-label': 'Quick picks: add to the change' }, QUICK.map((q) => h('button', { type: 'button', class: 'chip-btn',
        onClick: () => { st.change = st.change.trim() ? `${st.change.trim().replace(/[,.]$/, '')}, ${q}` : q; draw('#se-change'); } }, '+ ', q))),
      h('p', { class: 'muted small' }, 'Codex reads the whole style and proposes the smallest edit that makes this felt in every image. You see it before anything changes.'),
      isLocalOnly() && h('p', { class: 'notice small local-note' }, LOCAL_NOTE, ' ', h('a', { href: '#/models' }, 'Models page')),
      h('details', { class: 'small current' }, h('summary', {}, 'How the style reads now'), currentFacts()),
    ];
  }

  function currentFacts() {
    return h('dl', { class: 'facts-mini' }, Object.entries(FIELDS).filter(([k]) => s[k]?.length).map(([k, label]) => [
      h('dt', {}, label), h('dd', {}, Array.isArray(s[k]) ? h('ul', { class: 'plain' }, s[k].map((x) => h('li', {}, x))) : s[k])]));
  }

  function footOne() {
    mainBtn = h('button', { onClick: propose });
    const words = h('button', { class: 'secondary outline', onClick: () => { st.how = 'words'; st.step = 2; draw(); },
      title: 'No Codex: your words go into the style as they are' }, 'Add my words as they are');
    queueMicrotask(drawFoot);
    const fork = h('button', { class: 'ghost small', title: `Make a new style from ${s.name} with this change, and leave ${s.name} as it is`,
      onClick: () => { dlg.close(); openFork({ style: ctx.style, change: st.change.trim(), onCreated: ctx.onForked }); } }, 'As a new style…');
    return [fork, h('span', { class: 'spacer' }), words, mainBtn];
  }

  function drawFoot() {
    if (st.step !== 1 || !mainBtn) return;
    const ready = !!st.change.trim();
    mainBtn.disabled = !ready || !!st.busy || isLocalOnly();
    mainBtn.title = isLocalOnly() ? LOCAL_NOTE : '';
    mainBtn.setAttribute('aria-busy', st.busy ? 'true' : 'false');
    mainBtn.textContent = st.busy ? `Codex is reading the style… ${st.busy} s` : 'Propose the edit';
    foot.querySelector('.secondary.outline').disabled = !ready || !!st.busy;
  }

  async function propose() {
    const t0 = Date.now();
    st.busy = 1;
    drawFoot();
    const tick = setInterval(() => { st.busy = Math.max(1, Math.round((Date.now() - t0) / 1000)); drawFoot(); }, 1000);
    try {
      st.proposal = await api('style/propose', { method: 'POST', body: { style: ctx.style, change: st.change } });
      st.how = 'codex';
      st.skip = new Set();
      st.step = 2;
    } catch (err) {
      showError(err);
    } finally {
      clearInterval(tick);
      st.busy = 0;
      draw();
    }
  }

  // ------------------------------------------------------------ step 2: read the edit, choose, apply

  function changes() {
    if (st.how === 'words') {
      const k = st.words;
      return { [k]: [...(s[k] || []), st.change.trim()] };
    }
    return Object.fromEntries(Object.entries(st.proposal.changes).filter(([k]) => !st.skip.has(k)));
  }

  function stepTwo() {
    if (st.how === 'words') {
      return [
        h('p', { class: 'remix-summary' }, h('strong', {}, 'Your words, as they are: '), `“${st.change.trim()}”`),
        h('span', { class: 'nr-label' }, 'Add them as'),
        h('div', { class: 'rseg', role: 'group', 'aria-label': 'Add as' }, [['prefer', 'Lean towards'], ['avoid', 'Avoid']].map(([k, label]) => h('button', {
          type: 'button', class: 'rseg-btn', 'aria-pressed': String(st.words === k), onClick: () => { st.words = k; draw(); } }, label))),
        h('p', { class: 'muted small' }, st.words === 'prefer' ? 'Write it as what you want: “one main subject, quiet areas around it”.'
          : 'Write it as what to leave out: “rows of identical towers”.'),
        fieldDiff(st.words, s[st.words] || [], changes()[st.words], false),
      ];
    }
    const p = st.proposal;
    return [
      p.summary && h('p', { class: 'remix-summary' }, h('strong', {}, 'Codex: '), p.summary, p.dry_run ? '' : h('span', { class: 'muted' }, ` · ${p.seconds} s`)),
      h('p', { class: 'muted small' }, 'Added words marked, removed ones struck through. Untick a field to leave it as it is.'),
      ...Object.entries(p.changes).map(([k, v]) => fieldDiff(k, p.before[k], v, true)),
    ];
  }

  function fieldDiff(k, before, after, tickable) {
    const on = !st.skip.has(k);
    return h('section', { class: 'field-diff' + (on ? '' : ' is-off') },
      h('div', { class: 'field-head' },
        tickable ? h('label', { class: 'nr-check' }, h('input', { type: 'checkbox', checked: on,
          onChange: (e) => { e.target.checked ? st.skip.delete(k) : st.skip.add(k); draw(); } }), h('strong', {}, FIELDS[k] || k))
          : h('strong', {}, FIELDS[k] || k)),
      diffValue(before, after));
  }

  function footTwo() {
    mainBtn = h('button', { onClick: apply, disabled: !Object.keys(changes()).length }, 'Apply to the style');
    return [h('button', { class: 'secondary', onClick: () => { st.step = 1; draw('#se-change'); } }, '← Back'),
      h('span', { class: 'spacer' }), mainBtn];
  }

  async function apply() {
    mainBtn.disabled = true;
    mainBtn.setAttribute('aria-busy', 'true');
    try {
      const rec = await api('style/apply', { method: 'POST', body: { style: ctx.style, changes: changes(), change: st.change,
        summary: st.how === 'codex' ? st.proposal.summary : '', how: st.how, source: ctx.batch ? { batch: ctx.batch, name: ctx.name } : null } });
      await refreshStyles();
      dlg.close();
      ctx.onApplied?.(rec);
      toast(`${s.name} updated: the next images use it.`, { action: 'Undo', timeout: 12000, onAction: () => undoEdit(rec, ctx.onApplied) });
    } catch (err) {
      mainBtn.disabled = false;
      mainBtn.removeAttribute('aria-busy');
      showError(err);
    }
  }
}

export async function undoEdit(rec, after) {
  try {
    await api('style/undo', { method: 'POST', body: { id: rec.id } });
    await refreshStyles();
    after?.();
    toast(rec.how === 'new' || rec.how === 'fork' ? 'New style undone: it is off the Taste page' : 'Style edit undone');
  } catch (err) { showError(err); }
}

// Before / after of one field: text with words marked; a list item by item (same length: paired; else kept,
// added and removed items).
export function diffValue(before, after) {
  if (!Array.isArray(after) && !Array.isArray(before)) return h('p', { class: 'diff prompt' }, wordDiff(before || '', after || ''));
  const a = Array.isArray(before) ? before : before ? [before] : [];
  const b = Array.isArray(after) ? after : after ? [after] : [];
  let rows;
  if (a.length === b.length) rows = b.map((x, i) => (x === a[i] ? h('li', {}, x) : h('li', {}, wordDiff(a[i], x))));
  else {
    rows = [...b.map((x) => (a.includes(x) ? h('li', {}, x) : h('li', {}, h('ins', {}, x)))),
      ...a.filter((x) => !b.includes(x)).map((x) => h('li', {}, h('del', {}, x)))];
  }
  return h('ul', { class: 'diff prompt diff-list' }, rows);
}
