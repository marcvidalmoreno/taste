// About: the story, the reasoning, the decisions. The text lives in app/about.html (plain HTML, easy to edit);
// this only loads it and scrolls to a section.   #/about   #/about/<section>
import { h, showError } from './ui.js';

let cache;

export async function renderAbout(view, section) {
  try {
    cache ??= await fetch('/about.html').then((r) => { if (!r.ok) throw new Error(`about.html: ${r.status}`); return r.text(); });
  } catch (err) {
    cache = undefined;
    view.replaceChildren(h('p', {}, 'Could not load the About page.'));
    return showError(err);
  }
  document.title = 'About · taste';
  view.innerHTML = cache;   // our own file from app/, never user input
  if (section) document.getElementById('about-' + section)?.scrollIntoView({ block: 'start' });
}
