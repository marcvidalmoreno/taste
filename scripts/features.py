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
