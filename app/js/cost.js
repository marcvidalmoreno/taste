// What a run costs, shown the same way everywhere something spends Codex allowance (new run, remix,
// variations): the meters from Codex's own log, this run in images / minutes / share of the window, and the
// Codex week (since its weekly reset) with this run's share of it. Numbers are measured (README "Allowance"), never typed by hand.
import { api } from './api.js';
import { h, plural } from './ui.js';

// What one image costs (README "Allowance", measured 13 Nov 2026): ~95-116k tokens, about a minute,
// 0.25–0.75 % of the five-hour window.
export const COST = { minutes: 1, fiveLow: 0.25, fiveHigh: 0.75 };

let cached = null;
let at = 0;
// The allowance read costs a subprocess: share one answer for a minute.
export async function allowance(fresh = false) {
  if (!fresh && cached && Date.now() - at < 60_000) return cached;
  await modelInfo(fresh).catch(() => null);   // defaults per style and Local only, for the "Made with" choice
  cached = await api('allowance');
  at = Date.now();
  return cached;
}

// A used-percentage meter: one thin bar, the number written next to it (never colour alone).
// add: what this run would add (Remix): a hatched stretch after the used part, and "used → after %".
export function meter(label, used, add = 0) {
  const pct = Math.max(0, Math.min(100, Number(used) || 0));
  const more = Math.max(0, Math.min(100 - pct, Number(add) || 0));
  return h('div', { class: 'meter' },
    h('span', {}, label),
    h('span', { class: 'bar', role: 'meter', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': pct,
                'aria-label': `${label}: ${pct} % used` }, h('i', { style: { width: pct + '%' } }),
      more > 0 && h('i', { class: 'add', style: { left: pct + '%', width: more + '%' } })),
    h('span', { class: 'num' }, more > 0 ? `${pct} → ${Math.round(pct + more)} %` : `${pct} % used`));
}

// a: GET /api/allowance (or {error}), n: images this run would make, extra: e.g. 'Codex writes subjects first: ~15 s each'
// onRoute: redraw callback; given, the block starts with the "Made with" choice (ChatGPT or FLUX on Cloudflare).
// style: the style this run is for (its default model is picked once); seed: the run starts from an image.
// picker: false leaves out the "Made with" choice. multi: the chips toggle, several models make one run each (New batch).
export function costBlock(a, n, { extra = '', compact = false, onRoute = null, style = '', seed = false, picker = true, multi = false } = {}) {
  if (onRoute) preselect(style, multi);
  const pick = onRoute && picker && routePicker(onRoute, style, multi);
  if (!a) return h('section', { class: 'cost', 'aria-busy': 'true' }, pick, 'Reading the allowance…');
  if (a.error) return h('section', { class: 'cost' }, pick, `Allowance unknown: ${a.error}`);
  const dry = a.dry_run && h('p', { class: 'notice' }, 'Dry run: the app was started with --dry-run. Nothing will be generated or spent.');
  const list = multi ? models() : [model()];
  if (!onRoute || list.length === 1) return h('section', { class: 'cost' }, pick, dry, costFor(a, n, onRoute ? list[0] : 'codex', { extra, compact, onRoute, seed }));
  // Several models: each one's own block under its name (ChatGPT's allowance, FLUX's day, the laptop's minutes).
  return h('section', { class: 'cost' }, pick, dry, list.map((m) => h('div', { class: 'cost-model' },
    h('h3', { class: 'cost-model-name' }, MODELS[m].badge), costFor(a, n, m, { extra: m === list[0] ? extra : '', compact: true, onRoute, seed }))));
}

