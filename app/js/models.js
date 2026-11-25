// Models (25 Nov 2026): the five ways to make an image side by side, and each style's default model.
//   #/models            the cards, Local only, and one style compared across the models
//   #/models/<style>    the same, with that style picked
// Cards: what each model is good at, how many images it made, median seconds per image (runs.csv) and usage where
// it applies (ChatGPT: the Codex week; FLUX: free images left today; local: laptop minutes, no tokens).
// One style: each model's latest images of it (the 24 Nov test batches first: same prompt and seed on every local
// model, so the columns line up), its thumbs-up rate for the style, and one click to make it the default.
// The default lives in generated/codex/style-models.json; New run, One image, Remix and Variations preselect it.
import { api, styles } from './api.js';
import { allowance, modelInfo, MODELS, LOCAL, isLocalOnly, setLocalOnly, localSeconds } from './cost.js';
import { galleryHref } from './gallery.js';
import { h, thumbUrl, plural, showError, toast } from './ui.js';

let view, all = {}, info = null, alw = null, styleKey = '';

export async function renderModels(el, style) {
  view = el;
  document.title = 'Models · taste';
  view.replaceChildren(h('p', { 'aria-busy': 'true' }, 'Reading the models…'));
  try {
    [all, info] = await Promise.all([styles(), modelInfo(true)]);
  } catch (err) {
    view.replaceChildren(h('p', {}, 'Could not read the models.'));
    return showError(err);
  }
  styleKey = all[style] ? style : styleKey && all[styleKey] ? styleKey : Object.keys(all)[0];
  draw();
  allowance().then((a) => { alw = a; }).catch((e) => { alw = { error: e.message }; }).finally(() => { if (view.querySelector('.models-page')) drawCards(); });
}

let cardsEl, styleEl;

function draw() {
  cardsEl = h('div', { class: 'model-cards' });
  styleEl = h('section', { class: 'model-style' });
  view.replaceChildren(h('div', { class: 'models-page' },
    h('hgroup', { class: 'page-head' }, h('h1', {}, 'Models'),
      h('p', {}, 'Five ways to make an image. Compare them here, and pick the model each style starts with.')),
    localOnlyCard(),
    cardsEl,
    styleEl));
  drawCards();
  drawStyle();
}

// Local only: one switch. On: only the three models on this laptop run, and a local model writes subjects and prompts.
function localOnlyCard() {
  const on = isLocalOnly();
  const flip = async (btn) => {
    btn.disabled = true;
    try {
      const r = await api('models/local-only', { method: 'POST', body: { on: !on } });
      setLocalOnly(r.local_only);
      await modelInfo(true);
      toast(r.local_only ? 'Local only is on: no ChatGPT tokens' : 'Local only is off');
      draw();
    } catch (err) { btn.disabled = false; showError(err); }
  };
  return h('section', { class: 'local-only' + (on ? ' is-on' : '') },
    h('div', {},
      h('h2', {}, 'Local only'),
      h('p', { class: 'small' }, on
        ? 'On. Only FLUX local, Z-Image and Playground run, and a model on this laptop writes subjects and prompt rewrites. No ChatGPT tokens.'
        : 'Off. Turn it on to use no ChatGPT tokens at all: only the models on this laptop, and a local model writes subjects and prompts.'),
      h('p', { class: 'muted small' }, 'While it is on, New style from images, Suggestions (distil), Change the style and Fork with Codex wait: they need ChatGPT to read images or rewrite a style.')),
    h('button', { type: 'button', role: 'switch', 'aria-checked': String(on), class: 'switch-btn', onClick: (e) => flip(e.currentTarget) },
      h('span', { class: 'knob', 'aria-hidden': 'true' }), on ? 'On' : 'Off'));
}

const secsText = (s) => (s == null ? 'not measured yet' : s < 90 ? `${s} s per image` : `${(s / 60).toFixed(1)} min per image`);
const pctText = (r) => (r == null ? 'no thumbs yet' : `👍 ${Math.round(r * 100)} %`);

function usage(k) {
  if (!alw) return h('span', { 'aria-busy': 'true' }, 'Reading…');
  if (alw.error) return `Usage unknown: ${alw.error}`;
  if (k === 'codex') return alw.now ? `This Codex week: ${alw.now.weekly} % used, ${plural(alw.week_images, 'image')} so far` : 'Codex week unknown';
  if (k === 'cloudflare') {
    const cf = alw.cloudflare;
    if (!cf?.connected) return 'Not connected (New run, Made with: FLUX)';
    return cf.used_up ? `Free images used up today (since ${cf.used_up_since})` : `Free · about ${cf.images_left} images left today`;
  }
  return `Free, no tokens · about ${Math.max(1, Math.round(localSeconds(alw, k) / 60))} min of laptop time per image`;
}

