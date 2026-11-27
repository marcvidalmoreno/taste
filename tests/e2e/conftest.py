"""Shared helpers for the regression check. scripts/e2e.py sets TASTE_E2E_URL (the app in the throwaway copy) and
TASTE_E2E_COPY (the copy's folder). Tests never touch anything outside that folder."""
import csv, json, os, re
from pathlib import Path
from urllib.parse import urlparse

import pytest

URL = os.environ.get('TASTE_E2E_URL', '')
COPY = Path(os.environ.get('TASTE_E2E_COPY', '.'))
BASE = COPY / 'generated' / 'codex'
B1, B2, B3, B4 = ('2026-01-01-quiet-meadow', '2026-01-02-paper-lanterns-flux', '2026-01-03-tin-harbour-klein', '2026-01-04-old-test-style')
BAD_TEXT = ('undefined', 'NaN', '[object Object]')
OUT = Path(os.environ['TASTE_E2E_OUT']) if os.environ.get('TASTE_E2E_OUT') else None

# Write requests the tests sent (27 Nov 2026): 'POST api/keep' -> first test that sent it. test_9_coverage.py checks
# them against tests/e2e/coverage.json; e2e.py's run folder gets hits.json.
HITS, CURRENT = {}, ['']


def hit(method, url):
    path = urlparse(url).path.strip('/')
    if method != 'GET' and path.startswith('api/'):
        HITS.setdefault(f'{method} {path}', CURRENT[0])


@pytest.fixture(scope='session')
def base_url():
    assert URL, 'run this through scripts/e2e.py (it starts the app in a copy and sets TASTE_E2E_URL)'
    return URL


@pytest.fixture(scope='session')
def browser_context_args(browser_context_args):
    return {**browser_context_args, 'viewport': {'width': 1280, 'height': 800}}


class Watch:
    """What went wrong on the page: console errors, uncaught errors, failed or refused /api and image requests."""
    def __init__(self, page):
        self.problems = []
        page.on('request', lambda r: hit(r.method, r.url))
        page.on('console', lambda m: self.problems.append(f'console {m.type}: {m.text}') if m.type == 'error' and 'favicon' not in m.text and 'Failed to load resource' not in m.text else None)
        page.on('pageerror', lambda e: self.problems.append(f'uncaught: {e}'))
        page.on('requestfailed', lambda r: self.problems.append(f'request failed: {r.url}') if '/api/' in r.url or '/img/' in r.url or '/thumb/' in r.url else None)
        page.on('response', lambda r: self.problems.append(f'HTTP {r.status}: {r.url}') if r.status >= 400 and 'favicon' not in r.url and (self.strict or '/img/' in r.url or '/thumb/' in r.url) else None)
    strict = True

    def clear(self):
        self.problems.clear()

    def assert_clean(self, where=''):
        assert not self.problems, f'{where}: ' + '; '.join(self.problems[:5])


@pytest.fixture
def watch(page):
    page.on('dialog', lambda d: d.accept())   # confirm() on Stop
    return Watch(page)


def api(page, path):
    r = page.request.get(f'{URL}/api/{path}')
    assert r.ok, f'GET /api/{path} -> {r.status}'
    return r.json()


def post(page, path, body):
    hit('POST', f'{URL}/api/{path}')
    r = page.request.post(f'{URL}/api/{path}', data=json.dumps(body), headers={'Content-Type': 'application/json', 'X-Taste-App': '1'})
    return r.status, (r.json() if r.ok else r.text())


def go(page, hash_, wait='#view > *'):
    """Open an address inside the app and wait until something is drawn into #view."""
    page.goto(f'{URL}/#{hash_.lstrip("#")}')
    page.wait_for_selector(wait, timeout=15000)
    page.wait_for_function("() => !document.querySelector('#view [aria-busy=true]')", timeout=15000)
    page.wait_for_timeout(150)   # lets the first images and requests start (a failed one is caught by Watch)


def screen_text(page):
    return page.evaluate('document.body.innerText')


def assert_no_bad_text(page, where=''):
    text = screen_text(page)
    for bad in BAD_TEXT:
        assert not re.search(rf'(?<![A-Za-z]){re.escape(bad)}(?![A-Za-z])', text), f'{where}: "{bad}" on screen'


def ratings_rows():
    f = BASE / 'ratings.csv'
    return list(csv.DictReader(open(f, encoding='utf-8'))) if f.exists() else []


# If the smoke test fails the page does not load: skip the rest instead of waiting out a timeout in each.
SMOKE_FAILED = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    if report.when == 'call' and report.failed and item.module.__name__.endswith('test_0_smoke'):
        SMOKE_FAILED.append(item.name)


@pytest.fixture(autouse=True)
def _skip_when_the_page_does_not_load(request):
    if SMOKE_FAILED and not request.module.__name__.endswith('test_0_smoke') and request.node.name != 'test_every_route_has_a_test':
        pytest.skip('the app does not load (see test_the_app_loads)')


@pytest.fixture(autouse=True)
def _name_the_test(request):
    CURRENT[0] = request.node.originalname or request.node.name


def pytest_sessionfinish(session):
    if OUT and OUT.is_dir():
        (OUT / 'hits.json').write_text(json.dumps(HITS, indent=1, sort_keys=True), encoding='utf-8')
