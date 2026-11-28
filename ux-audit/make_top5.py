"""Outlined screenshots for the top-5 findings (ux-audit/top5/), against the fake-data copy only.

    .venv/Scripts/python -I ux-audit/make_top5.py http://127.0.0.1:<port>
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path.home() / '.claude' / 'skills' / 'ux-audit' / 'scripts'))   # the global ux-audit skill
from capture_lib import outline   # noqa: E402
from playwright.sync_api import sync_playwright   # noqa: E402

URL = sys.argv[1].rstrip('/')
assert ':8791' not in URL, 'never the real app'
OUT = ROOT / 'ux-audit'
RAW = OUT / 'raw' / 'top5'
RAW.mkdir(parents=True, exist_ok=True)
IMG = OUT / '.tools' / 'test-images'
B1 = '2026-01-01-quiet-meadow'

BOX = """(sel) => [...document.querySelectorAll(sel)].map(e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }).filter(b => b[2] && b[3])"""


def union(boxes):
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


def go(page, hash_, wait='#view > *'):
    page.goto('about:blank')
    page.goto(f'{URL}/#{hash_}')
    page.wait_for_selector(wait, timeout=15000)
    page.wait_for_timeout(700)


def shoot(page, n, slug, boxes, fid):
    raw = RAW / f'{n:02d}-{slug}.png'
    page.screenshot(path=str(raw))
    outline(raw, boxes, OUT / 'top5' / f'{n:02d}-{slug}.png', tag=f'{n} · {fid}')
    print(n, slug, [list(map(round, b)) for b in boxes])


def open_new_style(page, files):
    go(page, '/taste')
    page.click('button:has-text("New style from images")')
    page.wait_for_selector('dialog.new-style[open]')
    page.set_input_files('dialog.new-style input[type=file]', [str(IMG / f) for f in files])
    page.wait_for_function(f'document.querySelectorAll("dialog.new-style .ref-tile img").length === {len(files)}')


with sync_playwright() as p:
    b = p.chromium.launch()
    # 01 · F-001: phone width, nav runs off-screen
    m = b.new_page(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    go(m, '/')
    nav = m.evaluate(BOX, '.topbar nav')[0]
    shoot(m, 1, 'phone-nav-overflow', [[nav[0], nav[1], min(nav[2], 390) - 8, nav[3]]], 'F-001')
    m.close()

    pg = b.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=2)
    # 02 · F-002: extraction error as a far toast
    open_new_style(pg, ['test-1.jpg', 'test-2.jpg', 'test-3.jpg'])
    pg.route('**/api/style/new/propose', lambda r: r.fulfill(status=502, content_type='application/json',
                                                             body='{"error": "codex: the model is busy, try again later"}'))
    pg.click('dialog.new-style footer button:not(.secondary)')
    pg.wait_for_selector('#toasts .toast')
    pg.wait_for_timeout(400)
    shoot(pg, 2, 'extract-error-toast', [pg.evaluate(BOX, '#toasts .toast')[0],
                                         pg.evaluate(BOX, 'dialog.new-style footer button:not(.secondary)')[0]], 'F-002')
    pg.unroute('**/api/style/new/propose')

    # 03 · F-004: rating buttons under 44 px
    go(pg, f'/b/{B1}')
    tiles = pg.evaluate("""() => [...document.querySelectorAll('.grid > li')].map(li => [...li.querySelectorAll('button.mark-btn, button')].map(e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height, r.height < 44]; }).filter(b => b[2] && b[4]))""")
    shoot(pg, 3, 'small-rating-targets', [union(t) for t in tiles if t][:8], 'F-004')

    # 04 · F-003: 30–60 s wait shown only in the button label
    open_new_style(pg, ['test-1.jpg', 'test-2.jpg', 'test-3.jpg'])
    held = []
    pg.route('**/api/style/new/propose', lambda r: held.append(r))
    pg.click('dialog.new-style footer button:not(.secondary)')
    pg.wait_for_timeout(12000)
    shoot(pg, 4, 'extract-wait-label-only', [pg.evaluate(BOX, 'dialog.new-style footer button[aria-busy=true]')[0]], 'F-003')
    held[0].continue_()
    pg.unroute('**/api/style/new/propose')

    # 05 · F-005: viewer panel, equal-weight actions
    go(pg, f'/b/{B1}/quiet-meadow-2', wait='dialog.viewer[open]')
    acts = pg.evaluate("""() => [...document.querySelectorAll('dialog.viewer button')].filter(e => /Up|Down|Why|Keep|Publish|Remix|Redo|Change the style|Note for Claude/.test(e.textContent) && e.getBoundingClientRect().width).map(e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })""")
    shoot(pg, 5, 'viewer-equal-weight-actions', [union(acts)], 'F-005')
    b.close()
