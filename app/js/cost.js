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
export function costBlock(a, n, { extra = '', compact = false } = {}) {
  if (!a) return h('section', { class: 'cost', 'aria-busy': 'true' }, 'Reading the allowance…');
  if (a.error) return h('section', { class: 'cost' }, `Allowance unknown: ${a.error}`);
  const after = a.week_images + (a.queued_images || 0) + n;
  const over = after > a.week_budget;
  return h('section', { class: 'cost' },
    a.dry_run && h('p', { class: 'notice' }, 'Dry run: the app was started with --dry-run. Nothing will be generated or spent.'),
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
