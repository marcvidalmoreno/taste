"""First: the page loads at all. When it does not (a broken module), every other browser test would only wait out its
timeout and say the same thing, so conftest.py skips them and this one names the break."""
from conftest import go


def test_the_app_loads(page, watch):
    go(page, '/', wait='#view h1')
    assert page.locator('#view h1').inner_text().strip() == 'Batches'
    assert page.locator('a[data-nav]').count() >= 8
    watch.assert_clean('start page')