function costFor(a, n, m, { extra, compact, onRoute, seed }) {
  if (onRoute && m === 'cloudflare') return cloudflareBlock(a, n, onRoute, extra);
  if (onRoute && MODELS[m].local) return localBlock(a, n, m, extra, seed);
  // The week is Codex's own window (since its weekly reset), counted in % of the week, not a fixed image budget.
  const per = a.week_per_image || 0.1;
  const used = a.now ? a.now.weekly : null;
  const add = ((a.queued_images || 0) + n) * per;
  const after = used == null ? null : used + add;
  const over = after != null && after > 100;
  return [
    h('p', { class: 'cost-main' },
      h('strong', {}, plural(n, 'image')),
      h('span', { class: 'muted' }, ` · about ${n * COST.minutes} min · ≈ ${(n * COST.fiveLow).toFixed(1)}–${(n * COST.fiveHigh).toFixed(1)} % of the five-hour window`)),
    extra && h('p', { class: 'muted small' }, extra),
    !compact && (a.now ? h('div', { class: 'meters' },
      meter('Five-hour window', a.now.five_hour), meter('This week', a.now.weekly),
      h('p', { class: 'muted small' }, `Used, from Codex's own log as of ${a.now.as_of.slice(11)} on ${a.now.as_of.slice(0, 10)}.`))
      : h('p', { class: 'small' }, `Allowance unknown: ${a.unknown_reason || 'no reading'}`)),
    h('p', { class: 'small' + (over ? ' over' : ' muted') }, weekLine(a, add, after, over))];
}

const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const when = (iso) => { const d = new Date(iso); return `${WD[d.getDay()]} ${d.getDate()} ${MO[d.getMonth()]}, ${iso.slice(11, 16)}`; };
const pct = (x) => (x === 0 ? '0' : x < 1 ? x.toFixed(1) : Math.round(x)) + ' %';

// "This Codex week: 37 images since Mon 23 Nov, 16:52. This run adds about 0.5 % of the week (resets Mon 30 Nov, 16:52)."
function weekLine(a, add, after, over) {
  const since = a.week_start ? ` since ${when(a.week_start)}` : ' in the last 7 days';
  const queued = a.queued_images ? ` (+${a.queued_images} queued)` : '';
  const resets = a.now?.weekly_resets ? ` (resets ${when(a.now.weekly_resets)})` : '';
  return `This Codex week: ${plural(a.week_images, 'image')}${queued}${since}. `
    + (over ? `This run may reach the weekly limit: about ${Math.round(after)} % of the week${resets}.`
            : `This run${a.queued_images ? ' and the queue add' : ' adds'} about ${pct(add)} of the week${resets}.`);
}

