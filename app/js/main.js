// Router: the address after # says which view to show, so Back, Forward and reload all work.
//   #/                      all batches
//   #/b/<batch>?show=...    one batch (show = to-rate | rated | ignored)
//   #/overview              ratings per style
import { renderBatches } from './batches.js';

const view = document.getElementById('view');

function parseHash() {
  const [path, query = ''] = location.hash.slice(1).split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  return { parts, query: new URLSearchParams(query) };
}

async function route() {
  const { parts } = parseHash();
  const page = parts[0] === 'overview' ? 'overview' : 'batches';
  for (const a of document.querySelectorAll('[data-nav]')) {
    a.toggleAttribute('aria-current', a.dataset.nav === page && parts[0] !== 'b');
  }
  await renderBatches(view);
}

window.addEventListener('hashchange', route);
route();
