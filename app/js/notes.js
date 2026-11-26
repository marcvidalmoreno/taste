// Notes for Claude Code: feedback on an image or a style, left here instead of typed in chat.
// They wait in generated/codex/claude-notes.json; in chat, "process my app notes" makes Claude read them
// (scripts/notes.py), propose the style edits as one set for Marc's OK, and answer each note here.
// Codex never reads them: the taste stays with Claude (CLAUDE.md, "Who owns what").
import { api, allStyles } from './api.js';
import { h, thumbUrl, shortDate, plural, toast, showError } from './ui.js';

const EXAMPLES = ['too pink, more varied light', 'this composition is the one: more like it', 'faces look plastic',
  'never put text in the sky'];

// ctx: {batch, name, file, label, style} for an image, or {style} alone for a style
export async function openNote(ctx) {
  const all = await allStyles();
  const styleName = all[ctx.style]?.name || ctx.style;
  const st = { about: ctx.name ? 'image' : 'style', text: '' };
  const area = h('textarea', { rows: 4, maxlength: 1000, 'aria-label': 'Note',
    placeholder: `e.g. ${EXAMPLES[Math.floor(Math.random() * EXAMPLES.length)]}`, onInput: (e) => { st.text = e.target.value; btn.disabled = !st.text.trim(); } });
  const btn = h('button', { disabled: true, onClick: send }, 'Leave the note');
  const dlg = h('dialog', { class: 'variations note-dialog' }, h('article', {},
    h('header', { class: 'var-head' },
      ctx.file && h('img', { src: thumbUrl(ctx.batch, ctx.file), alt: '' }),
      h('hgroup', {}, h('h3', {}, 'Note for Claude'),
        h('p', {}, 'Claude reads it when you say “process my app notes” in chat'))),
    ctx.name && ctx.style && h('div', { class: 'rseg about', role: 'group', 'aria-label': 'About' },
      [['image', `This image (${ctx.label})`], ['style', `The style: ${styleName}`]].map(([k, label]) => h('button', {
        type: 'button', class: 'rseg-btn', 'aria-pressed': String(st.about === k),
        onClick: (e) => { st.about = k; e.currentTarget.parentNode.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget))); } }, label))),
    !ctx.name && h('p', { class: 'small' }, ctx.style ? `About the style: ${styleName}` : 'A general note, not about one style or image'),
    area,
    h('p', { class: 'muted small' }, 'Claude looks at what the note points at, proposes style edits as one set for your OK, then answers here (Overview page).'),
    h('footer', {}, h('span', { class: 'spacer' }), btn)));
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !btn.disabled) { e.preventDefault(); send(); } });
  document.body.append(dlg);
  dlg.showModal();
  area.focus();

  async function send() {
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    try {
      const image = st.about === 'image' && ctx.name;
      await api('notes', { method: 'POST', body: { text: st.text, style: ctx.style || '', batch: image ? ctx.batch : '', name: image ? ctx.name : '' } });
      dlg.close();
      ctx.onSaved?.();
      toast('Note saved. In chat: “process my app notes”.', { action: 'Copy that', onAction: () => navigator.clipboard.writeText('process my app notes'), timeout: 8000 });
    } catch (err) {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      showError(err);
    }
  }
}

// The notes card on the Overview page: open ones first (can be taken back), answered ones with Claude's answer.
export async function notesCard() {
  const box = h('article', { class: 'card notes-card' }, h('h2', {}, 'Notes for Claude'), h('p', { 'aria-busy': 'true' }, 'Loading…'));
  const all = await allStyles();
  const draw = async () => {
    let notes;
    try { ({ notes } = await api('notes')); } catch (err) { box.replaceChildren(h('h2', {}, 'Notes for Claude'), h('p', {}, err.message)); return; }
    const open = notes.filter((n) => n.status === 'open').reverse();
    const done = notes.filter((n) => n.status !== 'open').reverse().slice(0, 8);
    const where = (n) => [n.style && (all[n.style]?.name || n.style), n.name && `image ${n.name}`].filter(Boolean).join(' · ') || 'general';
    box.replaceChildren(...[
      h('h2', {}, 'Notes for Claude'),
      h('p', { class: 'big' }, open.length ? plural(open.length, 'open note') : 'No open notes'),
      open.length > 0 && h('p', { class: 'muted small' }, 'Say “process my app notes” in chat. ',
        h('button', { class: 'ghost small', onClick: () => navigator.clipboard.writeText('process my app notes').then(() => toast('Copied', { timeout: 1500 })) }, 'Copy')),
      h('ul', { class: 'plain note-list' },
        open.map((n) => h('li', {},
          n.batch && n.name && h('img', { src: thumbUrl(n.batch, n.name + '.png'), alt: '' }),
          h('div', {}, h('p', {}, n.text), h('small', { class: 'muted' }, `${where(n)} · ${shortDate(n.created.slice(0, 10))}`)),
          h('button', { class: 'ghost small', onClick: async () => {
            try { await api('notes/delete', { method: 'POST', body: { id: n.id } }); toast('Note taken back'); draw(); } catch (err) { showError(err); }
          } }, 'Take back'))),
        done.map((n) => h('li', { class: 'answered' },
          n.batch && n.name && h('img', { src: thumbUrl(n.batch, n.name + '.png'), alt: '' }),
          h('div', {}, h('p', {}, n.text), h('p', { class: 'answer' }, h('strong', {}, 'Claude: '), n.answer || 'done'),
            h('small', { class: 'muted' }, `${where(n)} · answered ${shortDate(n.answered.slice(0, 10))}`))))),
      h('button', { class: 'secondary outline', onClick: () => openNote({ onSaved: draw }) }, 'General note…')].filter(Boolean));
  };
  draw();
  return box;
}