function drawCards() {
  const keys = isLocalOnly() ? LOCAL : Object.keys(MODELS);
  const cards = info.models.filter((m) => keys.includes(m.key));
  cardsEl.replaceChildren(...cards.map((m) => h('article', { class: 'model-card' },
    h('header', {}, h('span', { class: 'route-badge' }, m.badge), h('strong', {}, m.name)),
    h('p', { class: 'small' }, m.good),
    h('dl', { class: 'model-facts small' },
      h('dt', {}, 'Speed'), h('dd', {}, secsText(m.median_seconds)),
      h('dt', {}, 'Made'), h('dd', {}, m.images ? h('a', { href: galleryHref({ model: m.key }) }, plural(m.images, 'image')) : 'none yet'),
      h('dt', {}, 'Liked'), h('dd', {}, pctText(m.rate), m.n ? h('span', { class: 'muted' }, ` of ${m.n} rated`) : ''),
      h('dt', {}, 'Usage'), h('dd', {}, usage(m.key))))));
}

async function drawStyle() {
  const keys = Object.keys(all).sort((a, b) => all[a].name.localeCompare(all[b].name));
  const picker = h('select', { 'aria-label': 'Style to compare', onChange: (e) => { location.hash = '#/models/' + encodeURIComponent(e.target.value); } },
    keys.map((k) => h('option', { value: k, selected: k === styleKey }, all[k].name + (info.defaults[k] ? ` · ${MODELS[info.defaults[k]]?.badge}` : ''))));
  const body = h('div', { 'aria-busy': 'true' }, 'Reading the images…');
  const set = Object.entries(info.defaults).filter(([k]) => all[k]);
  styleEl.replaceChildren(
    h('div', { class: 'model-style-head' },
      h('h2', {}, 'One style, every model'), picker),
    h('p', { class: 'muted small' }, set.length
      ? `Defaults so far: ${set.map(([k, m]) => `${all[k].name} → ${MODELS[m]?.badge}`).join(', ')}. Styles without one start with the model you used last.`
      : 'No style has a default yet: each starts with the model you used last. Pick one below.'),
    body);
  let d;
  try { d = await api('models/style/' + encodeURIComponent(styleKey)); } catch (err) { body.removeAttribute('aria-busy'); body.textContent = err.message; return; }
  body.removeAttribute('aria-busy');
  const shownKeys = isLocalOnly() ? LOCAL : Object.keys(MODELS);
  body.replaceChildren(h('div', { class: 'model-rows' }, d.models.filter((m) => shownKeys.includes(m.key)).map((m) => row(m, d.default))));
}

function row(m, def) {
  const isDef = def === m.key;
  const pick = async (btn) => {
    btn.disabled = true;
    try {
      const r = await api('models/default', { method: 'POST', body: { style: styleKey, model: isDef ? '' : m.key } });
      info.defaults = r.defaults;
      await modelInfo(true);
      toast(isDef ? `${all[styleKey].name}: no default model` : `${all[styleKey].name} now starts with ${m.badge}`);
      drawStyle();
    } catch (err) { btn.disabled = false; showError(err); }
  };
  return h('div', { class: 'model-row' + (isDef ? ' is-default' : '') },
    h('div', { class: 'model-row-head' },
      h('span', { class: 'route-badge' }, m.badge),
      h('span', { class: 'small' }, m.count ? h('a', { href: galleryHref({ style: styleKey, model: m.key }) }, plural(m.count, 'image')) : h('span', { class: 'muted' }, 'none yet')),
      h('span', { class: 'small muted' }, m.n ? `👍 ${Math.round(m.rate * 100)} % of ${m.n} rated` : 'no thumbs yet'),
      h('span', { class: 'spacer' }),
      h('button', { type: 'button', class: isDef ? 'small-btn' : 'secondary outline small-btn', 'aria-pressed': String(isDef),
        title: isDef ? 'Press again to clear the default' : `New runs of this style start with ${m.badge}`, onClick: (e) => pick(e.currentTarget) },
      isDef ? '✓ Default' : 'Make default')),
    m.images.length
      ? h('ul', { class: 'model-thumbs' }, m.images.map((im, i) => h('li', {},
        h('a', { href: galleryHref({ style: styleKey, model: m.key }, im), title: i < m.test ? 'From the 24 Nov test: same prompt on every local model' : im.batch },
          h('img', { src: thumbUrl(im.batch, im.file, im.mtime), alt: '', loading: 'lazy' }),
          im.rating && h('span', { class: `mark ${im.rating} saved`, 'aria-hidden': 'true' }, im.rating === 'keep' ? '👍' : im.rating === 'no' ? '👎' : '~')))))
      : h('p', { class: 'muted small' }, `No ${all[styleKey].name} image from ${m.badge} yet.`));
}
