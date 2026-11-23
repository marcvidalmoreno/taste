// The only place that talks to the server (scripts/app.py). Every view goes through api().

// Writes carry a custom header. A web page on another site cannot add it without the server's
// permission (CORS preflight), and this server never gives it: only this page can change files.
const WRITE_HEADERS = { 'Content-Type': 'application/json', 'X-Taste-App': '1' };

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch('/api/' + path, {
    method,
    headers: method === 'GET' ? {} : WRITE_HEADERS,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || `${res.status} ${res.statusText}`), { status: res.status });
  return data;
}

// Styles change rarely: load them once and share.
// styles() is the ones that are on (the picker, Taste, edits); allStyles() adds the ones switched off, for labels
// (a switched-off style still names its images in the Gallery and the Overview).
let stylesPromise;
const load = () => (stylesPromise ??= api('styles').catch(() => ({ styles: {}, archived: {} })));
export const styles = () => load().then((d) => d.styles);
export const archivedStyles = () => load().then((d) => d.archived || {});
export const allStyles = () => load().then((d) => ({
  ...Object.fromEntries(Object.entries(d.archived || {}).map(([k, v]) => [k, { ...v, archived: true }])), ...d.styles }));
// After a style edit or a switch: read them again (every caller then gets the new text).
export function refreshStyles() {
  stylesPromise = null;
  return styles();
}
