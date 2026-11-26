"""The main things Marc does in the app: mark, ignore, keep, note, history, start runs, pause, close popups.
Every run is a dry run (the app in the copy is started with --dry-run)."""
import time

from conftest import B1, B2, B3, B4, URL, api, assert_no_bad_text, go, post, ratings_rows


def wait_until(fn, what, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError(f'timed out waiting for: {what}')


def soft_api(page, path):
    """A read that may fail while the server swaps the file in (a known race, see README "Regression check")."""
    r = page.request.get(f'{URL}/api/{path}')
    return r.json() if r.ok else {}


def quiet(page):
    """Leave nothing queued or running so the next test starts clean."""
    for _ in range(3):
        job = api(page, 'job')
        for q in job.get('queue') or []:
            post(page, 'queue/cancel', {'id': q['id']})
        if job.get('running'):
            post(page, 'stop', {})
        if job.get('hold'):
            post(page, 'queue/resume', {})
        time.sleep(0.4)


def queued_titles(page):
    j = api(page, 'job')
    now = [j.get('title') or ''] if j.get('running') else []
    return now + [q.get('title') or '' for q in j.get('queue') or []] + [r.get('title') or '' for r in j.get('recent') or []]


def item(page, batch, name):
    return next(i for i in api(page, f'batch/{batch}')['items'] if i['name'] == name)


# ---------------------------------------------------------------- marks, ignore, keep, note, history

def test_mark_up_down_and_take_back(page, watch):
    go(page, f'/b/{B1}/quiet-meadow-3')
    page.wait_for_selector('dialog[open]')
    n0 = len(ratings_rows())
    page.keyboard.press('u')
    wait_until(lambda: len(ratings_rows()) == n0 + 1 and ratings_rows()[-1]['rating'] == 'keep', 'a "keep" row in ratings.csv')
    page.keyboard.press('u')   # the same thumb again takes it back
    wait_until(lambda: len(ratings_rows()) == n0 + 2 and ratings_rows()[-1]['rating'] == 'cleared', 'a "cleared" row')
    page.keyboard.press('d')
    wait_until(lambda: len(ratings_rows()) == n0 + 3 and ratings_rows()[-1]['rating'] == 'no', 'a "no" row')
    page.keyboard.press('d')
    wait_until(lambda: len(ratings_rows()) == n0 + 4 and ratings_rows()[-1]['rating'] == 'cleared', 'a second "cleared" row')
    assert ratings_rows()[-1]['name'] == 'quiet-meadow-3'
    watch.assert_clean('marks')


def test_mark_with_the_thumb_button(page, watch):
    go(page, f'/b/{B1}/quiet-meadow-4')
    page.wait_for_selector('dialog[open]')
    n0 = len(ratings_rows())
    page.click('dialog.viewer button.mark-btn.keep')
    wait_until(lambda: len(ratings_rows()) == n0 + 1, 'a row from the thumb button')
    page.click('dialog.viewer button.mark-btn.keep')   # take back
    wait_until(lambda: ratings_rows()[-1]['rating'] == 'cleared', 'taken back')
    watch.assert_clean('thumb button')


def test_ignore_and_undo(page, watch):
    go(page, f'/b/{B4}/old-test-style-2')
    page.wait_for_selector('dialog[open]')
    page.click('dialog.viewer button:has-text("Ignore")')
    wait_until(lambda: item(page, B4, 'old-test-style-2')['status'] == 'ignored', 'the image to be ignored')
    page.click('#toasts button:has-text("Undo")')
    wait_until(lambda: item(page, B4, 'old-test-style-2')['status'] != 'ignored', 'Undo to restore it')
    watch.assert_clean('ignore')


def test_keep_as_example(page, watch):
    go(page, f'/b/{B2}/paper-lanterns-1')
    page.wait_for_selector('dialog[open]')
    page.click('dialog.viewer button.keep-btn')
    wait_until(lambda: item(page, B2, 'paper-lanterns-1').get('kept'), 'the image to be kept')
    page.click('dialog.viewer button.keep-btn')
    wait_until(lambda: not item(page, B2, 'paper-lanterns-1').get('kept'), 'the image to be unkept')
    watch.assert_clean('keep')


def test_leave_a_note(page, watch):
    go(page, f'/b/{B1}/quiet-meadow-4')
    page.wait_for_selector('dialog[open]')
    page.click('dialog.viewer button:has-text("Note for Claude")')
    page.fill('dialog.note-dialog textarea', 'e2e check: a note about this image')
    page.click('dialog.note-dialog button:has-text("Leave the note")')
    wait_until(lambda: any('e2e check' in n['text'] for n in soft_api(page, 'notes').get('notes', [])), 'the note to be saved')
    watch.assert_clean('note')


def test_how_it_got_here(page, watch):
    go(page, f'/b/{B3}/tin-harbour-1')
    page.wait_for_selector('dialog[open] section.lineage')
    text = page.inner_text('dialog[open] section.lineage')
    assert 'How it got here' in text and '1 step' in text, text
    assert_no_bad_text(page, 'history')
    watch.assert_clean('history')


# ---------------------------------------------------------------- popups

def open_note(page):
    go(page, f'/b/{B1}/quiet-meadow-4')
    page.wait_for_selector('dialog[open]')
    page.click('dialog.viewer button:has-text("Note for Claude")')
    page.wait_for_selector('dialog.note-dialog[open]')


def test_popup_closes_with_its_cross(page, watch):
    open_note(page)
    page.click('dialog.note-dialog .dlg-x')
    assert not page.locator('dialog.note-dialog[open]').count()


def test_popup_closes_with_esc(page, watch):
    open_note(page)
    page.keyboard.press('Escape')
    assert not page.locator('dialog.note-dialog[open]').count()


def test_popup_closes_with_a_click_outside(page, watch):
    open_note(page)
    page.mouse.click(5, 5)
    assert not page.locator('dialog.note-dialog[open]').count()


def test_popup_stays_open_when_text_was_typed(page, watch):
    open_note(page)
    page.fill('dialog.note-dialog textarea', 'half a thought')
    page.mouse.click(5, 5)
    assert page.locator('dialog.note-dialog[open]').count() == 1
    assert 'Kept open' in page.inner_text('#toasts')
    page.click('dialog.note-dialog .dlg-x')   # on purpose
    assert not page.locator('dialog.note-dialog[open]').count()
    watch.assert_clean('popups')


# ---------------------------------------------------------------- runs (all dry runs)

def test_new_run_batch_queues_a_dry_run(page, watch):
    go(page, '/new?mode=batch')
    page.click('button.style-chip:has-text("Quiet meadow")')
    page.click('button.start:not([disabled])')
    wait_until(lambda: any('Quiet meadow' in t for t in queued_titles(page)), 'the run to be queued')
    watch.assert_clean('new run (batch)')
    quiet(page)


def test_new_run_one_image_queues_a_dry_run(page, watch):
    go(page, '/new?mode=one')
    page.fill('textarea[aria-label="Subject"]', 'a small boat in fog')
    page.click('button.start:not([disabled])')
    wait_until(lambda: any(queued_titles(page)), 'the run to be queued')
    watch.assert_clean('new run (one)')
    quiet(page)


def test_new_run_without_a_style_uses_a_palette(page, watch):
    go(page, '/new?mode=one')
    page.select_option('select[aria-label="Style"]', label='No style · palette only')
    page.wait_for_selector('text=No style rules')
    assert_no_bad_text(page, 'palette only')
    watch.assert_clean('palette only')


def test_new_run_with_two_models_queues_one_batch_each(page, watch):
    page.add_init_script("localStorage.setItem('taste-model', 'codex'); localStorage.setItem('taste-models-more', JSON.stringify(['klein']));")
    go(page, '/new?mode=batch')
    page.click('button.style-chip:has-text("Tin harbour")')
    assert 'Made with 2 models' in page.inner_text('#view'), page.inner_text('#view')[-600:]
    page.click('button.start:not([disabled])')
    wait_until(lambda: sum('Tin harbour' in t for t in queued_titles(page)) >= 2, 'one run per model')
    watch.assert_clean('two models')
    quiet(page)


def test_remix_queues_a_dry_run(page, watch):
    go(page, f'/b/{B1}/quiet-meadow-4')
    page.wait_for_selector('dialog[open]')
    page.keyboard.press('r')
    page.wait_for_selector('dialog:not(.viewer)[open] button.make')
    page.click('dialog:not(.viewer)[open] button.rx-chip:has-text("Palette")')
    page.click('dialog:not(.viewer)[open] button.make')
    wait_until(lambda: any(queued_titles(page)), 'the remix to be queued')
    watch.assert_clean('remix')
    quiet(page)


def test_pause_resume_and_stop(page, watch):
    for i in range(5):
        status, body = post(page, 'run', {'kind': 'batch', 'styles': ['quiet-meadow'], 'n': 4, 'ratio': 'mixed', 'model': 'codex', 'name': f'pause-{i}'})
        assert status == 200, body
    go(page, '/')
    wait_until(lambda: api(page, 'job').get('running') and len(api(page, 'job')['queue']) >= 1, 'a run going with others waiting')
    page.click('#job-chip button.chip-log')   # the Log popup holds Pause, Stop and the queue
    page.click('dialog[open] button:text-is("Pause")')
    wait_until(lambda: (api(page, 'job').get('hold') or {}).get('paused'), 'the queue to wait (paused)', timeout=60)
    assert len(api(page, 'job')['queue']) >= 1
    page.click('dialog[open] button:text-is("Resume")')
    wait_until(lambda: not api(page, 'job').get('hold'), 'Resume to lift the hold')
    wait_until(lambda: api(page, 'job').get('running'), 'the queue to go on')
    page.click('dialog[open] button:text-is("Stop")')   # confirm() is accepted by the watch fixture
    wait_until(lambda: not api(page, 'job').get('running') or api(page, 'job').get('stopped'), 'Stop to end the run')
    watch.assert_clean('pause')
    quiet(page)
