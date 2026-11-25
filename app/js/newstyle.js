// A new style from reference images (21 Nov 2026), opened from the Taste page.
// 1. Add 1-4 images that share a look (choose, drop or paste a copied image), a name and what draws you to them.
// 2. Codex looks at them and writes the style in words (~30-60 s); the palette is measured from the pixels.
//    Every field can be edited before anything is written.
// 3. Create style: taste/styles/<key>.json is written, the style is on the Taste page, a first run is one click away.
// The images stay on this laptop (generated/codex/references/, git-ignored): they are other people's work.
import { api, refreshStyles } from './api.js';
import { undoEdit, diffValue } from './styleedit.js';
import { h, toast, showError, plural } from './ui.js';
import { isLocalOnly, LOCAL_NOTE } from './cost.js';

const MAX = 4;
const NL = String.fromCharCode(10);
export const TEXTS = [['description', 'Description', 3], ['camera_or_medium', 'Medium', 1], ['texture_detail', 'Detail', 2]];
export const LISTS = [['light', 'Light'], ['composition', 'Composition'], ['mood', 'Mood'], ['prefer', 'Lean towards'],
  ['avoid', 'Avoid'], ['subjects', 'Subjects']];

// Shrink in the browser (longest side 1280 px, JPEG): a phone photo of 8 MB travels as ~300 KB.
async function shrink(file) {
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, 1280 / Math.max(bmp.width, bmp.height));
  const c = Object.assign(document.createElement('canvas'), { width: Math.round(bmp.width * k), height: Math.round(bmp.height * k) });
  c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close?.();
  return c.toDataURL('image/jpeg', 0.88);
}

// Shared with the fork dialog (forkstyle.js): the field editors of step 2, what a style still lacks, and the "created" block.
// parent: when given (a fork), each field that differs from it shows the changed words marked under the field.
// A field the style does not have is left out when a parent is given (the fork keeps the parent's shape).
export function fieldEditors(s, onChange, parent) {
  const rows = (k) => Math.min(6, Math.max(2, (s[k] || []).length + 1));
  const slot = (k) => {
    const box = h('div', { class: 'fork-diff' });
    const mark = () => {
      const same = JSON.stringify(s[k] ?? null) === JSON.stringify(parent[k] ?? null);
      box.replaceChildren(...(same ? [] : [h('p', { class: 'muted small' }, `Changed from ${parent.name}`), diffValue(parent[k], s[k])]));
    };
    mark();
    return [box, mark];
  };
  const field = (k, label, asList, r) => {
    const [box, mark] = parent ? slot(k) : [null, () => {}];
    const set = asList ? (v) => v.split(NL).map((x) => x.trim()).filter(Boolean) : (v) => v;
    const val = asList ? (s[k] || []).join(NL) : s[k] || '';
    return h('section', { class: 'field-diff' },
      h('label', { class: 'field-head', for: 'ns-' + k }, h('strong', {}, label), asList && h('span', { class: 'muted small' }, plural((s[k] || []).length, 'line'))),
      h('textarea', { id: 'ns-' + k, rows: asList ? rows(k) : r, onInput: (e) => { s[k] = set(e.target.value); mark(); onChange(); } }, val), box);
  };
  const keep = ([k]) => !parent || k in s;
  return [...TEXTS.filter(keep).map(([k, label, r]) => field(k, label, Array.isArray(s[k]), r)),
    ...LISTS.filter(keep).map(([k, label]) => field(k, label, true))];
}

export function missingFields(s) {
  const need = [['name', 'a name'], ['description', 'a description'], ['light', 'light'], ['composition', 'composition'],
    ['mood', 'mood'], ['camera_or_medium', 'a medium'], ['texture_detail', 'detail'], ['avoid', 'an avoid line']];
  return need.filter(([k]) => k in s && !(Array.isArray(s[k]) ? s[k].length : String(s[k] || '').trim())).map(([, w]) => w);
}

export function createdBlock(s, line) {
  return h('div', { class: 'ns-done' },
    h('span', { class: 'swatches big', 'aria-hidden': 'true' }, s.palette.slice(0, 5).map((c) => h('i', { style: { background: c } }))),
    h('div', {}, h('p', {}, h('strong', {}, s.name), ' is on the Taste page.'), h('p', { class: 'muted small' }, line)));
}