// ---------------------------------------------------------------- which model makes the images (23 Nov 2026)
// "Made with": nine models since 26 Nov 2026. ChatGPT through Codex, FLUX on Cloudflare's free daily allowance
// (docs/cloudflare-route.md) and seven open models on this laptop through ComfyUI (docs/local-route.md). The choice
// is remembered in this browser; a style's default model (Models page) is picked for you when the style comes up.
// Local only (Models page) leaves only the local models.
export const MODELS = {
  codex: { badge: 'Codex', name: 'Codex image tool (ChatGPT plan)', note: 'Best quality and closest to the style. Uses the Codex allowance.' },
  cloudflare: { badge: 'FLUX', name: 'FLUX on Cloudflare', tag: 'free', note: 'Free, about 80 a day. Quick drafts; simpler scenes come out best.' },
  klein: { badge: 'FLUX local', name: 'FLUX klein on this laptop', local: true, seed: 'edit',
    note: 'Free, no tokens, no daily limit. The same FLUX, on this laptop. Edits a seed image.' },
  zimage: { badge: 'Z-Image', name: 'Z-Image Turbo on this laptop', local: true, seed: 'prompt',
    note: 'Free, no tokens. Rich, photographic detail; the slowest. Words only: it can\'t take an image.' },
  playground: { badge: 'Playground', name: 'Playground v2.5 on this laptop', local: true, seed: 'img2img',
    note: 'Free, no tokens. Painterly and colourful. Starts from a seed image.' },
  // SDXL community fine-tunes (26 Nov 2026)
  dreamshaper: { badge: 'DreamShaper', name: 'DreamShaper XL on this laptop', local: true, seed: 'img2img',
    note: 'Free, no tokens. All-rounder: painted, poster and print styles; fast. Starts from a seed image.' },
  juggernaut: { badge: 'Juggernaut', name: 'Juggernaut XL on this laptop', local: true, seed: 'img2img',
    note: 'Free, no tokens. Photographic and calm, good with people; the fastest. Starts from a seed image.' },
  zavychroma: { badge: 'ZavyChroma', name: 'ZavyChroma XL on this laptop', local: true, seed: 'img2img',
    note: 'Free, no tokens. Rich, saturated colour; slower. Starts from a seed image.' },
  animagine: { badge: 'Animagine', name: 'Animagine XL on this laptop', local: true, seed: 'img2img',
    note: 'Free, no tokens. Anime look; often drifts from the subject. Starts from a seed image.' },
};
// Who made each model and on what terms (26 Nov 2026), from the makers' own pages only (model cards, licences,
// announcements); each entry lists its sources. "Open weights": the files can be downloaded and run; the licence
// says what else is allowed. Not confirmed by the maker is said in the text, never filled in.
const SDXL_LINE = 'Stability AI\'s SDXL 1.0 (July 2023) is the open base model behind it.';
export const ABOUT = {
  codex: { by: 'OpenAI (USA)', released: 'GPT Image 2: Apr 2026 · Images 2.5: Sep 2026', open: 'Closed',
    licence: 'OpenAI\'s terms; no weights to download',
    history: 'OpenAI\'s GPT Image line, built into ChatGPT and Codex. ChatGPT Images 2.0 came in April 2026, '
      + 'Images 2.5 in September 2026. OpenAI does not say which version Codex\'s image tool runs.',
    good: 'Precise control, text in many languages, posters and infographics (OpenAI\'s examples).',
    sources: [['OpenAI: ChatGPT Images 2.0', 'https://openai.com/index/introducing-chatgpt-images-2-0/'],
      ['OpenAI: GPT Image 2 model page', 'https://developers.openai.com/api/docs/models/gpt-image-2']] },
  cloudflare: { by: 'Black Forest Labs (made it) · Cloudflare (hosts it)', released: 'Jan 2026', open: 'Open weights',
    licence: 'Apache 2.0 weights; the hosted service runs on Cloudflare\'s and Black Forest Labs\' terms',
    history: 'FLUX.2 [klein] 4B, the smallest and fastest model of FLUX.2, Black Forest Labs\' second FLUX '
      + 'generation. Cloudflare runs it on Workers AI.',
    good: 'Quick, interactive work: previews, drafts, making and editing in one model (Cloudflare).',
    sources: [['Cloudflare: FLUX.2 klein 4B', 'https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/'],
      ['Black Forest Labs: FLUX.2 klein', 'https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence']] },
  klein: { by: 'Black Forest Labs', released: 'Jan 2026', open: 'Open weights',
    licence: 'Apache 2.0 (commercial use allowed; the bigger 9B klein is non-commercial)',
    history: 'FLUX.2 [klein] 4B: the smallest, distilled model of FLUX.2, Black Forest Labs\' second FLUX '
      + 'generation. Its own design, not built on SDXL.',
    good: 'Fast text-to-image and editing on ordinary graphics cards (Black Forest Labs).',
    sources: [['Hugging Face: FLUX.2-klein-4B', 'https://huggingface.co/black-forest-labs/FLUX.2-klein-4B'],
      ['Black Forest Labs: FLUX.2 klein', 'https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence']] },
  zimage: { by: 'Tongyi-MAI, Z-Image team (Alibaba, from its contact address)', released: 'Nov 2025', open: 'Open weights',
    licence: 'Apache 2.0 (commercial use allowed)',
    history: 'Z-Image Turbo is the quick, distilled version of the 6-billion-parameter Z-Image model: '
      + 'about 8 steps per image instead of dozens. Its own design, not built on SDXL.',
    good: 'Photorealism, text in English and Chinese, following instructions (Tongyi-MAI).',
    sources: [['Hugging Face: Z-Image-Turbo', 'https://huggingface.co/Tongyi-MAI/Z-Image-Turbo'],
      ['GitHub: Tongyi-MAI/Z-Image', 'https://github.com/Tongyi-MAI/Z-Image']] },
  playground: { by: 'Playground (Playground AI, USA)', released: 'Feb 2024', open: 'Open weights',
    licence: 'Playground v2.5 Community License: commercial use free up to 1 million monthly users; '
      + 'images may not train other image models',
    history: 'Successor to Playground v2, trained by Playground on the SDXL design (about 3 billion parameters), '
      + 'tuned for aesthetic quality.',
    good: 'Good-looking images in many aspect ratios, people included (Playground).',
    sources: [['Hugging Face: Playground v2.5', 'https://huggingface.co/playgroundai/playground-v2.5-1024px-aesthetic'],
      ['Licence', 'https://huggingface.co/playgroundai/playground-v2.5-1024px-aesthetic/blob/main/LICENSE.md']] },
  dreamshaper: { by: 'Lykon (independent creator)', released: 'Feb 2024', open: 'Open weights',
    licence: 'OpenRAIL++ (use limits; commercial use allowed per its Civitai page)',
    history: 'A community fine-tune: DreamShaper XL began in July 2023 on SDXL. '
      + 'This Lightning build is tuned to draw in about 4–6 steps. ' + SDXL_LINE,
    good: 'An all-rounder in few steps: art, illustration and photo looks (Lykon).',
    sources: [['Hugging Face: dreamshaper-xl-lightning', 'https://huggingface.co/Lykon/dreamshaper-xl-lightning'],
      ['Civitai: DreamShaper XL', 'https://civitai.com/models/112902']] },
  juggernaut: { by: 'KandooAI, with RunDiffusion', released: 'Feb 2024', open: 'Open weights',
    licence: 'CreativeML Open RAIL-M; paid API use needs a licence from RunDiffusion',
    history: 'Juggernaut XL is a long-running photographic fine-tune of SDXL. This build is version 9 + RDPhoto2 '
      + '(its Civitai name), made with SDXL Lightning to draw in 4–6 steps. ' + SDXL_LINE,
    good: 'Photorealism, fast enough for live iteration on modest hardware (KandooAI).',
    sources: [['Hugging Face: Juggernaut-XL-Lightning', 'https://huggingface.co/RunDiffusion/Juggernaut-XL-Lightning'],
      ['Civitai: Juggernaut XL', 'https://civitai.com/models/133005']] },
  zavychroma: { by: 'Zavy (independent creator)', released: 'Oct 2024', open: 'Open weights',
    licence: 'Creator\'s own terms on Civitai: images may be sold, image services need a licence from Zavy, no derivatives',
    history: 'A community fine-tune of SDXL. Version 10 brings back the variety of styles of earlier versions, '
      + 'a little less steady than v9 (Zavy). ' + SDXL_LINE,
    good: 'Photographic quality with a wide range of styles (Zavy).',
    sources: [['Civitai: ZavyChromaXL', 'https://civitai.com/models/119229']] },
  animagine: { by: 'Cagliostro Research Lab', released: 'Jan 2025 (Opt: Feb 2025)', open: 'Open weights',
    licence: 'CreativeML Open RAIL++-M, same as SDXL (use limits; commercial use allowed)',
    history: 'The latest Animagine XL, retrained from SDXL 1.0 on about 8.4 million anime images. '
      + 'The Opt version improves stability, anatomy and colour. ' + SDXL_LINE,
    good: 'Anime-style images from tag prompts (Cagliostro).',
    sources: [['Hugging Face: animagine-xl-4.0', 'https://huggingface.co/cagliostrolab/animagine-xl-4.0']] },
};
// "Black Forest Labs · Open weights · Jan 2026": the short line under the picker and on hover.
export const aboutLine = (k) => { const a = ABOUT[k]; return a ? `${a.by} · ${a.open} · ${a.released}` : ''; };

