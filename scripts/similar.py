"""Images that look like one image, by colour and composition (21 Nov 2026). Free: no Codex, no images spent.

Same number recipe as nearest.py (scripts/features.py): per image 35 numbers, measured once from its thumbnail and
cached in generated/codex/.look-index.json (safe to delete: it is rebuilt). The numbers are standardised over all
images, then the colour group (brightness, saturation, hue mix) and the composition group (4x4 brightness grid, edges,
shape) count equally. It sees colour and framing, never the subject.

Used by scripts/app.py (GET /api/similar). Command line: .venv/Scripts/python -I scripts/similar.py <batch> <name>
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import numpy as np
except ModuleNotFoundError:   # started with a Python outside the project .venv: borrow its packages
    sys.path.append(str(ROOT / '.venv' / 'Lib' / 'site-packages'))
    import numpy as np

COLOUR = list(range(0, 16)) + [34]       # brightness and saturation stats, hue mix, share of grey
LAYOUT = list(range(16, 34))             # 4x4 brightness grid, edge amount, aspect ratio


def measure(thumb_path):
    """The 35 numbers of one image, from its (already small) thumbnail file."""
    from PIL import Image
    from features import features
    im = Image.open(thumb_path)
    w, h = im.size
    im.draft('RGB', (256, 256))
    a = np.asarray(im.convert('RGB').resize((64, 64)))
    return [float(x) for x in features(a, w, h)]


def load_index(cache):
    try:
        return json.load(open(cache, encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update_index(cache, items):
    """items: [(key, thumb_path, mtime)]. Measures the ones not in the cache (or changed), saves, returns {key: vector}."""
    index = load_index(cache)
    todo = [(k, p, m) for k, p, m in items if index.get(k, [None])[0] != m]
    for k, p, m in todo:
        try:
            index[k] = [m, measure(p)]
        except Exception:   # a broken file: leave it out rather than fail the row
            index.pop(k, None)
    live = {k for k, _, _ in items}
    if todo or any(k not in live for k in index):
        index = {k: v for k, v in index.items() if k in live}
        tmp = Path(str(cache) + '.tmp')
        json.dump(index, open(tmp, 'w', encoding='utf-8'))
        os.replace(tmp, cache)
    return {k: v[1] for k, v in index.items()}


def nearest(vectors, key, count=8, allowed=None):
    """[(key, distance)] of the images closest to `key`, best first. allowed: only these keys, if given."""
    keys = list(vectors)
    if key not in vectors:
        return []
    X = np.array([vectors[k] for k in keys])
    sd = X.std(0)
    Z = (X - X.mean(0)) / np.where(sd < 1e-9, 1, sd)
    w = np.zeros(X.shape[1])
    w[COLOUR] = 1 / np.sqrt(len(COLOUR))
    w[LAYOUT] = 1 / np.sqrt(len(LAYOUT))
    i = keys.index(key)
    d = np.linalg.norm((Z - Z[i]) * w, axis=1)
    out = [(keys[j], float(d[j])) for j in np.argsort(d) if j != i and (allowed is None or keys[j] in allowed)]
    return out[:count]
