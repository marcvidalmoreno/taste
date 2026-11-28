"""UX audit capture for the taste web app (project-specific half of the ux-audit skill).

    .venv/Scripts/python -I ux-audit/run_audit.py http://127.0.0.1:<port>

Run it ONLY against the fake-data copy (`scripts/e2e.py --serve`), never the real app on 8791: it creates a style
and marks images. Writes ux-audit/screens/*.png and ux-audit/raw/*.json. Test images: ux-audit/.tools/test-images/.
"""
import json, re, sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path.home() / '.claude' / 'skills' / 'ux-audit' / 'scripts'))   # the global ux-audit skill
from capture_lib import Audit, slow_network   # noqa: E402
from playwright.sync_api import sync_playwright   # noqa: E402

URL = sys.argv[1].rstrip('/')
assert ':8791' not in URL, 'never the real app'
OUT = ROOT / 'ux-audit'
IMG = OUT / '.tools' / 'test-images'
B1 = '2026-01-01-quiet-meadow'
WIDTHS = {1440: (1440, 900), 390: (390, 844)}
a = Audit(out=OUT, axe=OUT / '.tools' / 'node_modules' / 'axe-core' / 'axe.min.js')
extra = {'errors': [], 'tab_walks': {}, 'console': [], 'notes': [], 'blocked_clicks': []}


def go(page, hash_, wait='#view > *'):
    if page.locator('dialog[open]').count():
        page.goto('about:blank')
    page.goto(f'{URL}/#{hash_}')
    page.wait_for_selector(wait, timeout=15000)
    page.wait_for_timeout(600)


def click(page, sel):
    """Click like a person; if something covers the target, record it as evidence and click through the DOM."""
    try:
        page.click(sel, timeout=4000)
    except Exception as e:
        covers = [ln.strip()[:200] for ln in str(e).splitlines() if 'intercepts pointer events' in ln]
        extra['blocked_clicks'].append({'url': page.url, 'target': sel, 'viewport': page.viewport_size['width'],
                                        'covered_by': covers[-1] if covers else str(e).splitlines()[0][:200]})
        page.locator(sel).first.dispatch_event('click')


def flow(fn):
    def run(page, w):
        try:
            fn(page, w)
        except Exception as e:   # one broken step must not stop the rest
            extra['errors'].append(f'{fn.__name__}@{w}: {e}')
            traceback.print_exc()
            try:
                page.screenshot(path=str(OUT / 'raw' / f'error-{fn.__name__}-{w}.png'))
                page.goto('about:blank')   # a dialog left open must not leak into the next flow
            except Exception:
                pass
    run.__name__ = fn.__name__
    return run


def close_dialogs(page):
    for _ in range(3):
        if page.locator('dialog[open]').count():
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)


# ---------------------------------------------------------------- flows

@flow
def land(page, w):
    go(page, '/')
    a.capture(page, 'land', 'batches', w)
    a.capture(page, 'land', 'batches-fold', w, full_page=False)
    if w == 1440:
        extra['tab_walks']['land'] = a.tab_walk(page, 30)


@flow
def land_empty(page, w):
    page.route('**/api/batches', lambda r: r.fulfill(status=200, content_type='application/json', body='{"batches": []}'))
    page.goto('about:blank')
    go(page, '/')
    a.capture(page, 'land', 'empty', w)
    page.unroute('**/api/batches')


@flow
def land_error(page, w):
    page.route('**/api/batches', lambda r: r.fulfill(status=500, content_type='application/json', body='{"error": "server error"}'))
    page.goto('about:blank')
    page.goto(f'{URL}/#/')
    page.wait_for_timeout(2500)
    a.capture(page, 'land', 'server-error', w)
    page.unroute('**/api/batches')


@flow
def land_slow(page, w):
    """Cold load on Slow 3G: when does anything show, when does the list show."""
    ctx_page = page.context.new_page()
    slow_network(ctx_page, 'slow3g')
    t0 = time.perf_counter()
    ctx_page.goto(f'{URL}/#/', wait_until='commit')
    first = done = None
    while time.perf_counter() - t0 < 60:
        st = ctx_page.evaluate("() => ({ paint: performance.getEntriesByType('paint').some(e => e.name === 'first-contentful-paint'), view: !!document.querySelector('#view > *') })")
        if first is None and st['paint']:
            first = time.perf_counter() - t0
            ctx_page.screenshot(path=str(OUT / 'screens' / f'land-slow3g-first-paint-{w}.png'))
        if st['view']:
            done = time.perf_counter() - t0
            break
        ctx_page.wait_for_timeout(100)
    a.timings.append({'label': f'cold load, Slow 3G, {w}px', 'first_feedback_ms': round((first or 0) * 1000), 'result_ms': round((done or 0) * 1000) or None})
    ctx_page.close()


