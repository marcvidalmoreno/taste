// Router: the address after # says which view to show, so Back, Forward and reload all work.
//   #/                          all batches
//   #/b/<batch>?show=...        one batch (show = to-rate | rated | ignored)
//   #/b/<batch>/<image>?show=   the same, with the large view open on one image
//   #/overview                  ratings per style
//   #/gallery?style=&rating=&batch=   every image, read-only
//   #/taste[/<style>]           the styles with my images as examples
//   #/about[/<section>]         story, reasoning, decisions
//   #/new?mode=batch|one&style=a,b   start a run (batch with fresh subjects, or one image)
//   #/distil                    Codex proposes style edits from the new ratings; apply style by style
import { renderBatches } from './batches.js';
import { renderBatch } from './grid.js';
import { renderOverview } from './overview.js';
import { renderGallery } from './gallery.js';
import { renderTaste } from './taste.js';
import { renderAbout } from './about.js';
import { renderNewRun } from './newrun.js';
import { renderDistil } from './distil.js';
import { closeViewer } from './viewer.js';
import './job.js';   // picks up a run that may already be going

const view = document.getElementById('view');

function parseHash() {
  const [path, query = ''] = location.hash.slice(1).split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  return { parts, query: new URLSearchParams(query) };
}

async function route() {
  const { parts, query } = parseHash();
  const pages = { overview: 'overview', b: 'batch', gallery: 'gallery', taste: 'taste', about: 'about', new: 'new', distil: 'overview' };
  const page = pages[parts[0]] || 'batches';
  for (const a of document.querySelectorAll('[data-nav]')) {
    a.toggleAttribute('aria-current', a.dataset.nav === page);
  }
  if (page !== 'batch') closeViewer();
  if (page === 'batch' && parts[1]) return renderBatch(view, parts[1], query.get('show'), parts[2]);
  if (parts[0] === 'distil') return renderDistil(view);   // under Overview in the header
  if (page === 'overview') return renderOverview(view);
  if (page === 'gallery') return renderGallery(view, query);
  if (page === 'taste') return renderTaste(view, parts[1]);
  if (page === 'about') return renderAbout(view, parts[1]);
  if (page === 'new') return renderNewRun(view, query);
  await renderBatches(view);
}

window.addEventListener('hashchange', route);
route();