export const LOCAL = ['klein', 'zimage', 'playground', 'dreamshaper', 'juggernaut', 'zavychroma', 'animagine'];
// seconds per image, measured 24-26 Nov 2026 (until runs.csv says more)
const SPEED = { klein: 109, zimage: 185, playground: 75, dreamshaper: 40, juggernaut: 30, zavychroma: 81, animagine: 70 };
export const modelBadge = (k) => MODELS[k]?.badge || (k === 'local' ? 'Local' : 'Codex');
export const modelName = (k) => MODELS[k]?.name || (k === 'local' ? 'A local model (blind test)' : 'Codex image tool (ChatGPT plan)');

// Shown where a feature needs ChatGPT to look at images or edit a style, while Local only is on.
export const LOCAL_NOTE = 'Uses ChatGPT tokens – turn off Local only.';

const MKEY = 'taste-model';
const LKEY = 'taste-local-only';
export const isLocalOnly = () => localStorage.getItem(LKEY) === '1';
export function setLocalOnly(on) {
  if (isLocalOnly() === !!on) return;
  localStorage.setItem(LKEY, on ? '1' : '0');
  document.dispatchEvent(new CustomEvent('taste-local-only'));
}
export function model() {
  let m = localStorage.getItem(MKEY) || (localStorage.getItem('taste-route') === 'cloudflare' ? 'cloudflare' : 'codex');
  if (!MODELS[m]) m = 'codex';
  if (isLocalOnly() && !MODELS[m].local) m = 'klein';
  return m;
}
export function setModel(m) { if (MODELS[m]) localStorage.setItem(MKEY, m); }
// New batch with several models (26 Nov 2026): the first is model(), the others are kept here, in pick order.
const MOREKEY = 'taste-models-more';
const more = () => { try { return JSON.parse(localStorage.getItem(MOREKEY)) || []; } catch { return []; } };
const setMore = (list) => localStorage.setItem(MOREKEY, JSON.stringify(list));
export function models() {
  const m = model();
  return [m, ...more().filter((k) => MODELS[k] && k !== m && (!isLocalOnly() || MODELS[k].local))];
}
// A chip in the several-models picker: on adds it, off drops it (the last one stays: a run needs a model).
function toggleModel(k) {
  const list = models();
  if (!list.includes(k)) { setMore([...list.slice(1), k]); return; }
  if (list.length === 1) return;
  const rest = list.filter((x) => x !== k);
  setModel(rest[0]);
  setMore(rest.slice(1));
}
// The route codex_run.py takes: codex, cloudflare or local (kept for older callers)
export const route = () => (MODELS[model()].local ? 'local' : model());