export function openNewStyle({ onCreated } = {}) {
  const st = { step: 1, images: [], name: '', notes: '', busy: 0, proposal: null, style: null, rec: null, key: '' };
  const body = h('div');
  const foot = h('footer');
  let mainBtn;
  const dlg = h('dialog', { class: 'variations style-edit new-style' }, h('article', {},
    h('header', {}, h('hgroup', {}, h('h3', {}, 'New style from images'),
      h('p', {}, 'Images that share a look you like: Codex writes the look in words, you check it, then make images in it'))),
    body, foot));
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && mainBtn && !mainBtn.disabled) { e.preventDefault(); mainBtn.click(); } });
  dlg.addEventListener('paste', (e) => {
    const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'));
    if (files.length && st.step === 1) { e.preventDefault(); add(files); }
  });
  document.body.append(dlg);
  dlg.showModal();
  draw();

  function draw(focus) {
    const steps = { 1: [stepOne, footOne], 2: [stepTwo, footTwo], 3: [stepThree, footThree] }[st.step];
    body.replaceChildren(...steps[0]().filter(Boolean));
    foot.replaceChildren(...steps[1]().filter(Boolean));
    const el = focus && dlg.querySelector(focus);
    el?.focus();
  }

  async function add(files) {
    const room = MAX - st.images.length;
    const pics = [...files].filter((f) => f.type.startsWith('image/'));
    if (!pics.length) return toast('Only images can be added.', { tone: 'error' });
    if (pics.length > room) toast(`${MAX} images at most: the first ${plural(room, 'one')} added.`);
    for (const f of pics.slice(0, room)) {
      try { st.images.push(await shrink(f)); } catch { toast(`${f.name || 'An image'} could not be read.`, { tone: 'error' }); }
    }
    draw();
  }

  // ------------------------------------------------------------ step 1: the references

  function stepOne() {
    const input = h('input', { type: 'file', accept: 'image/*', multiple: true, hidden: true,
      onChange: (e) => { add(e.target.files); e.target.value = ''; } });
    const zone = h('div', { class: 'drop-zone' + (st.images.length ? ' has-images' : ''),
      onDragover: (e) => { e.preventDefault(); zone.classList.add('is-over'); },
      onDragleave: () => zone.classList.remove('is-over'),
      onDrop: (e) => { e.preventDefault(); zone.classList.remove('is-over'); add(e.dataTransfer.files); } },
      st.images.map((src, i) => h('figure', { class: 'ref-tile' }, h('img', { src, alt: `Reference ${i + 1}` }),
        h('button', { type: 'button', class: 'ref-remove', 'aria-label': `Remove reference ${i + 1}`,
          onClick: () => { st.images.splice(i, 1); draw(); } }, '×'))),
      st.images.length < MAX && h('button', { type: 'button', class: 'drop-add', onClick: () => input.click() },
        h('strong', {}, st.images.length ? '+ Add another' : 'Choose images'),
        h('span', { class: 'muted small' }, st.images.length ? `up to ${MAX}` : `or drop them here, or paste a copied image · 1 to ${MAX}`)),
      input);
    return [
      zone,
      h('p', { class: 'muted small' }, 'Two to four images with one look in common work best: Codex keeps what they share. They stay on this laptop.'),
      h('label', { class: 'nr-label', for: 'ns-name' }, 'Name (optional: Codex suggests one)'),
      h('input', { id: 'ns-name', maxlength: 60, value: st.name, placeholder: 'e.g. Twilight tales', onInput: (e) => { st.name = e.target.value; } }),
      h('label', { class: 'nr-label', for: 'ns-notes' }, 'What draws you to them? (optional)'),
      h('textarea', { id: 'ns-notes', rows: 2, maxlength: 400, placeholder: 'e.g. the muted dusk colours, flat shapes, one small figure in a big space',
        onInput: (e) => { st.notes = e.target.value; } }, st.notes),
      isLocalOnly() && h('p', { class: 'notice small local-note' }, LOCAL_NOTE, ' ', h('a', { href: '#/models' }, 'Models page')),
    ];
  }

  function footOne() {
    mainBtn = h('button', { onClick: propose });
    queueMicrotask(drawFoot);
    return [h('button', { class: 'secondary', onClick: () => dlg.close() }, 'Cancel'), h('span', { class: 'spacer' }), mainBtn];
  }

  function drawFoot() {
    if (st.step !== 1 || !mainBtn) return;
    mainBtn.disabled = !st.images.length || !!st.busy || isLocalOnly();
    mainBtn.title = isLocalOnly() ? LOCAL_NOTE : '';
    mainBtn.setAttribute('aria-busy', st.busy ? 'true' : 'false');
    mainBtn.textContent = st.busy ? `Codex is looking at the images… ${st.busy} s` : 'Propose the style';
  }

  async function propose() {
    const t0 = Date.now();
    st.busy = 1;
    drawFoot();
    const tick = setInterval(() => { st.busy = Math.max(1, Math.round((Date.now() - t0) / 1000)); drawFoot(); }, 1000);
    try {
      st.proposal = await api('style/new/propose', { method: 'POST', body: { images: st.images, name: st.name, notes: st.notes } });
      st.style = structuredClone(st.proposal.style);
      st.step = 2;
    } catch (err) {
      showError(err);
    } finally {
      clearInterval(tick);
      st.busy = 0;
      draw(st.step === 2 ? '#ns-final-name' : null);
    }
  }

  // ------------------------------------------------------------ step 2: read and edit the proposal

  function stepTwo() {
    const p = st.proposal, s = st.style;
    const lines = (k) => (s[k] || []).join('\n');
    const rows = (k) => Math.min(6, Math.max(2, (s[k] || []).length + 1));
    return [
      h('div', { class: 'ref-strip', 'aria-label': 'Your references' }, st.images.map((src) => h('img', { src, alt: '' }))),
      p.summary && h('p', { class: 'remix-summary' }, h('strong', {}, 'Codex: '), p.summary,
        p.dry_run ? '' : h('span', { class: 'muted' }, ` · ${p.seconds} s`)),
      h('p', { class: 'muted small' }, 'Nothing is written yet. Change any word; in the lists, one line is one option (light, composition and mood get one option picked per image).'),
      h('label', { class: 'nr-label', for: 'ns-final-name' }, 'Name'),
      h('input', { id: 'ns-final-name', maxlength: 60, value: s.name, onInput: (e) => { s.name = e.target.value; drawCreate(); } }),
      h('section', { class: 'field-diff' },
        h('div', { class: 'field-head' }, h('strong', {}, 'Palette'),
          h('span', { class: 'muted small' }, p.measured ? 'measured from your images' : 'as Codex read it')),
        h('div', { class: 'swatches ns-palette', role: 'list' }, s.palette.map((c) => h('span', { role: 'listitem', title: c },
          h('i', { style: { background: c } }), h('code', {}, c))))),
      ...fieldEditors(s, drawCreate),
    ];
  }

  const missing = () => missingFields(st.style);

  let hint;
  function footTwo() {
    mainBtn = h('button', { onClick: create }, 'Create style');
    hint = h('span', { class: 'muted small' });
    queueMicrotask(drawCreate);
    return [h('button', { class: 'secondary', onClick: () => { st.step = 1; draw(); } }, '← Back'),
      h('span', { class: 'spacer' }), hint, mainBtn];
  }

  function drawCreate() {
    if (st.step !== 2 || !mainBtn) return;
    const m = missing();
    mainBtn.disabled = m.length > 0;
    hint.textContent = m.length ? `Needs ${m.join(', ')}` : '';
  }

  async function create() {
    mainBtn.disabled = true;
    mainBtn.setAttribute('aria-busy', 'true');
    try {
      st.rec = await api('style/new/create', { method: 'POST',
        body: { draft: st.proposal.draft, style: st.style, notes: st.notes, summary: st.proposal.summary } });
      st.key = st.rec.style;
      await refreshStyles();
      onCreated?.(st.key);
      st.step = 3;
      draw('#ns-first-run');
    } catch (err) {
      mainBtn.disabled = false;
      mainBtn.removeAttribute('aria-busy');
      showError(err);
    }
  }

  // ------------------------------------------------------------ step 3: created, make the first images

  function stepThree() {
    return [createdBlock(st.style, 'A first run shows whether the words caught the look. Your thumbs then steer it, like every other style.')];
  }

  function footThree() {
    mainBtn = h('a', { id: 'ns-first-run', role: 'button', href: '#/new?mode=batch&style=' + encodeURIComponent(st.key),
      onClick: () => dlg.close() }, 'First run');
    return [
      h('button', { class: 'ghost small', onClick: () => { dlg.close(); undoEdit(st.rec, () => onCreated?.(null)); } }, 'Undo'),
      h('span', { class: 'spacer' }),
      h('button', { class: 'secondary', onClick: () => dlg.close() }, 'Done'), mainBtn];
  }
}
