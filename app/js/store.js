// The open batch, shared by the grid and the large view. One copy of the data, many views of it:
// a change is made here, then every view that cares hears about it through onChange().
export const store = {
  data: null,      // GET /api/batch/<batch>: summary + items
  show: 'to-rate', // grid filter
  styles: {},      // key -> {name, palette, description}
};

export const item = (name) => store.data?.items.find((im) => im.name === name);
// The variation type: what this image changed from its seed, or how it was made.
export const kindOf = (im) => im.change || (im.mode === 'text' ? 'from text' : im.mode) || '';
export const styleName = (key) => store.styles[key]?.name || key || 'no style';

// What the grid shows under each filter. Drafts are still "to rate": nothing is final until saved.
export const FILTERS = {
  'to-rate': { label: 'To rate', test: (im) => im.status === 'new' || im.status === 'draft',
               empty: 'Nothing left to rate in this batch.' },
  rated: { label: 'Rated', test: (im) => im.status === 'rated',
           empty: 'No saved ratings yet. Marks become ratings when you save the batch.' },
  ignored: { label: 'Ignored', test: (im) => im.status === 'ignored',
             empty: 'No ignored images. Press I on an image to hide it from the grid.' },
};
export const visible = () => (store.data?.items || []).filter(FILTERS[store.show].test);

// kind: 'mark' | 'why' | 'ignore' (one image); 'saved', 'reload' (read the batch again); 'job' (progress)
const listeners = new Set();
export const onChange = (fn) => listeners.add(fn);
export const changed = (name, kind) => listeners.forEach((fn) => fn(name, kind));