// The Models page's facts (defaults per style, Local only), shared for a minute like the allowance.
let info = null;
let infoAt = 0;
export async function modelInfo(fresh = false) {
  if (!fresh && info && Date.now() - infoAt < 60_000) return info;
  info = await api('models');
  infoAt = Date.now();
  setLocalOnly(info.local_only);
  return info;
}
export const styleDefault = (style) => (style && info?.defaults?.[style]) || '';

// A style's default model is picked once each time that style comes up in a dialog; Marc's own pick then holds.
let lastStyle = null;
export function preselect(style, multi = false) {
  if (!style || style === lastStyle || !info) return;
  lastStyle = style;
  if (multi && models().length > 1) return;   // several models picked by hand (New batch): that pick holds
  const d = info.defaults?.[style];
  if (d && MODELS[d] && (!isLocalOnly() || MODELS[d].local)) setModel(d);
}
export const resetPreselect = () => { lastStyle = null; };

function routePicker(onRoute, style, multi = false) {
  const m = model();
  const on = multi ? models() : [m];
  const keys = isLocalOnly() ? LOCAL : Object.keys(MODELS);
  const def = styleDefault(style);
  const pick = (k) => { if (multi) toggleModel(k); else setModel(k); onRoute(); };
  const several = on.length > 1;
  return h('div', { class: 'route-pick' },
    h('span', { class: 'nr-label' }, 'Made with'),
    h('div', { class: 'rseg rseg-wrap', role: 'group', 'aria-label': 'Made with' },
      keys.map((k) => h('button', { type: 'button', class: 'rseg-btn', 'aria-pressed': String(on.includes(k)), onClick: () => pick(k),
        title: `${MODELS[k].name}${def === k ? ' (default for this style)' : ''}\n${aboutLine(k)}` },
        MODELS[k].badge, MODELS[k].tag && h('small', {}, ' ' + MODELS[k].tag), def === k && h('small', { class: 'def-dot' }, ' · default')))),
    multi && h('p', { class: 'muted small' }, several
      ? `${on.length} models: one batch each, same settings and subjects, side by side. Click a model again to drop it.`
      : 'Pick more models to compare them: one batch each, same settings and subjects.'),
    !several && h('p', { class: 'muted small' }, MODELS[m].note, isLocalOnly() ? ' Local only is on (Models page).' : ''),
    !several && ABOUT[m] && h('p', { class: 'muted small model-about-line' }, aboutLine(m), ' · ',
      h('a', { href: '#/models', target: '_blank', rel: 'noopener' }, 'More on the Models page')));
}