def open_new_style(page):
    go(page, '/taste')
    click(page, 'button:has-text("New style from images")')
    page.wait_for_selector('dialog.new-style[open]')
    page.wait_for_timeout(300)


@flow
def extract(page, w):
    open_new_style(page)
    a.capture(page, 'extract', '1-empty', w, full_page=False)
    if w == 1440:
        extra['tab_walks']['extract-dialog'] = a.tab_walk(page, 15)
    files = [str(IMG / f'test-{i}.jpg') for i in (1, 2, 3)]
    t0 = time.perf_counter()
    page.set_input_files('dialog.new-style input[type=file]', files)
    page.wait_for_function('document.querySelectorAll("dialog.new-style .ref-tile img").length === 3')
    a.timings.append({'label': f'add 3 images → tiles shown, {w}px', 'first_feedback_ms': None, 'result_ms': round((time.perf_counter() - t0) * 1000)})
    page.fill('#ns-notes', 'muted dusk colours, flat shapes, one small figure in a big space')
    a.capture(page, 'extract', '2-images-added', w, full_page=False)

    # Hold the propose request: Codex really takes ~30-60 s; the dry-run copy answers at once.
    held = []
    page.route('**/api/style/new/propose', lambda r: held.append(r))
    btn = 'dialog.new-style footer button:not(.secondary)'
    a.time_it(page, f'propose click → first feedback, {w}px', lambda: click(page, btn),
              done_js='document.querySelector("dialog.new-style footer button[aria-busy=true]") !== null', timeout=5)
    page.wait_for_timeout(2000)
    a.capture(page, 'extract', '3-in-progress-2s', w, full_page=False)
    page.wait_for_timeout(10000)
    a.capture(page, 'extract', '3-in-progress-12s', w, full_page=False)
    t0 = time.perf_counter()
    held[0].continue_()
    page.unroute('**/api/style/new/propose')
    page.wait_for_selector('#ns-final-name', timeout=30000)
    a.timings.append({'label': f'propose answer → proposal shown (dry run, after the hold), {w}px', 'first_feedback_ms': None, 'result_ms': round((time.perf_counter() - t0) * 1000)})
    page.wait_for_timeout(400)
    a.capture(page, 'extract', '4-proposal', w, full_page=True)
    a.capture(page, 'extract', '4-proposal-fold', w, full_page=False)
    # Missing field: empty the description
    page.fill('#ns-description', '')
    page.wait_for_timeout(200)
    a.capture(page, 'extract', '5-missing-field', w, full_page=False)
    page.fill('#ns-description', 'Muted dusk landscape, flat shapes, a small figure (audit test).')
    page.fill('#ns-final-name', f'Audit test {w}')
    click(page, 'dialog.new-style footer button:has-text("Create style")')
    page.wait_for_selector('#ns-first-run', timeout=15000)
    page.wait_for_timeout(400)
    a.capture(page, 'extract', '6-created', w, full_page=False)
    close_dialogs(page)


@flow
def extract_errors(page, w):
    open_new_style(page)
    inp = 'dialog.new-style input[type=file]'
    page.set_input_files(inp, str(IMG / 'notes.txt'))
    page.wait_for_timeout(500)
    a.capture(page, 'extract', 'err-not-an-image', w, full_page=False)
    page.wait_for_timeout(5500)
    page.set_input_files(inp, str(IMG / 'corrupt.png'))
    page.wait_for_timeout(800)
    a.capture(page, 'extract', 'err-corrupt-file', w, full_page=False)
    page.wait_for_timeout(5500)
    t0 = time.perf_counter()
    page.set_input_files(inp, str(IMG / 'huge-12000.png'))
    busy_seen = page.evaluate('() => !!document.querySelector("dialog.new-style [aria-busy=true], dialog.new-style .is-loading")')
    page.wait_for_function('document.querySelectorAll("dialog.new-style .ref-tile img").length === 1', timeout=60000)
    a.timings.append({'label': f'add one 12000×12000 PNG → tile shown, {w}px', 'first_feedback_ms': None, 'result_ms': round((time.perf_counter() - t0) * 1000), 'busy_indicator_seen': busy_seen})
    a.capture(page, 'extract', 'edge-huge-image', w, full_page=False)
    page.set_input_files(inp, [str(IMG / 'odd-ratio-4000x200.jpg'), str(IMG / 'tiny-8px.png'), str(IMG / 'test-4.jpg'), str(IMG / 'test-5.jpg')])
    page.wait_for_timeout(1500)
    a.capture(page, 'extract', 'edge-too-many-odd-tiny', w, full_page=False)
    # Server errors on propose
    for status, body, name in ((502, '{"error": "codex: the model is busy, try again later"}', 'err-502'),
                               (413, '{"error": "request too large"}', 'err-413')):
        page.route('**/api/style/new/propose', (lambda s, b: lambda r: r.fulfill(status=s, content_type='application/json', body=b))(status, body))
        click(page, 'dialog.new-style footer button:not(.secondary)')
        page.wait_for_timeout(900)
        a.capture(page, 'extract', name, w, full_page=False)
        page.unroute('**/api/style/new/propose')
        page.wait_for_timeout(5500)
    page.route('**/api/style/new/propose', lambda r: r.abort('internetdisconnected'))
    click(page, 'dialog.new-style footer button:not(.secondary)')
    page.wait_for_timeout(900)
    a.capture(page, 'extract', 'err-offline', w, full_page=False)
    page.unroute('**/api/style/new/propose')
    # Escape with images added: is the work lost?
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)
    extra['notes'].append({'w': w, 'escape_with_4_images_closes_dialog': page.locator('dialog.new-style[open]').count() == 0})
    a.capture(page, 'extract', 'after-escape', w, full_page=False)
    close_dialogs(page)


