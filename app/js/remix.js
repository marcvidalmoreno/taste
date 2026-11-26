// Remix (25 Nov 2026): Remix and Variations in one dialog, designed in docs/mockups/2026-11-25-remix-merged.html.
// More images from one image, in its own style. Pick what changes (or nothing: one of each), say more in words,
// choose how close the result stays and how many, and which models make it. Template prompts, nothing spent before Make.
// "More options": read and edit the prompts first (Codex writes them, ~15 s each), or write them yourself.
// wordDiff is also used by the style editor.
import { api, allStyles } from './api.js';
import { allowance, meter, localSeconds, COST, MODELS, LOCAL, isLocalOnly, model, setModel, preselect, resetPreselect, LOCAL_NOTE } from './cost.js';
import { enqueueRun } from './job.js';
import { h, thumbUrl, plural, toast, showError } from './ui.js';

const AXES = { palette: ['Palette', 'new palette'], subject: ['Subject', 'new subject'], light: ['Light', 'other light'], composition: ['Composition', 'new framing'] };
const SPREAD = ['palette', 'subject', 'composition'];   // nothing picked: what Variations used to make
const GROUPS = {
  'Light & time': ['golden hour', 'blue hour', 'at dawn', 'midday sun', 'overcast, soft light', 'backlit', 'rim light',
    'one light source', 'candlelight', 'moonlight', 'harsh shadows', 'no shadows', 'cooler light', 'fog'],
  'Colour': ['more saturated colour', 'muted colours', 'fewer colours', 'black and white', 'one accent colour',
    'darker overall', 'lighter overall', 'pastel', 'warmer palette', 'cooler palette', 'higher contrast', 'lower contrast'],
  'Framing': ['seen from far above', "worm's-eye view", 'eye level', 'centred', 'off-centre, rule of thirds', 'symmetrical',
    'more negative space', 'tighter crop', 'subject smaller', 'subject larger', 'wide panorama', 'shallow depth of field', 'everything in focus'],
  'Content': ['simpler', 'more detail', 'fewer objects', 'one main subject', 'add a person', 'add an animal', 'no text or signs',
    'no buildings', 'more nature', 'add water', 'add sky', 'less background clutter', 'add a path or road'],
  'Mood': ['calmer', 'more dramatic', 'lonelier', 'more playful', 'mysterious', 'cosy', 'eerie', 'dreamlike', 'hopeful', 'melancholic', 'energetic', 'quiet, still'],
  'Weather & season': ['rain', 'snow', 'after rain, wet surfaces', 'mist', 'storm clouds', 'clear sky', 'autumn', 'spring', 'summer heat', 'winter'],
  'Experimental': ['surreal', 'impossible scale', 'seen through glass or water', 'double exposure', 'as a miniature', 'turned into a pattern',
    'one colour only', 'extreme close-up', 'upside down world', 'made of paper', 'glitch', 'as a dream half-remembered'],
  'Medium & texture': ['more painterly', 'more photographic', 'film grain', 'smoother', 'flat, graphic', 'watercolour', 'ink drawing',
    'paper texture', 'less glossy', 'softer edges', 'sharper detail', 'long exposure'],
};
// Shown first: the groups most relevant to an image, four picks each (the order then follows what Marc picks most).
const RELEVANT = {
  'Content': ['less busy', 'no people', 'simpler', 'fewer objects'],
  'Light & time': ['at night', 'warmer light', 'golden hour', 'fog'],
  'Framing': ['a closer view', 'wider, more empty space', 'seen from far above', 'tighter crop'],
  'Colour': ['more contrast', 'muted colours', 'one accent colour', 'darker overall'],
};
for (const [g, l] of Object.entries(RELEVANT)) GROUPS[g] = [...new Set([...l, ...GROUPS[g]])];
GROUPS.Mood = [...new Set(['calmer mood', ...GROUPS.Mood])];
const ALL_IDEAS = new Set(Object.values(GROUPS).flat());
const CLOSE = {
  close: ['Close', 'The original goes along as a reference: the result stays near it.'],
  balanced: ['Balanced', 'Reference sent, and the model is told it may move away.'],
  loose: ['Loose', 'Only the prompt goes: more freedom, may drift far.'],
  wild: ['Wild ✦', 'Experimental: the model is asked to reinterpret boldly (odd angles, surreal turns, another medium). Expect misses and a few surprises.'],
};
const CLOSE_WORD = { close: 'close to the original', balanced: 'near the original, free to move', loose: 'from the prompt only, more freedom', wild: 'a wild, experimental take: expect misses' };
const COUNTS = [1, 2, 3, 4, 6, 8, 12];
const NOTE = { codex: 'best, uses tokens', cloudflare: 'free, daily limit', klein: 'free, laptop', zimage: 'free, laptop', playground: 'free, laptop',
  dreamshaper: 'free, laptop', juggernaut: 'free, laptop', zavychroma: 'free, laptop', animagine: 'free, laptop' };