// The make button: FLUX and the local models cost nothing, so it says so instead of "spend allowance".
export function makeLabel(n) {
  const m = model();
  if (MODELS[m].local) return `Make ${plural(n, 'image')} on this laptop`;
  return m === 'cloudflare' ? `Make ${plural(n, 'free image')}` : `Spend allowance: make ${plural(n, 'image')}`;
}

// Why Start can't go yet with this model ('' = it can).
export function routeBlocker(a, multi = false) {
  return (multi ? models() : [model()]).includes('cloudflare') && a && !a.error && !a.cloudflare?.connected ? 'Connect Cloudflare first.' : '';
}

// Seconds per image of a local model: measured from runs.csv, else the 24 Nov test.
export const localSeconds = (a, m) => a?.local?.speed?.[m]?.median || SPEED[m] || 120;

// A local model: no tokens, only laptop time. seed: this run starts from an image (what each model does with it).
function localBlock(a, n, m, extra, seed) {
  const secs = localSeconds(a, m);
  const min = Math.max(1, Math.round((n * secs) / 60) + 1);
  const seedLine = seed && {
    edit: 'FLUX local edits the seed image.',
    img2img: `${MODELS[m].badge} starts from the seed image and redraws about half of it.`,
    prompt: 'Z-Image can\'t take an image: it works from the seed\'s prompt and the change.',
  }[MODELS[m].seed];
  return [
    h('p', { class: 'cost-main' }, h('strong', {}, plural(n, 'image')),
      h('span', { class: 'muted' }, ` · free, no tokens · about ${min} min of laptop time`)),
    seedLine && h('p', { class: 'small' }, seedLine),
    extra && h('p', { class: 'muted small' }, extra),
    h('p', { class: 'muted small' }, `About ${Math.round(secs / 60 * 10) / 10} min per image here, plus a minute to load the model. `
      + 'The laptop works hard meanwhile; ComfyUI starts by itself and lets go of the memory after the run.'),
  ];
}

