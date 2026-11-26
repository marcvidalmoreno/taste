"""The chip in the top bar that says the regression check found a break (it reads GET /api/e2e)."""
import json

from conftest import COPY, api, go

LAST = COPY / 'generated' / 'e2e' / 'last.json'


def test_chip_shows_while_the_last_check_fails_and_leaves_when_it_passes(page, watch):
    LAST.parent.mkdir(parents=True, exist_ok=True)
    try:
        LAST.write_text(json.dumps({'status': 'fail', 'sha': 'abc1234', 'failing': [{'test': 'x', 'why': 'y'}]}), encoding='utf-8')
        assert api(page, 'e2e') == {'failing': True, 'sha': 'abc1234', 'tests': 1}
        go(page, '/')
        page.wait_for_selector('#e2e-chip:not([hidden]) .e2e-chip')
        assert 'Regression found' in page.inner_text('#e2e-chip')
        LAST.write_text(json.dumps({'status': 'pass', 'sha': 'abc1235', 'failing': []}), encoding='utf-8')
        page.reload()
        page.wait_for_selector('#view > *')
        page.wait_for_timeout(500)
        assert page.locator('#e2e-chip').is_hidden()
        watch.assert_clean('chip')
    finally:
        LAST.unlink(missing_ok=True)