const KEEPABLE = ['subject', 'palette', 'composition', 'light'];
const USE_KEY = 'taste-remix-ideas';   // {idea: times picked}: the groups you use most come first

const usage = () => { try { return JSON.parse(localStorage.getItem(USE_KEY)) || {}; } catch { return {}; } };
const bump = (idea) => { const u = usage(); u[idea] = (u[idea] || 0) + 1; localStorage.setItem(USE_KEY, JSON.stringify(u)); };
const sw = (c) => h('span', { class: 'sw', 'aria-hidden': 'true' }, c.map((x) => h('i', { style: { background: x || '' } })));

// src: {batch, file, label, style, prompt}
export async function openRemix(src) {
  const all = await allStyles();
  const styleName = all[src.style]?.name || '';
  resetPreselect();
  const st = { axes: [], pal: 'random', combo: 'separate', extra: '', close: 'close', n: 3, models: [model()], touched: false, review: false, own: false,
    more: false, alw: null, pals: null, step: 1, kinds: [], prompts: {}, editing: {}, base: src.prompt || '', busy: '', sent: false };
  const dlg = h('dialog', { class: 'variations remix' });
  const body = h('div');
  const foot = h('footer');
  dlg.append(h('article', {},
    h('header', { class: 'var-head' },
      h('img', { src: thumbUrl(src.batch, src.file), alt: '' }),
      h('hgroup', {}, h('h3', {}, `Remix ${src.label}`),
        h('p', {}, [styleName, 'more images from this one, in its style'].filter(Boolean).join(' · ')))),
    body, foot));
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); foot.querySelector('button.make:not(:disabled)')?.click(); }
  });
  const parts = () => st.extra.split(',').map((x) => x.trim()).filter(Boolean);
  const keys = () => (isLocalOnly() ? LOCAL : Object.keys(MODELS));
  const chosenPal = () => (st.pal !== 'random' && st.pals?.[st.pal]) || null;
  const palLabel = () => (chosenPal() ? `palette: ${chosenPal().name}` : 'new palette, picked for you');
  const axisTitle = (a) => (a === 'palette' ? palLabel() : AXES[a][1]);
  const needsBase = () => !src.prompt && !st.base;
  const blockedLocal = () => !src.prompt && isLocalOnly() && !st.own;

  // From what's filled in, which images get made. The count is the user's; the changes are shared out over it.
  function plan() {
    const extra = st.extra.trim();
    const short = extra.length > 26 ? extra.slice(0, 24) + '…' : extra;
    const axes = AXES_ORDER().filter((a) => st.axes.includes(a));
    let kinds;
    if (!axes.length && !extra) kinds = SPREAD.map((a) => ({ title: axisTitle(a), keep: 'rest kept', pal: a === 'palette' }));
    else if (!axes.length) kinds = [{ title: `“${short}”`, keep: 'rest kept' }];
    else if (st.combo === 'together' && axes.length > 1) kinds = [{ title: axes.map(axisTitle).join(' + '), keep: extra ? `+ “${short}”` : 'rest kept', pal: axes.includes('palette') }];
    else kinds = axes.map((a) => ({ title: axisTitle(a), keep: extra ? `+ “${short}”` : 'rest kept', pal: a === 'palette' }));
    return { images: Array.from({ length: st.n }, (_, i) => kinds[i % kinds.length]), kinds };
  }
  const AXES_ORDER = () => Object.keys(AXES);

  // ------------------------------------------------------------ the form
  function draw(focus) {
    if (st.step === 2) return drawPrompts();
    if (src.style && !st.touched && !(st.alw == null)) { preselect(src.style); st.models = [model()]; }
    const t0 = body.querySelector('#rx-extra');
    const keep = document.activeElement === t0 && t0 ? [t0.selectionStart, t0.selectionEnd] : null;
    const p = plan();
    const k = p.kinds.length;
    const noRef = st.models.includes('zimage');
    const total = st.n * Math.max(1, st.models.length);
    const extra = st.extra.trim();
    body.replaceChildren(...[
      // 1. what changes
      h('div', { class: 'rx-row' },
        h('span', { class: 'rx-label', id: 'rx-lbl-change' }, 'Change ', h('span', { class: 'muted small' }, '· pick none and you get one of each')),
        h('div', { class: 'rx-chips', role: 'group', 'aria-labelledby': 'rx-lbl-change' }, Object.entries(AXES).map(([a, [label]]) => h('button', {
          type: 'button', class: 'rx-chip', 'aria-pressed': String(st.axes.includes(a)), 'data-focus': `axis-${a}`,
          onClick: () => { st.axes = st.axes.includes(a) ? st.axes.filter((x) => x !== a) : [...st.axes, a]; if (a === 'palette') loadPalettes(); draw(`[data-focus="axis-${a}"]`); } }, label))),
        st.axes.includes('palette') && palettePanel(),
        st.axes.length > 1 && combinePanel()),
      // 2. words + ideas
      h('div', { class: 'rx-row' },
        h('label', { class: 'rx-label', for: 'rx-extra' }, 'Anything else? ', h('span', { class: 'muted small' }, '· goes into every image')),
        h('textarea', { id: 'rx-extra', rows: 2, maxlength: 400, placeholder: 'e.g. a red-orange sun, no planet in the sky',
          onInput: (e) => { st.extra = e.target.value; draw(); } }, st.extra),
        ideas()),
      // 3. closeness + count
      h('div', { class: 'rx-row rx-two' },
        h('div', {}, h('span', { class: 'rx-label', id: 'rx-lbl-close' }, 'How close to the original'),
          h('div', { class: 'rx-seg', role: 'group', 'aria-labelledby': 'rx-lbl-close' }, Object.entries(CLOSE).map(([c, [label]]) => h('button', {
            type: 'button', 'aria-pressed': String(st.close === c), 'data-focus': `close-${c}`, onClick: () => { st.close = c; draw(`[data-focus="close-${c}"]`); } }, label))),
          h('p', { class: 'muted small rx-hint' }, CLOSE[st.close][1] + (noRef && !['loose', 'wild'].includes(st.close) ? " Z-Image can't take an image, so its set works from the prompt only." : ''))),
        h('div', {}, h('span', { class: 'rx-label', id: 'rx-lbl-n' }, 'How many images'),
          h('div', { class: 'rx-seg', role: 'group', 'aria-labelledby': 'rx-lbl-n' }, COUNTS.map((n) => h('button', {
            type: 'button', 'aria-pressed': String(st.n === n), 'data-focus': `n-${n}`, onClick: () => { st.n = n; draw(`[data-focus="n-${n}"]`); } }, String(n)))),
          h('p', { class: 'muted small rx-hint' }, k === 1 ? (st.n === 1 ? 'One image.' : `${st.n} takes on the same change, each a little different.`)
            : st.n < k ? `Fewer images than changes: only the first ${st.n} get made.`
              : st.n % k === 0 ? `${st.n / k} of each change.` : `Shared out in turn: ${st.n} images over ${k} changes.`))),
      // 4. models
      h('div', { class: 'rx-row' },
        h('span', { class: 'rx-label', id: 'rx-lbl-model' }, 'Made with ', h('span', { class: 'muted small' }, '· pick one or more')),
        h('div', { class: 'rx-chips', role: 'group', 'aria-labelledby': 'rx-lbl-model' }, keys().map((m) => h('button', {
          type: 'button', class: 'rx-chip', 'aria-pressed': String(st.models.includes(m)), 'data-focus': `model-${m}`,
          onClick: () => { st.models = keys().filter((x) => (x === m ? !st.models.includes(m) : st.models.includes(x))); st.touched = true; if (st.models.length === 1) setModel(st.models[0]); draw(`[data-focus="model-${m}"]`); } },
        MODELS[m].badge, h('small', {}, NOTE[m])))),
        h('p', { class: 'muted small rx-hint' }, !st.models.length ? 'Pick at least one model.'
          : st.models.length === 1 ? "The style's usual model is picked first. Pick more to compare: each makes the same set, side by side."
            : `Each model makes the same ${plural(st.n, 'image')}, in its own batch, so you can compare them.`,
        isLocalOnly() ? ' Local only is on: only the models on this laptop.' : '')),
      // 5. outcome
      h('div', { class: 'rx-row' },
        h('span', { class: 'rx-label' }, "What you'll get"),
        h('div', { class: 'rx-plan', 'aria-live': 'polite' }, (st.models.length ? st.models : [model()]).flatMap((mk) => [
          st.models.length > 1 && h('div', { class: 'rx-mdl' }, MODELS[mk].badge),
          h('div', { class: 'rx-tiles' }, p.images.map((im) => h('div', { class: 'rx-tile' },
            im.pal && chosenPal() && sw(chosenPal().c), h('b', {}, im.title), h('span', { class: 'muted' }, im.keep)))),
        ])),
        h('p', { class: 'rx-will' }, h('strong', {}, `Will make ${plural(total, 'image')}`),
          st.models.length > 1 ? ` (${plural(st.n, 'image')} × ${st.models.length} models)` : '',
          `: ${willWhat(p, extra)}. ${styleName ? `In the ${styleName} style; ` : ''}everything not picked stays; ${CLOSE_WORD[st.close]}.`,
          st.review ? h('span', { class: 'muted' }, ' You read the prompts first.') : '',
          !src.prompt && !st.own ? h('span', { class: 'muted' }, ' The original has no prompt on record, so Codex reads the image first (about 30 s).') : '')),
      costBox(),
      blockedLocal() && h('p', { class: 'notice' }, `This image has no prompt on record, and looking at it uses ChatGPT tokens – turn off Local only, or write the prompt yourself (More options).`),
      h('details', { class: 'rx-more', open: st.moreOpen || st.review || st.own, onToggle: (e) => { st.moreOpen = e.target.open; } },
        h('summary', {}, 'More options'),
        h('div', { class: 'rx-more-body' },
          h('label', { class: 'nr-check' }, h('input', { type: 'checkbox', id: 'rx-review', checked: st.review,
            onChange: (e) => { st.review = e.target.checked; if (st.review) st.own = false; draw('#rx-review'); } }),
          h('span', {}, 'Review the prompts before making',
            h('span', { class: 'muted small' }, ` · ${isLocalOnly() ? 'the local model' : 'Codex'} writes them first (about 15 s each, nothing spent), you read and edit`))),
          h('label', { class: 'nr-check' }, h('input', { type: 'checkbox', id: 'rx-own', checked: st.own,
            onChange: (e) => { st.own = e.target.checked; if (st.own) st.review = false; draw('#rx-own'); } }),
          h('span', {}, 'Write the prompt myself', h('span', { class: 'muted small' }, ' · start from the original prompt, change what you like'))))),
    ].filter(Boolean));
    drawFootOne(total);
    if (focus) body.querySelector(focus)?.focus();
    else if (keep) { const t = body.querySelector('#rx-extra'); t.focus(); t.setSelectionRange(...keep); }
  }

  function willWhat(p, extra) {
    if (!st.axes.length && !extra) return `one new palette, one new subject, one new framing${st.n > 3 ? ', and round again' : ''}`;
    if (!st.axes.length) return `${st.n > 1 ? `${st.n} takes on ` : ''}“${extra}”`;
    return (p.kinds.length === 1 && st.n > 1 ? `${st.n} takes on ` : '') + [...new Set(p.images.map((i) => i.title))].join(' · ')
      + (extra ? `, ${st.n > 1 ? 'each ' : ''}with “${extra}”` : '');
  }

  function drawFootOne(total) {
    const blocked = blocker();
    foot.replaceChildren(h('button', { class: 'secondary', type: 'button', onClick: () => dlg.close() }, 'Cancel'), h('span', { class: 'spacer' }),
      h('span', { class: 'muted small keys' }, h('kbd', {}, 'Ctrl'), ' + ', h('kbd', {}, 'Enter')),
      h('button', { class: 'make', type: 'button', disabled: !!blocked || !!st.busy, title: blocked, 'aria-busy': st.busy ? 'true' : 'false', onClick: make },
        st.busy || (st.review ? 'Write the prompts' : st.own ? 'Next: write the prompt' : `Make ${plural(total ?? st.n * st.models.length, 'image')}`)));
  }

  function blocker() {
    const a = st.alw;
    if (!st.models.length) return 'Pick at least one model.';
    if (blockedLocal()) return LOCAL_NOTE;
    if (st.models.includes('cloudflare') && a && !a.error && !a.cloudflare?.connected) return 'Connect Cloudflare first (New run, Made with: FLUX).';
    return '';
  }

  // ------------------------------------------------------------ palette and combine
  async function loadPalettes() {
    if (st.pals) return;
    st.pals = [];
    st.palBusy = true;
    try {
      const r = await api(`remix/palettes/${encodeURIComponent(src.batch)}/${encodeURIComponent(src.file)}/${encodeURIComponent(src.style || '')}`);
      st.pals = r.palettes || [];
    } catch { st.pals = []; }
    st.palBusy = false;
    if (st.step === 1) draw();
  }

  function palettePanel() {
    const pals = st.pals || [];
    return h('div', { class: 'rx-sub' },
      h('span', { class: 'rx-label' }, 'Which palette'),
      h('div', { class: 'rx-pals', role: 'group', 'aria-label': 'Palette' },
        h('button', { type: 'button', class: 'rx-pal random', 'aria-pressed': String(st.pal === 'random'), 'data-focus': 'pal-random', onClick: () => { st.pal = 'random'; draw('[data-focus="pal-random"]'); } },
          sw(['', '', '', '', '']), 'Surprise me'),
        st.palBusy && h('span', { class: 'muted small' }, 'Reading the style and your 👍 images…'),
        pals.map((p, i) => h('button', { type: 'button', class: 'rx-pal', 'aria-pressed': String(st.pal === i), 'data-focus': `pal-${i}`, title: p.c.join(' '),
          onClick: () => { st.pal = i; draw(`[data-focus="pal-${i}"]`); } }, sw(p.c), p.name))),
      h('p', { class: 'rx-hint muted small' }, !chosenPal()
        ? 'A different palette per image, chosen to suit the style. Subject, framing and light stay.'
        : `Every palette image uses ${chosenPal().name}. Proposed from the style and from images you gave 👍.`));
  }

  function combinePanel() {
    const names = AXES_ORDER().filter((a) => st.axes.includes(a)).map((a) => AXES[a][0].toLowerCase());
    return h('div', { class: 'rx-sub' },
      h('span', { class: 'rx-label' }, `${plural(st.axes.length, 'change')} picked`),
      h('div', { class: 'rx-seg', role: 'group', 'aria-label': 'How the changes combine' },
        h('button', { type: 'button', 'aria-pressed': String(st.combo === 'separate'), 'data-focus': 'combo-separate', onClick: () => { st.combo = 'separate'; draw('[data-focus="combo-separate"]'); } }, 'One change per image'),
        h('button', { type: 'button', 'aria-pressed': String(st.combo === 'together'), 'data-focus': 'combo-together', onClick: () => { st.combo = 'together'; draw('[data-focus="combo-together"]'); } }, 'All changes in every image')),
      h('p', { class: 'rx-hint muted small' }, st.combo === 'separate'
        ? `Each image changes one thing, so you see what each change does. ${names.join(', ')}, then round again.`
        : `Every image changes ${names.join(' and ')} at once: further from the original, harder to tell which change did what.`));
  }

  // ------------------------------------------------------------ ideas: four cards, "More ideas" opens them all
  function ideaChip(s) {
    const on = parts().includes(s);
    return h('button', { type: 'button', class: 'rx-s', 'aria-pressed': String(on), 'data-focus': `idea-${s}`, onClick: () => {
      if (!on) bump(s);
      st.extra = on ? parts().filter((x) => x !== s).join(', ') : (st.extra.trim() ? `${st.extra.trim().replace(/[,.]$/, '')}, ${s}` : s);
      draw(`[data-focus="idea-${s}"]`);
    } }, on ? '✓ ' : '+ ', s);
  }

  function ideas() {
    const u = usage();
    const score = (g) => GROUPS[g].reduce((n, x) => n + (u[x] || 0), 0);
    const order = Object.keys(GROUPS).sort((a, b) => score(b) - score(a));   // stable: the default order breaks ties
    const used = (g) => GROUPS[g].filter((x) => parts().includes(x)).length;
    const top = (g) => [...new Set([...(RELEVANT[g] || GROUPS[g]).slice(0, 4)].sort((a, b) => (u[b] || 0) - (u[a] || 0)).concat(GROUPS[g].filter((x) => parts().includes(x))))];
    const card = (g, list) => h('div', { class: 'rx-card' },
      h('span', { class: 'rx-gh' }, g, used(g) ? h('span', { class: 'n' }, ` ✓${used(g)}`) : ''),
      h('div', { class: 'rx-srow' }, list.map(ideaChip)));
    const shown = order.slice(0, 4);
    const shownCount = shown.reduce((n, g) => n + top(g).length, 0);
    return h('div', { class: 'rx-ideas', 'aria-label': 'Ideas: click to add to the text, click again to take out' },
      h('div', { class: 'rx-ideas-head' }, h('span', { class: 'muted small' }, st.more ? 'All ideas, by group' : 'Picked for this image'),
        h('button', { type: 'button', class: 'rx-link', 'aria-expanded': String(st.more), 'data-focus': 'more-ideas', onClick: () => { st.more = !st.more; draw('[data-focus="more-ideas"]'); } },
          st.more ? 'Fewer ideas ▴' : `More ideas (${ALL_IDEAS.size - shownCount} more, ${order.length} groups) ▾`)),
      st.more ? h('div', { class: 'rx-cards wide' }, order.map((g) => card(g, GROUPS[g])))
        : h('div', { class: 'rx-cards compact' }, shown.map((g) => card(g, top(g)))));
  }

  // ------------------------------------------------------------ cost: one calm line per model; meters only when they matter
  function costBox() {
    const a = st.alw;
    if (!st.models.length) return h('section', { class: 'cost rx-cost' }, h('p', { class: 'muted' }, 'No model picked, nothing to make.'));
    if (!a) return h('section', { class: 'cost rx-cost', 'aria-busy': 'true' }, 'Reading the allowance…');
    if (a.error) return h('section', { class: 'cost rx-cost' }, `Allowance unknown: ${a.error}`);
    const n = st.n;
    const many = st.models.length > 1;
    const lines = st.models.map((m) => {
      const name = many && h('strong', {}, `${MODELS[m].badge}: `);
      if (m === 'codex') {
        return h('p', {}, name, `≈ ${(n * COST.fiveLow).toFixed(1)}–${(n * COST.fiveHigh).toFixed(1)} % of the five-hour window`,
          h('span', { class: 'muted' }, ` · about ${n * COST.minutes} min`));
      }
      if (m === 'cloudflare') {
        return h('p', {}, name, a.cloudflare?.connected ? 'Free' : 'Free, but connect Cloudflare first (New run)',
          a.cloudflare?.connected && h('span', { class: 'muted' }, ` · ${n} of about ${a.cloudflare.images_left} left today`));
      }
      return h('p', {}, name, 'Free, no tokens', h('span', { class: 'muted' }, ` · about ${Math.max(1, Math.round((n * localSeconds(a, m)) / 60) + 1)} min on this laptop`));
    });
    const five = a.now?.five_hour;
    const chat = st.models.includes('codex') ? n : 0;
    const add = chat * COST.fiveHigh;
    const meters = chat && five != null && five >= 70 && h('div', { class: 'meters' },
      meter('Five-hour window', five, add), meter('This week', a.now.weekly, chat * (a.week_per_image || 0.1)),
      h('p', { class: 'small ' + (five + add > 90 ? 'over' : 'muted') }, five + add > 90
        ? 'This would bring the window close to full. FLUX or a laptop model is free.' : 'Shown because the window is over 70 % used.'));
    return h('section', { class: 'cost rx-cost', 'aria-label': 'Cost' },
      a.dry_run && h('p', { class: 'notice' }, 'Dry run: the app was started with --dry-run. Nothing will be generated or spent.'),
      lines, meters);
  }

  // ------------------------------------------------------------ making it
  const request = (extra = {}) => ({ batch: src.batch, file: src.file, style: src.style || '', changes: st.axes, palette: st.axes.includes('palette') && chosenPal() ? chosenPal().c : [],
    combine: st.combo, extra: st.extra.trim(), close: st.close, n: st.n, prompt: st.base || '', models: st.models, model: st.models[0], ...extra });

  const timed = async (label, work) => {   // a slow step (Codex reads the image, writes a prompt): the button counts the seconds
    const t0 = Date.now();
    const tick = setInterval(() => { st.busy = `${label}… ${Math.max(1, Math.round((Date.now() - t0) / 1000))} s`; draw(); }, 1000);
    st.busy = `${label}… 1 s`;
    draw();
    try { return await work(); } finally { clearInterval(tick); st.busy = ''; }
  };

  // No prompt on record: Codex reads the image and writes one (about 30 s), then every prompt can start from it.
  async function ensureBase() {
    if (src.prompt || st.base) return;
    const who = isLocalOnly() ? 'The local model' : 'Codex';
    await timed(`${who} is looking at the image`, async () => {
      const r = await api('text/rewrite', { method: 'POST', body: { batch: src.batch, file: src.file, style: src.style, keep: [],
        change: 'describe this image exactly as it is, as a prompt, changing nothing' } });
      st.base = r.prompt;
    });
  }

  async function make() {
    try {
      await ensureBase();
      if (st.review || st.own) { await toPrompts(); return; }
      await send({});
    } catch (err) {
      st.busy = '';
      draw();
      showError(err);
    }
  }

  async function send(prompts) {
    const res = await enqueueRun({ kind: 'remix', ...request({ prompts }) });
    dlg.close();
    const k = st.models.length;
    toast(k > 1 ? `${plural(k, 'set')} of remixes of ${src.label} queued, one per model`
      : res.position <= 1 ? `Remixing ${src.label}: ${plural(st.n, 'image')}` : `Remix of ${src.label} queued, number ${res.position}`);
  }

  // ------------------------------------------------------------ More options: read and edit the prompts first
  async function toPrompts() {
    const p = await api('remix/plan', { method: 'POST', body: request() });
    st.kinds = p.kinds;
    st.base = st.base || p.prompt || '';
    st.prompts = {}; st.editing = {};
    if (st.own) {
      for (const k of st.kinds) { st.prompts[k.key] = st.base; st.editing[k.key] = true; }
    } else {
      const who = isLocalOnly() ? 'The local model' : 'Codex';
      await timed(`${who} is writing the prompts`, async () => {
        for (const k of st.kinds) {
          const keep = k.axes.length ? KEEPABLE.filter((a) => !k.axes.includes(a)) : [];
          const r = await api('text/rewrite', { method: 'POST', body: { prompt: st.base, batch: src.batch, file: src.file, style: src.style, change: k.change, keep } });
          st.prompts[k.key] = r.prompt;
        }
      });
    }
    st.step = 2;
    draw();
  }

  function drawPrompts() {
    const noted = st.own ? 'Start from the original prompt and change what you like.' : 'Added words are marked, removed ones struck through. Edit to change.';
    body.replaceChildren(
      h('p', { class: 'remix-summary' }, h('strong', {}, st.own ? 'Your prompt: ' : `${isLocalOnly() ? 'Local model' : 'Codex'}: `),
        st.kinds.length > 1 ? `one prompt per kind of image (${st.kinds.length}); every image of a kind shares it.` : 'one prompt for the whole set.', ' ', noted),
      ...st.kinds.map((k) => {
        const area = st.editing[k.key] || !st.base;
        return h('div', { class: 'rx-row' },
          h('div', { class: 'prompt-head' },
            h('span', {}, `${plural(k.images, 'image')}: `, h('strong', {}, k.axes.length ? k.axes.map((a) => AXES[a][0]).join(' + ') : 'your words'),
              h('span', { class: 'muted' }, ` · ${k.change.slice(0, 90)}${k.change.length > 90 ? '…' : ''}`)),
            st.base && h('button', { class: 'ghost small', type: 'button', onClick: () => { st.editing[k.key] = !st.editing[k.key]; drawPrompts(); } }, area ? 'Show the changes' : 'Edit')),
          area ? h('textarea', { rows: 6, maxlength: 4000, 'aria-label': `Prompt: ${k.key}`, onInput: (e) => { st.prompts[k.key] = e.target.value; } }, st.prompts[k.key])
            : h('div', { class: 'diff prompt', 'aria-label': 'Changes against the original prompt' }, wordDiff(st.base, st.prompts[k.key])));
      }),
      costBox());
    const total = st.n * st.models.length;
    foot.replaceChildren(h('button', { class: 'secondary', type: 'button', onClick: () => { st.step = 1; draw(); } }, '← Back'), h('span', { class: 'spacer' }),
      h('button', { class: 'make', type: 'button', disabled: !!blocker(), onClick: async () => {
        try { await send(Object.fromEntries(Object.entries(st.prompts).filter(([, v]) => v.trim()))); } catch (err) { showError(err); }
      } }, `Make ${plural(total, 'image')}`));
  }

  document.body.append(dlg);
  dlg.showModal();
  draw();
  allowance().then((a) => { st.alw = a; }).catch((e) => { st.alw = { error: e.message }; }).finally(() => draw());
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
