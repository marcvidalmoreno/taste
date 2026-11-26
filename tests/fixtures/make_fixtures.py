"""Fake data for the regression check (scripts/e2e.py): invented styles, plain coloured pictures, runs and ratings.

Nothing here is copied from Marc's real styles, images or ratings (the repo is public).
  build(root)  fills <root>/taste/styles, <root>/generated/codex and runs scripts/build_taste.py inside <root>.
"""
import csv, json, subprocess, sys
from pathlib import Path

from PIL import Image, ImageDraw

STYLES = {
    'quiet-meadow': ('Quiet meadow', ['#2b3a2f', '#6b8f5e', '#c9d8a6']),
    'paper-lanterns': ('Paper lanterns', ['#2a1b2e', '#a8456b', '#f2c879']),
    'tin-harbour': ('Tin harbour', ['#1d2b36', '#5a7d92', '#d6dde2']),
}
ARCHIVED = {'old-test-style': ('Old test style', ['#222222', '#777777', '#dddddd'])}

# batch folder -> (style, route, session, n images, colour seed, with a seed picture)
BATCHES = {
    '2026-01-01-quiet-meadow': ('quiet-meadow', 'codex', 'fake-session-1', 4, 10, False),
    '2026-01-02-paper-lanterns-flux': ('paper-lanterns', 'cloudflare', 'cloudflare', 4, 80, False),
    '2026-01-03-tin-harbour-klein': ('tin-harbour', 'local', 'local:klein', 3, 150, True),
    '2026-01-04-old-test-style': ('old-test-style', 'codex', 'fake-session-2', 2, 200, False),
}
RUNS_HEADER = ['date', 'time', 'batch', 'name', 'mode', 'style', 'change', 'seed', 'ok', 'width', 'height', 'tokens',
               'five_hour_first', 'five_hour_last', 'weekly_first', 'weekly_last', 'seconds', 'session', 'prompt', 'route']
RATINGS_HEADER = ['date', 'batch', 'number', 'name', 'style', 'mode', 'change', 'rating', 'why', 'prompt']


def style_json(name, palette):
    return {
        'name': name,
        'description': f'{name}: a calm invented test style with soft shapes and plenty of empty space.',
        'palette': palette,
        'light': ['soft even daylight', 'low warm evening light'],
        'composition': ['one small shape low in the frame', 'a wide empty field with a single mark'],
        'camera_or_medium': 'plain gouache on paper',
        'mood': ['quiet', 'patient'],
        'texture_detail': ['fine paper grain', 'smooth flat fills'],
        'avoid': ['text', 'logos', 'busy detail'],
        'subjects': [f'{name} at dawn', f'{name} in rain', f'{name} at night'],
        'use': ['test fixture'],
    }


def picture(path, seed, i, size=(320, 180)):
    r, g, b = (seed * 7 + i * 53) % 200 + 30, (seed * 3 + i * 91) % 200 + 30, (seed * 11 + i * 29) % 200 + 30
    im = Image.new('RGB', size, (r, g, b))
    d = ImageDraw.Draw(im)
    d.ellipse((size[0] // 3, size[1] // 3, size[0] // 3 * 2, size[1] // 3 * 2), fill=(255 - r, 255 - g, 255 - b))
    im.save(path)


def build(root):
    root = Path(root)
    styles = root / 'taste' / 'styles'
    (styles / 'archived').mkdir(parents=True, exist_ok=True)
    for k, (n, p) in STYLES.items():
        (styles / f'{k}.json').write_text(json.dumps(style_json(n, p), indent=1), encoding='utf-8')
    for k, (n, p) in ARCHIVED.items():
        (styles / 'archived' / f'{k}.json').write_text(json.dumps(style_json(n, p), indent=1), encoding='utf-8')
    subprocess.run([sys.executable, '-I', str(root / 'scripts' / 'build_taste.py'), str(root)], check=True,
                   capture_output=True)

    base = root / 'generated' / 'codex'
    base.mkdir(parents=True, exist_ok=True)
    rows = []
    for batch, (style, route, session, n, seed, has_seed) in BATCHES.items():
        folder = base / batch
        folder.mkdir(exist_ok=True)
        if has_seed:
            picture(folder / 'seed.png', seed, 99)
        for i in range(1, n + 1):
            picture(folder / f'{style}-{i}.png', seed, i)
            rows.append(['2026-01-0' + batch[9], '10:0' + str(i), batch, f'{style}-{i}', 'batch', style, '', 'seed.png' if has_seed else '', 'yes',
                         320, 180, 0, '', '', '', '', 12 + i, session, f'Fake prompt {i} for {style}.', route])
        (folder / 'run.json').write_text(json.dumps({
            'kind': 'batch', 'title': f'{style.replace("-", " ").title()} · test', 'styles': [style], 'n': n,
            'route': route, 'started': '2026-01-01 10:00', 'by': 'web app'}), encoding='utf-8')
    with open(base / 'runs.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(RUNS_HEADER)
        w.writerows(rows)
    b1 = '2026-01-01-quiet-meadow'
    with open(base / 'ratings.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(RATINGS_HEADER)
        w.writerow(['2026-01-02', b1, 1, 'quiet-meadow-1', 'quiet-meadow', 'batch', '', 'keep', 'calm', 'Fake prompt 1'])
        w.writerow(['2026-01-02', b1, 2, 'quiet-meadow-2', 'quiet-meadow', 'batch', '', 'no', 'too busy', 'Fake prompt 2'])
    return root


if __name__ == '__main__':
    print(build(sys.argv[1]))
