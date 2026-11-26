"""At 1920 and 768 px wide no page scrolls sideways."""
import pytest

from conftest import go
from test_1_pages import PAGES

ADDRESSES = [lst[0] for lst in PAGES.values()] + [PAGES['b'][2], PAGES['gallery'][1], '/new?mode=one']


@pytest.mark.parametrize('width,height', [(1920, 1080), (768, 1024)])
def test_no_sideways_scroll(page, watch, width, height):
    page.set_viewport_size({'width': width, 'height': height})
    wide = []
    for address in ADDRESSES:
        page.goto('about:blank')
        go(page, address)
        page.wait_for_timeout(150)
        over = page.evaluate('() => document.documentElement.scrollWidth - document.documentElement.clientWidth')
        if over > 1:
            wide.append(f'{address} (+{over} px)')
    assert not wide, f'scrolls sideways at {width} px: ' + ', '.join(wide)
    watch.assert_clean(f'width {width}')
