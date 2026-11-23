// What a run costs, shown the same way everywhere something spends Codex allowance (new run, remix,
// variations): the meters from Codex's own log, this run in images / minutes / share of the window, and the
// week against the budget. Numbers are measured (README "Allowance"), never typed by hand.
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
  cached = await api('allowance');
  at = Date.now();
  return cached;
}

// A used-percentage meter: one thin bar, the number written next to it (never colour alone).
export function meter(label, used) {
  const pct = Math.max(0, Math.min(100, Number(used) || 0));
  return h('div', { class: 'meter' },
    h('span', {}, label),
    h('span', { class: 'bar', role: 'meter', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': pct,
                'aria-label': `${label}: ${pct} % used` }, h('i', { style: { width: pct + '%' } })),
    h('span', { class: 'num' }, `${pct} % used`));
}

// a: GET /api/allowance (or {error}), n: images this run would make, extra: e.g. 'Codex writes subjects first: ~15 s each'
// onRoute: redraw callback; given, the block starts with the "Made with" choice (ChatGPT or FLUX on Cloudflare).
export function costBlock(a, n, { extra = '', compact = false, onRoute = null } = {}) {
  const pick = onRoute && routePicker(onRoute);
  if (!a) return h('section', { class: 'cost', 'aria-busy': 'true' }, pick, 'Reading the allowance…');
  if (a.error) return h('section', { class: 'cost' }, pick, `Allowance unknown: ${a.error}`);
  const dry = a.dry_run && h('p', { class: 'notice' }, 'Dry run: the app was started with --dry-run. Nothing will be generated or spent.');
  if (onRoute && route() === 'cloudflare') return h('section', { class: 'cost' }, pick, dry, cloudflareBlock(a, n, onRoute, extra));
  const after = a.week_images + (a.queued_images || 0) + n;
  const over = after > a.week_budget;
  return h('section', { class: 'cost' },
    pick,
    dry,
    h('p', { class: 'cost-main' },
      h('strong', {}, plural(n, 'image')),
      h('span', { class: 'muted' }, ` · about ${n * COST.minutes} min · ≈ ${(n * COST.fiveLow).toFixed(1)}–${(n * COST.fiveHigh).toFixed(1)} % of the five-hour window`)),
    extra && h('p', { class: 'muted small' }, extra),
    !compact && (a.now ? h('div', { class: 'meters' },
      meter('Five-hour window', a.now.five_hour), meter('This week', a.now.weekly),
      h('p', { class: 'muted small' }, `Used, from Codex's own log as of ${a.now.as_of.slice(11)} on ${a.now.as_of.slice(0, 10)}.`))
      : h('p', { class: 'small' }, `Allowance unknown: ${a.unknown_reason || 'no reading'}`)),
    h('p', { class: 'small' + (over ? ' over' : ' muted') },
      `Images in the last 7 days: ${a.week_images}` + (a.queued_images ? ` (+${a.queued_images} queued)` : '')
      + `, budget ~${a.week_budget}` + (over ? ` – this run takes it to ${after}, over the budget.` : '.')));
}

// ---------------------------------------------------------------- which model makes the images (23 Nov 2026)
// "Made with": ChatGPT through Codex (default) or FLUX on Cloudflare's free daily allowance (docs/cloudflare-route.md).
// One choice for the whole app, remembered in this browser; every dialog that spends shows it in its cost box.
const RKEY = 'taste-route';
export const route = () => (localStorage.getItem(RKEY) === 'cloudflare' ? 'cloudflare' : 'codex');
const ROUTE_NOTE = {
  codex: 'Best quality and closest to the style. Uses the Codex allowance.',
  cloudflare: 'Free, about 80 a day. Quick drafts; simpler scenes come out best.',
};

function routePicker(onRoute) {
  const r = route();
  const pick = (k) => { localStorage.setItem(RKEY, k); onRoute(); };
  return h('div', { class: 'route-pick' },
    h('span', { class: 'nr-label' }, 'Made with'),
    h('div', { class: 'rseg', role: 'group', 'aria-label': 'Made with' },
      h('button', { type: 'button', class: 'rseg-btn', 'aria-pressed': String(r === 'codex'), onClick: () => pick('codex') }, 'ChatGPT'),
      h('button', { type: 'button', class: 'rseg-btn', 'aria-pressed': String(r === 'cloudflare'), onClick: () => pick('cloudflare') },
        'FLUX ', h('small', {}, 'free'))),
    h('p', { class: 'muted small' }, ROUTE_NOTE[r]));
}

// The make button: FLUX costs nothing, so it says "free" instead of "spend allowance".
export const makeLabel = (n) => (route() === 'cloudflare' ? `Make ${plural(n, 'free image')}` : `Spend allowance: make ${plural(n, 'image')}`);

// Why Start can't go yet on this route ('' = it can).
export function routeBlocker(a) {
  return route() === 'cloudflare' && a && !a.error && !a.cloudflare?.connected ? 'Connect Cloudflare first.' : '';
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
  const over = n > cf.images_left;
  return [
    h('p', { class: 'cost-main' }, h('strong', {}, plural(n, 'image')), h('span', { class: 'muted' }, ' · free · a few seconds each')),
    extra && h('p', { class: 'muted small' }, extra),
    meter('Today', Math.round((cf.neurons_used / cf.daily) * 100)),
    h('p', { class: 'small' + (over ? ' over' : ' muted') },
      `${plural(cf.images_today, 'image')} made today, about ${cf.images_left} left; more at ${cf.resets_at}.`
      + (over ? ` This run needs ${n}: the ones past the limit wait for "Finish this batch" after ${cf.resets_at}.` : '')),
    h('p', { class: 'muted small' }, 'Estimated from this laptop\'s runs. ',
      h('button', { class: 'ghost small', onClick: async () => { await api('cloudflare/disconnect', { method: 'POST', body: {} }); await allowance(true); onRoute(); } },
        'Disconnect')),
  ];
}
