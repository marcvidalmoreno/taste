// Remix: a new image from one I made, changed the way I say. Two steps, nothing spent until the second:
//   1. Say what should change (words, or quick picks). Codex rewrites the prompt (~15 s, read-only text job),
//      or I edit the prompt myself.
//   2. Read the new prompt, with the changed words marked against the old one, edit it if needed, then make 1-4.
// The image itself can go along as a reference (closer result) or not (more freedom).
import { api, allStyles } from './api.js';
import { allowance, costBlock, makeLabel, route, routeBlocker } from './cost.js';
import { job, enqueueRun } from './job.js';
import { h, thumbUrl, plural, toast, showError } from './ui.js';

const QUICK = ['seen from far above', 'a closer view', 'wider, more empty space', 'at night', 'warmer light',
  'less busy', 'no people', 'more saturated colour', 'calmer mood'];
const LOCKS = { subject: 'Subject', palette: 'Palette', composition: 'Composition', light: 'Light', medium: 'Medium' };

// src: {batch, file, label, style, prompt}
export async function openRemix(src) {
  const all = await allStyles();
  const st = { step: 1, change: '', keep: [], ref: true, n: 1, prompt: src.prompt || '', summary: '', busy: 0, alw: null, edited: false, editing: false };
  const dlg = h('dialog', { class: 'variations remix' });
  const body = h('div');
  const foot = h('footer');
  let rewriteBtn, diffBox, makeBtn;   // parts redrawn on their own (declared before the first draw)
  dlg.append(h('article', {},
    h('header', { class: 'var-head' },
      h('img', { src: thumbUrl(src.batch, src.file), alt: '' }),
      h('hgroup', {}, h('h3', {}, `Remix ${src.label}`),
        h('p', {}, [all[src.style]?.name, 'a new image from this one, changed the way you say'].filter(Boolean).join(' · ')))),
    body, foot));
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); foot.querySelector('button:last-child:not(:disabled)')?.click(); }
  });
  document.body.append(dlg);
  dlg.showModal();
  draw();
  body.querySelector('textarea')?.focus();
  allowance().then((a) => { st.alw = a; }).catch((e) => { st.alw = { error: e.message }; }).finally(() => { if (st.step === 2) draw(); });

  function draw(focus) {
    body.replaceChildren(...(st.step === 1 ? stepOne() : stepTwo()).filter(Boolean));
    foot.replaceChildren(...(st.step === 1 ? footOne() : footTwo()));
    const el = focus && body.querySelector(focus);
    if (el) { el.focus(); if (el.setSelectionRange) el.setSelectionRange(el.value.length, el.value.length); }
  }

  // ------------------------------------------------------------ step 1: what should change

  function stepOne() {
    return [
      h('label', { class: 'nr-label', for: 'remix-change' }, 'What should change?'),
      h('textarea', { id: 'remix-change', rows: 3, maxlength: 400, placeholder: 'e.g. seen from far above, a red-orange sun, no people',
        onInput: (e) => { st.change = e.target.value; drawFootOne(); } }, st.change),
      h('div', { class: 'quick', 'aria-label': 'Quick picks: add to the change' },
        QUICK.map((q) => h('button', { type: 'button', class: 'chip-btn', onClick: () => {
          st.change = st.change.trim() ? `${st.change.trim().replace(/[,.]$/, '')}, ${q}` : q;
          draw('#remix-change');
        } }, '+ ', q))),
      h('fieldset', {},
        h('legend', { class: 'small' }, 'Must stay the same ', h('span', { class: 'muted' }, '(optional)')),
        h('div', { class: 'locks' }, Object.entries(LOCKS).map(([k, label]) => h('label', { class: 'nr-check' },
          h('input', { type: 'checkbox', checked: st.keep.includes(k),
            onChange: (e) => { st.keep = e.target.checked ? [...st.keep, k] : st.keep.filter((x) => x !== k); } }),
          h('span', {}, label))))),
      refToggle(),
      !src.prompt && h('p', { class: 'notice' }, 'This image has no prompt on record (it was made outside the logged runs). Write one yourself in the next step.'),
    ];
  }

  function refToggle() {
    return h('label', { class: 'nr-check' },
      h('input', { type: 'checkbox', checked: st.ref, onChange: (e) => { st.ref = e.target.checked; } }),
      h('span', {}, 'Send this image along as a reference ', h('span', { class: 'muted small' },
        '· on: the result stays close to it; off: only the prompt counts, more freedom')));
  }

  function footOne() {
    rewriteBtn = h('button', { onClick: rewrite });
    const own = h('button', { class: 'secondary outline', onClick: () => { st.step = 2; st.edited = true; st.editing = true; draw('#remix-prompt'); } },
      'Edit the prompt myself');
    const out = [h('button', { class: 'secondary', onClick: () => dlg.close() }, 'Cancel'), h('span', { class: 'spacer' }), own, rewriteBtn];
    queueMicrotask(drawFootOne);
    return out;
  }

  function drawFootOne() {
    if (!rewriteBtn) return;
    const ready = st.change.trim() && src.prompt;
    rewriteBtn.disabled = !ready || !!st.busy;
    rewriteBtn.setAttribute('aria-busy', st.busy ? 'true' : 'false');
    rewriteBtn.textContent = st.busy ? `Codex is rewriting… ${st.busy} s` : 'Write the new prompt';
    rewriteBtn.title = !src.prompt ? 'No prompt on record: edit it yourself' : !st.change.trim() ? 'Say what should change first' : 'About 15 s, a small text job on the Codex allowance';
  }

  async function rewrite() {
    const t0 = Date.now();
    st.busy = 1;
    drawFootOne();
    const tick = setInterval(() => { st.busy = Math.max(1, Math.round((Date.now() - t0) / 1000)); drawFootOne(); }, 1000);
    try {
      const r = await api('text/rewrite', { method: 'POST', body: { prompt: src.prompt, change: st.change, keep: st.keep } });
      st.prompt = r.prompt;
      st.summary = r.summary + (r.dry_run ? '' : ` · ${r.seconds} s`);
      st.step = 2;
      st.edited = false;
      st.editing = false;
    } catch (err) {
      showError(err);
    } finally {
      clearInterval(tick);
      st.busy = 0;
      draw(st.step === 2 ? '.prompt-toggle' : null);
    }
  }

  // ------------------------------------------------------------ step 2: read, edit, make

  function stepTwo() {
    diffBox = h('div', { class: 'diff prompt', 'aria-label': 'Changes against the old prompt' });
    drawDiff();
    return [
      st.summary && h('p', { class: 'remix-summary' }, h('strong', {}, 'Codex: '), st.summary),
      // One copy of the prompt at a time: the marked changes to read, or the text to edit.
      h('div', { class: 'prompt-head' },
        h('span', {}, 'New prompt ', !st.editing && src.prompt && h('span', { class: 'muted' }, '· added words marked, removed ones struck through')),
        src.prompt && h('button', { class: 'ghost small prompt-toggle', onClick: () => { st.editing = !st.editing; draw(st.editing ? '#remix-prompt' : '.prompt-toggle'); } },
          st.editing ? 'Show the changes' : 'Edit')),
      st.editing || !src.prompt
        ? h('textarea', { id: 'remix-prompt', rows: 8, maxlength: 4000, 'aria-label': 'New prompt',
          onInput: (e) => { st.prompt = e.target.value; st.edited = true; drawFootTwo(); } }, st.prompt)
        : diffBox,
      h('div', { class: 'nr-grid' },
        h('div', {}, h('span', { class: 'nr-label' }, 'How many'),
          h('div', { class: 'rseg', role: 'group', 'aria-label': 'How many' }, [1, 2, 4].map((n) => h('button', {
            type: 'button', class: 'rseg-btn', 'aria-pressed': String(st.n === n), onClick: () => { st.n = n; draw(); } }, n)))),
        h('div', {}, refToggle())),
      costBlock(st.alw, st.n, { compact: true, onRoute: () => draw() }),
    ];
  }

  function drawDiff() {
    if (!diffBox || !src.prompt) return;
    diffBox.replaceChildren(...wordDiff(src.prompt, st.prompt));
  }

  function footTwo() {
    makeBtn = h('button', { onClick: make });
    const out = [h('button', { class: 'secondary', onClick: () => { st.step = 1; draw('#remix-change'); } }, '← Back'),
      h('span', { class: 'spacer' }), makeBtn];
    queueMicrotask(drawFootTwo);
    return out;
  }

  function drawFootTwo() {
    if (!makeBtn) return;
    const busy = job.running || job.queue?.length;
    makeBtn.disabled = !st.prompt.trim() || !!routeBlocker(st.alw);
    makeBtn.title = routeBlocker(st.alw);
    makeBtn.textContent = st.alw?.dry_run ? `Dry run: ${plural(st.n, 'image')}` : busy ? `Add to queue · ${plural(st.n, 'image')}`
      : makeLabel(st.n);
  }

  async function make() {
    makeBtn.disabled = true;
    makeBtn.setAttribute('aria-busy', 'true');
    try {
      const res = await enqueueRun({ kind: 'remix', route: route(), batch: src.batch, file: src.file, prompt: st.prompt, change: st.change.trim() || (st.edited ? 'prompt edited' : ''),
        keep: st.keep, ref: st.ref, n: st.n });
      dlg.close();
      toast(res.position <= 1 ? `Remixing ${src.label}: about ${st.n} min` : `Remix of ${src.label} queued, number ${res.position}`);
    } catch (err) {
      makeBtn.removeAttribute('aria-busy');
      drawFootTwo();
      showError(err);
    }
  }
}

// Word-level diff (longest common subsequence): kept words plain, added in <ins>, removed in <del>.
// Seeing only what moved is change detection, far easier than comparing two paragraphs by eye.
export function wordDiff(a, b) {
  const x = a.split(/(\s+)/).filter((t) => t.trim()), y = b.split(/(\s+)/).filter((t) => t.trim());
  const n = x.length, m = y.length;
  if (n * m > 400_000) return [b];
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  const push = (tag, w) => {
    const last = out[out.length - 1];
    if (last && last.tag === tag) last.words.push(w); else out.push({ tag, words: [w] });
  };
  while (i < n && j < m) {
    if (x[i] === y[j]) { push('', x[i]); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) push('del', x[i++]); else push('ins', y[j++]);
  }
  while (i < n) push('del', x[i++]);
  while (j < m) push('ins', y[j++]);
  return out.flatMap((r, k) => [k ? ' ' : '', r.tag ? h(r.tag, {}, r.words.join(' ')) : r.words.join(' ')]);
}
