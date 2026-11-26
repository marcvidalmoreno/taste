"""Every route opens: nothing in the console, no refused request, no "undefined" / "NaN" / "[object Object]" on screen.
The route guard reads the keys of the `pages` map in app/js/main.js: a page added there without a test here fails."""
import re

import pytest

from conftest import B1, B3, COPY, assert_no_bad_text, go

# route key in main.js -> addresses that open it (the default page, the batch list, has no key)
PAGES = {
    '': ['/'],
    'b': [f'/b/{B1}', f'/b/{B1}?show=rated', f'/b/{B1}/quiet-meadow-3', f'/b/{B3}/tin-harbour-1'],
    'overview': ['/overview'],
    'distil': ['/distil'],
    'suggestions': ['/suggestions'],
    'gallery': ['/gallery', f'/gallery/{B1}/quiet-meadow-3'],
    'styles': ['/styles', '/styles/quiet-meadow'],
    'taste': ['/taste', '/taste/quiet-meadow'],
    'models': ['/models', '/models/quiet-meadow'],
    'guide': ['/guide', '/guide/models'],
    'about': ['/about'],
    'new': ['/new?mode=batch', '/new?mode=one'],
}
ADDRESSES = [a for lst in PAGES.values() for a in lst]


def route_keys():
    src = (COPY / 'app' / 'js' / 'main.js').read_text(encoding='utf-8')
    m = re.search(r'const pages = \{(.*?)\}', src, re.S)
    assert m, 'no `const pages = {...}` map in app/js/main.js: the route guard cannot read the routes'
    return set(re.findall(r'(\w+)\s*:', m.group(1)))


def test_every_route_has_a_test():
    missing = sorted(route_keys() - set(PAGES))
    assert not missing, f'route without a test: {", ".join(missing)} (add it to PAGES in tests/e2e/test_1_pages.py)'


@pytest.mark.parametrize('address', ADDRESSES)
def test_page_opens(page, watch, address):
    go(page, address)
    if address.startswith('/gallery/') or re.match(r'/b/[^/?]+/[^/?]+', address):
        page.wait_for_selector('dialog[open]')
    page.wait_for_timeout(150)
    assert_no_bad_text(page, address)
    watch.assert_clean(address)