@flow
def rate(page, w):
    go(page, f'/b/{B1}')
    page.wait_for_timeout(800)
    a.capture(page, 'rate', '1-grid', w)
    a.capture(page, 'rate', '1-grid-fold', w, full_page=False)
    go(page, f'/b/{B1}/quiet-meadow-2', wait='dialog[open]')
    page.wait_for_timeout(700)
    a.capture(page, 'rate', '2-viewer', w, full_page=False)
    if w == 1440:
        extra['tab_walks']['viewer'] = a.tab_walk(page, 25)
    sel = 'dialog.viewer button.mark-btn.keep'
    a.time_it(page, f'thumbs-up click → button pressed, {w}px', lambda: click(page, sel),
              done_js=f'(() => {{ const b = document.querySelector("{sel}"); return b && (b.getAttribute("aria-pressed") === "true" || b.classList.contains("on") || b.classList.contains("active")); }})()', timeout=5)
    page.wait_for_timeout(300)
    a.capture(page, 'rate', '3-marked', w, full_page=False)
    click(page, sel)   # take it back: leave the copy as it was
    page.wait_for_timeout(400)
    page.keyboard.press('r')
    page.wait_for_selector('dialog:not(.viewer)[open]', timeout=8000)
    page.wait_for_timeout(500)
    a.capture(page, 'rate', '4-remix', w, full_page=False)
    close_dialogs(page)


@flow
def newrun(page, w):
    go(page, '/new?mode=batch')
    a.capture(page, 'newrun', '1-form', w)
    a.capture(page, 'newrun', '1-form-fold', w, full_page=False)
    click(page, 'button.style-chip:has-text("Quiet meadow")')
    page.wait_for_timeout(400)
    a.capture(page, 'newrun', '2-style-picked', w, full_page=False)
    a.time_it(page, f'Start → first feedback, {w}px', lambda: click(page, 'button.start:not([disabled])'),
              done_js='!document.getElementById("job-chip").hidden || !!document.querySelector("#toasts .toast")', timeout=10)
    page.wait_for_timeout(1500)
    a.capture(page, 'newrun', '3-started', w, full_page=False)
    page.request.post(f'{URL}/api/stop', data={})
    for q in (page.request.get(f'{URL}/api/job').json().get('queue') or []):
        page.request.post(f'{URL}/api/queue/cancel', data={'id': q['id']})


@flow
def sweep(page, w):
    for name, hash_ in (('overview', '/overview'), ('gallery', '/gallery'), ('styles', '/styles'),
                        ('taste', '/taste'), ('models', '/models'), ('guide', '/guide'), ('about', '/about')):
        go(page, hash_)
        page.wait_for_timeout(500)
        a.capture(page, 'page', name, w, full_page=False)


# ---------------------------------------------------------------- run

with sync_playwright() as p:
    browser = p.chromium.launch()
    for w, (vw, vh) in WIDTHS.items():
        ctx = browser.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=2,
                                  is_mobile=w < 768, has_touch=w < 768, color_scheme='dark')
        page = ctx.new_page()
        page.on('console', lambda m: extra['console'].append(f'{m.type}: {m.text}') if m.type == 'error' else None)
        for f in (land, land_empty, land_error, land_slow, extract, extract_errors, rate, newrun, sweep):
            print(f'{f.__name__} @ {w}', flush=True)
            f(page, w)
        ctx.close()
    browser.close()

a.save()
(OUT / 'raw' / 'extra.json').write_text(json.dumps(extra, indent=1), encoding='utf-8')
print('states', len(a.states), 'errors', len(extra['errors']))
for e in extra['errors']:
    print('  ', e.splitlines()[0].encode('ascii', 'replace').decode())
