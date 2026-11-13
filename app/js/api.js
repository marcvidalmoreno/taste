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
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

// Styles change rarely: load them once and share.
let stylesPromise;
export function styles() {
  stylesPromise ??= api('styles').then((d) => d.styles).catch(() => ({}));
  return stylesPromise;
}
