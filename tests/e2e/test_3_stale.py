"""State left behind by an earlier version or by something that was renamed, deleted or archived: the page must still draw."""
import json
import sys

from conftest import COPY, assert_no_bad_text, go

GHOSTS = """
try {
sessionStorage.setItem('taste-newrun', JSON.stringify({mode: 'batch', styles: ['ghost-style', 'quiet-meadow'], n: 4,
  one: {style: 'ghost-style', subject: '', ratio: 'wide', n: 1, palOnly: false, palette: [], palFrom: 'ghost-style'}}));
localStorage.setItem('taste-model', 'ghost-model');
localStorage.setItem('taste-models-more', JSON.stringify(['gone-model', 'klein']));
localStorage.setItem('taste-gallery-size', 'huge');
sessionStorage.setItem('taste-batches', '{"kind":"gone","q":"zzz","todo":true}');
} catch (e) {}   // about:blank has no storage
"""


def test_new_run_draws_when_it_names_a_style_that_no_longer_exists(page, watch):   # commit f8394c4
    page.add_init_script(GHOSTS)
    for mode in ('batch', 'one'):
        go(page, f'/new?mode={mode}', wait='#view h1')
        page.wait_for_selector('#view h1:has-text("New run")')
        assert page.locator('button.style-chip, select[aria-label="Style"]').count() >= 1, mode
        assert 'ghost-style' not in page.inner_text('#view'), mode
        assert_no_bad_text(page, f'new run {mode}')
    watch.assert_clean('stale style')


def test_pages_draw_when_the_saved_model_no_longer_exists(page, watch):
    page.add_init_script(GHOSTS)
    for address in ('/models', '/new?mode=batch', '/', '/gallery'):
        page.goto('about:blank')
        go(page, address)
        assert_no_bad_text(page, address)
    watch.assert_clean('stale model')


def test_an_archived_style_still_works_as_the_example_for_a_new_style():   # commit cde4777
    sys.path.insert(0, str(COPY / 'scripts'))
    try:
        import codex_text
        assert codex_text.ROOT.resolve() == COPY.resolve(), 'the check must read the copy, not the real folders'
        assert codex_text.example_style('old-test-style')['name'] == 'Old test style'   # only in taste/styles/archived/
        assert codex_text.example_style('no-such-style')['name']   # falls back to any style
    finally:
        sys.path.remove(str(COPY / 'scripts'))


def test_an_empty_batch_list_draws_a_calm_page(page, watch):
    page.route('**/api/batches', lambda r: r.fulfill(json={'batches': []}))
    go(page, '/', wait='#view h1')
    page.wait_for_timeout(500)
    assert page.locator('#view h1').inner_text().strip() == 'Batches'
    assert_no_bad_text(page, 'empty list')
    watch.assert_clean('empty batch list')
