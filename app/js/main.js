// Router: the address after # says which view to show, so Back, Forward and reload all work.
//   #/                          all batches
//   #/b/<batch>?show=...        one batch (show = all | to-rate | rated | ignored; all by default)
//   #/b/<batch>/<image>?show=   the same, with the large view open on one image
//   #/overview                  ratings per style
//   #/gallery?style=&rating=&batch=   every image; the large view has the thumbs
//   #/gallery/<batch>/<image>?...     the same, with the large view open on one image
//   #/styles[/<style>]          every style, on / off, its history, runs and 👍 rate
//   #/taste[/<style>]           the styles with my images as examples
//   #/models[/<style>]          the models side by side, Local only, each style's default model
//   #/guide[/<section>]         how to use the app, page by page, and use cases
//   #/about[/<section>]         why the project exists
//   #/new?mode=batch|one&style=a,b   start a run (batch with fresh subjects, or one image)
//   #/suggestions (#/distil)    Codex's style suggestions from the latest ratings; apply or skip
import { renderBatches } from './batches.js';
import { renderBatch } from './grid.js';
import { renderOverview } from './overview.js';
import { renderGallery, closeGalleryLarge } from './gallery.js';
import { renderTaste } from './taste.js';
import { renderStyles } from './styles.js';
import { renderAbout, renderGuide } from './about.js';
import { renderNewRun } from './newrun.js';
import { renderDistil } from './distil.js';
import { renderModels } from './models.js';
import { modelInfo, isLocalOnly } from './cost.js';
import { closeViewer } from './viewer.js';
import './job.js';   // picks up a run that may already be going
import './e2e.js';   // the chip that says the regression check found a break

const view = document.getElementById('view');

function parseHash() {
  const [path, query = ''] = location.hash.slice(1).split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  return { parts, query: new URLSearchParams(query) };
}

async function route() {
  const { parts, query } = parseHash();
  const pages = { overview: 'overview', b: 'batch', gallery: 'gallery', styles: 'styles', taste: 'taste', models: 'models', about: 'about', guide: 'guide', new: 'new', distil: 'overview', suggestions: 'overview' };
  const page = pages[parts[0]] || 'batches';
  for (const a of document.querySelectorAll('[data-nav]')) {
    a.toggleAttribute('aria-current', a.dataset.nav === page);
  }
  if (page !== 'batch' && closeViewer({ refocus: false })) window.scrollTo(0, 0);   // left the large view for another page
  if (page !== 'gallery') closeGalleryLarge();
  if (page === 'batch' && parts[1]) return renderBatch(view, parts[1], query.get('show'), parts[2]);
  if (parts[0] === 'distil' || parts[0] === 'suggestions') return renderDistil(view);   // under Overview in the header
  if (page === 'overview') return renderOverview(view);
  if (page === 'gallery') return renderGallery(view, query, parts[1] && parts[2] ? `${parts[1]}/${parts[2]}` : '');
  if (page === 'styles') return renderStyles(view, parts[1]);
  if (page === 'taste') return renderTaste(view, parts[1]);
  if (page === 'models') return renderModels(view, parts[1]);
  if (page === 'about') return renderAbout(view, parts[1]);
  if (page === 'guide') return renderGuide(view, parts[1]);
  if (page === 'new') return renderNewRun(view, query);
  await renderBatches(view);
}

// The header chip says when Local only is on (25 Nov 2026): no ChatGPT tokens, only the models on this laptop.
const chip = document.getElementById('local-chip');
const drawChip = () => { chip.hidden = !isLocalOnly(); };
document.addEventListener('taste-local-only', drawChip);
drawChip();
modelInfo().then(drawChip).catch(() => {});

window.addEventListener('hashchange', route);
route();
