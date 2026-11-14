"""Render a real fractal (Mandelbrot, Julia, Burning Ship) coloured with a taste style's palette. No Codex, no allowance.

Usage (from the project root):
  .venv/Scripts/python -I scripts/fractal.py --style psychedelic-dreams --kind mandelbrot --view seahorse --out generated/fractals/a.png
  --kind mandelbrot|julia|ship   --view <name> or cx,cy,zoom   --ratio wide|square|portrait   --iter 600
  --c -0.8,0.156 (julia constant)   --cycles 3 (colour bands)   --glow 0.6 (bloom on the edges)
Views: mandelbrot: full, seahorse, spiral, elephant; julia: default; ship: full, bay.
Palette: the style's colours sorted dark to light, dark ground first, looped smoothly.
"""
import argparse, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SIZES = {'wide': (1672, 941), 'square': (1254, 1254), 'portrait': (941, 1672)}
VIEWS = {
    'mandelbrot': {'full': (-0.6, 0.0, 1.0), 'seahorse': (-0.7453, 0.1127, 220.0),
                   'spiral': (-0.7616, -0.0848, 300.0), 'elephant': (0.2824, 0.0095, 90.0)},
    'julia': {'default': (0.0, 0.0, 1.0)},
    'ship': {'full': (-0.5, -0.5, 1.0), 'bay': (-1.7443, -0.0173, 60.0)},
}


def hex_rgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def gradient(palette, n=1024):
    cols = sorted((hex_rgb(h) for h in palette), key=lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])
    pts = np.array(cols + [cols[0]], float)            # loop back to the dark ground
    xs = np.linspace(0, len(pts) - 1, n)
    return np.stack([np.interp(xs, range(len(pts)), pts[:, k]) for k in range(3)], 1)


def escape(kind, w, h, cx, cy, zoom, c, max_iter):
    span = 3.0 / zoom
    xs = np.linspace(cx - span / 2 * w / h, cx + span / 2 * w / h, w)
    ys = np.linspace(cy - span / 2, cy + span / 2, h)
    P = xs[None, :] + 1j * ys[:, None]
    Z = P.copy() if kind == 'julia' else np.zeros_like(P)
    C = np.full_like(P, c) if kind == 'julia' else P
    out = np.zeros(P.shape)
    alive = np.ones(P.shape, bool)
    for i in range(max_iter):
        if kind == 'ship':
            Z[alive] = (np.abs(Z[alive].real) + 1j * np.abs(Z[alive].imag)) ** 2 + C[alive]
        else:
            Z[alive] = Z[alive] ** 2 + C[alive]
        gone = alive & (np.abs(Z) > 256)
        if gone.any():                                  # smooth iteration count: no colour banding
            out[gone] = i + 1 - np.log2(np.log(np.abs(Z[gone])))
            alive &= ~gone
        if not alive.any():
            break
    out[alive] = np.nan                                 # inside the set
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--style', required=True)
    a.add_argument('--kind', default='mandelbrot', choices=['mandelbrot', 'julia', 'ship'])
    a.add_argument('--view', default=None)
    a.add_argument('--ratio', default='wide', choices=list(SIZES))
    a.add_argument('--iter', type=int, default=600)
    a.add_argument('--c', default='-0.8,0.156')
    a.add_argument('--cycles', type=float, default=3.0)
    a.add_argument('--glow', type=float, default=0.6)
    a.add_argument('--out', required=True)
    a = a.parse_args()

    style = json.loads((ROOT / 'taste' / 'styles' / f'{a.style}.json').read_text(encoding='utf-8'))
    views = VIEWS[a.kind]
    v = a.view or next(iter(views))
    cx, cy, zoom = views[v] if v in views else (float(x) for x in v.split(','))
    w, h = SIZES[a.ratio]
    cr, ci = (float(x) for x in a.c.split(','))
    n = escape(a.kind, w, h, cx, cy, zoom, complex(cr, ci), a.iter)

    grad = gradient(style['palette'])
    inside = np.isnan(n)
    t = (np.log1p(np.nan_to_num(n)) * a.cycles / 3.0) % 1.0   # log: bands stay even from far out to the edge
    img = grad[(t * (len(grad) - 1)).astype(int)]
    img[inside] = grad[0]                               # the dark ground of the style
    im = Image.fromarray(img.astype(np.uint8))
    if a.glow > 0:                                      # self-luminous edges, as the style asks
        bloom = im.filter(ImageFilter.GaussianBlur(max(w, h) / 90))
        im = Image.fromarray(np.clip(np.asarray(im, float) + a.glow * np.asarray(bloom, float), 0, 255).astype(np.uint8))
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print(out)


if __name__ == '__main__':
    main()