// Connect once: account ID and an API token, kept on this laptop outside the repo (never shown again).
function connectCard(onRoute) {
  const id = h('input', { type: 'text', placeholder: 'Account ID', 'aria-label': 'Cloudflare account ID', autocomplete: 'off', spellcheck: 'false' });
  const token = h('input', { type: 'password', placeholder: 'API token', 'aria-label': 'Cloudflare API token', autocomplete: 'off' });
  const msg = h('p', { class: 'small', role: 'status' });
  const save = h('button', { class: 'small-btn', onClick: async () => {
    if (!id.value.trim() || !token.value.trim()) { msg.textContent = 'Paste both, then Save.'; return; }
    save.setAttribute('aria-busy', 'true'); save.disabled = true; msg.textContent = '';
    try {
      await api('cloudflare/connect', { method: 'POST', body: { account_id: id.value.trim(), token: token.value.trim() } });
      await allowance(true);
      onRoute();
    } catch (err) {
      msg.textContent = err.message;
      save.removeAttribute('aria-busy'); save.disabled = false;
    }
  } }, 'Save');
  return h('div', { class: 'cf-connect' },
    h('p', {}, h('strong', {}, 'Connect Cloudflare once'), h('span', { class: 'muted' }, ' · about 5 minutes, free, no card')),
    h('ol', { class: 'small' },
      h('li', {}, h('a', { href: 'https://dash.cloudflare.com/sign-up', target: '_blank', rel: 'noopener' }, 'Make a free Cloudflare account'), '.'),
      h('li', {}, h('a', { href: 'https://dash.cloudflare.com/profile/api-tokens', target: '_blank', rel: 'noopener' }, 'Create an API token'),
        ' from the "Workers AI" template, and copy it.'),
      h('li', {}, 'Copy your Account ID: on the ', h('a', { href: 'https://dash.cloudflare.com/', target: '_blank', rel: 'noopener' }, 'dashboard'),
        ', in the account menu, "Copy account ID".')),
    h('div', { class: 'nr-row' }, id, token, save),
    msg,
    h('p', { class: 'muted small' }, 'Saved on this laptop only, outside the project. Nothing else is sent to Cloudflare but the prompts.'));
}

function cloudflareBlock(a, n, onRoute, extra) {
  const cf = a.cloudflare;
  if (!cf) return h('p', { class: 'small' }, 'Cloudflare status unknown: restart the app once.');
  if (!cf.connected) return connectCard(onRoute);
  // No promised reset time (24 Nov 2026): Cloudflare's "00:00 UTC" didn't hold. Once it refuses a call for the limit,
  // the block says so plainly and when the app last checked; the server checks once an hour for free.
  const over = !cf.used_up && n > cf.images_left;
  const day = cf.used_up
    ? h('p', { class: 'small over' },
      `FLUX's free images are used up (since ${cf.used_up_since}). Last checked ${cf.checked_at}; the app checks every hour `
      + 'and this line changes when FLUX is back. A run made now stops at once; "Finish this batch" makes it later.')
    : h('p', { class: 'small' + (over ? ' over' : ' muted') },
      `${plural(cf.images_today, 'image')} made today, about ${cf.images_left} left.`
      + (over ? ` This run needs ${n}: the ones past the limit wait for "Finish this batch" once FLUX is back.` : ''));
  return [
    h('p', { class: 'cost-main' }, h('strong', {}, plural(n, 'image')), h('span', { class: 'muted' }, ' · free · a few seconds each')),
    extra && h('p', { class: 'muted small' }, extra),
    !cf.used_up && meter('Today', Math.round((cf.neurons_used / cf.daily) * 100)),
    day,
    h('p', { class: 'muted small' }, cf.used_up ? '' : 'Estimated from this laptop\'s runs. ',
      h('button', { class: 'ghost small', onClick: async () => { await api('cloudflare/disconnect', { method: 'POST', body: {} }); await allowance(true); onRoute(); } },
        'Disconnect')),
  ];
}

// "Try with" for images ChatGPT's filter blocked (25 Nov 2026): FLUX on Cloudflare or a local model, remembered here.
const TKEY = 'taste-blocked-model';
export function tryModel() {
  const keys = isLocalOnly() ? LOCAL : ['cloudflare', ...LOCAL];
  const m = localStorage.getItem(TKEY);
  return keys.includes(m) ? m : keys[0];
}
export function tryPicker(onPick = () => {}) {
  const keys = isLocalOnly() ? LOCAL : ['cloudflare', ...LOCAL];
  return h('select', { class: 'try-with', 'aria-label': 'Try with which model',
    onChange: (e) => { localStorage.setItem(TKEY, e.target.value); onPick(e.target.value); } },
  keys.map((k) => h('option', { value: k, selected: tryModel() === k }, MODELS[k].badge + (MODELS[k].local ? ' (this laptop)' : ' (free)'))));
}

// A model's small label on a tile or in a details row.
export const modelTag = (k, cls = 'route-badge') => k && h('span', { class: cls, title: `Made with ${modelName(k)}` }, modelBadge(k));
