// Text pages: About (the why) and Guide (how to use the app). The text lives in app/about.html and app/guide.html
// (plain HTML, easy to edit); this only loads a page and scrolls to a section.
//   #/about   #/about/<section>   #/guide   #/guide/<section>
import { h, showError } from './ui.js';

const cache = {};
const TITLES = { about: 'About', guide: 'Guide' };

async function renderPage(name, view, section) {
  try {
    cache[name] ??= await fetch(`/${name}.html`).then((r) => { if (!r.ok) throw new Error(`${name}.html: ${r.status}`); return r.text(); });
  } catch (err) {
    delete cache[name];
    view.replaceChildren(h('p', {}, `Could not load the ${TITLES[name]} page.`));
    return showError(err);
  }
  document.title = `${TITLES[name]} · taste`;
  view.innerHTML = cache[name];   // our own file from app/, never user input
  // A section link scrolls to it; otherwise start at the top, not where the last page was left.
  const target = section && document.getElementById(`${name}-${section}`);
  if (target) target.scrollIntoView({ block: 'start' });
  else window.scrollTo(0, 0);
}

export const renderAbout = (view, section) => renderPage('about', view, section);
export const renderGuide = (view, section) => renderPage('guide', view, section);
