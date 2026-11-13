// Router: the address after # says which view to show, so Back, Forward and reload all work.
//   #/                          all batches
//   #/b/<batch>?show=...        one batch (show = to-rate | rated | ignored)
//   #/b/<batch>/<image>?show=   the same, with the large view open on one image
//   #/overview                  ratings per style
import { renderBatches } from './batches.js';
import { renderBatch } from './grid.js';
import { closeViewer } from './viewer.js';

const view = document.getElementById('view');

function parseHash() {
  const [path, query = ''] = location.hash.slice(1).split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  return { parts, query: new URLSearchParams(query) };
}

async function route() {
  const { parts, query } = parseHash();
  const page = parts[0] === 'overview' ? 'overview' : parts[0] === 'b' ? 'batch' : 'batches';
  for (const a of document.querySelectorAll('[data-nav]')) {
    a.toggleAttribute('aria-current', a.dataset.nav === page);
  }
  if (page !== 'batch') closeViewer();
  if (page === 'batch' && parts[1]) return renderBatch(view, parts[1], query.get('show'), parts[2]);
  await renderBatches(view);
}

window.addEventListener('hashchange', route);
route();
