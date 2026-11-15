"""Colour/composition features shared by clustering and the inbox (same recipe as build/cluster.py)."""
import numpy as np
from PIL import Image
from matplotlib.colors import rgb_to_hsv

Image.MAX_IMAGE_PIXELS = 300_000_000


def thumb64(path):
    """Open an image and return (64x64 RGB array, width, height, 128px thumbnail)."""
    im = Image.open(path)
    w, h = im.size
    im.draft('RGB', (256, 256))
    im = im.convert('RGB')
    t = im.copy()
    t.thumbnail((128, 128))
    return np.asarray(t.resize((64, 64))), w, h, t


def features(a64, w, h):
    a = a64 / 255.
    hsv = rgb_to_hsv(a)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    hist = np.zeros(12)
    for b in range(12):
        hist[b] = (((H * 12).astype(int) % 12 == b) * S * V).sum()
    hist /= hist.sum() + 1e-6
    g = V.reshape(4, 16, 4, 16).mean((1, 3)).ravel()
    gy, gx = np.gradient(V)
    edge = np.hypot(gx, gy).mean()
    ar = w / h
    return np.r_[V.mean(), V.std(), S.mean(), S.std(), hist * 1.5, g * 0.7, edge * 5,
                 min(ar, 2.5) * 0.5, (S < 0.12).mean()]


def palette(thumbs):
    """Measured palette for a list of 64x64 RGB arrays: 5 base colours (k-means, dark to light) + up to 2 accents
    (k-means on saturated, bright pixels only). Same recipe as build/restyle.py and build/collection_styles.py."""
    from sklearn.cluster import KMeans
    px = np.concatenate([t[::4, ::4].reshape(-1, 3) for t in thumbs]).astype(float)
    lum = lambda c: c @ [0.299, 0.587, 0.114]
    base = sorted(KMeans(5, n_init=4, random_state=0).fit(px).cluster_centers_, key=lum)
    sat = (px.max(1) - px.min(1)) / (px.max(1) + 1e-6)
    vivid = px[(sat > 0.55) & (px.max(1) > 110)]
    acc = KMeans(2, n_init=4, random_state=0).fit(vivid).cluster_centers_ if len(vivid) > 50 else []
    return ['#%02x%02x%02x' % tuple(int(v) for v in c) for c in list(base) + list(acc)]
