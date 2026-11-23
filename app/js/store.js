// The open batch, shared by the grid and the large view. One copy of the data, many views of it:
// a change is made here, then every view that cares hears about it through onChange().
export const store = {
  data: null,      // GET /api/batch/<batch>: summary + items
  show: 'all',     // grid filter
  styles: {},      // key -> {name, palette, description}
  justRated: new Set(),  // marked since the batch was opened: kept in the "To rate" grid until it is read again
};

export const item = (name) => store.data?.items.find((im) => im.name === name);
// The variation type: what this image changed from its seed, or how it was made.
export const kindOf = (im) => im.change || (im.mode === 'text' ? 'from text' : im.mode) || '';
export const styleName = (key) => store.styles[key]?.name || key || 'no style';

// What the grid shows under each filter. An image marked while the batch is open stays under "To rate" too,
// so the grid doesn't reflow under the pointer; it moves to "Rated" the next time the batch is opened.
// "All" (the default since 23 Nov 2026) is every image except the ignored ones: rating never moves a tile.
export const FILTERS = {
  all: { label: 'All', test: (im) => im.status !== 'ignored', empty: 'No images in this batch yet.' },
  'to-rate': { label: 'To rate', test: (im) => im.status === 'new' || store.justRated.has(im.name),
               empty: 'Nothing left to rate in this batch.' },
  rated: { label: 'Rated', test: (im) => im.status === 'rated',
           empty: 'No ratings yet. Press Up or Down on an image: it counts at once.' },
  ignored: { label: 'Ignored', test: (im) => im.status === 'ignored',
             empty: 'No ignored images. Press I on an image to hide it from the grid.' },
};
export const visible = () => (store.data?.items || []).filter(FILTERS[store.show].test);

// kind: 'mark' | 'why' | 'ignore' (one image); 'saved', 'reload' (read the batch again); 'job' (progress)
const listeners = new Set();
export const onChange = (fn) => listeners.add(fn);
export const changed = (name, kind) => listeners.forEach((fn) => fn(name, kind));
