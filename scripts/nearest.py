"""Closest styles for an image, by colour and composition. A hint only.

The 14 styles (13 Nov 2026) were defined by eye (subject, medium, mood), which pixel statistics can't see:
over the 999 tagged wallpapers this guess is right 36 % of the time as first choice and 63 % within the top 3.
So callers show the top 3 and Claude (looking at the image) or Marc picks the style.
Style members come from taste/data/style_members.json (scripts/build/restyle.py).

Usage: .venv/Scripts/python -I scripts/nearest.py <project-root> <image> [<image> ...]
"""
import sys, os, json
import numpy as np


def model(root):
    """Return guess(path) -> [(style, distance), ...] best first, plus far_from_all flag."""
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    sys.path.insert(0, os.path.join(root, 'scripts'))
    from features import thumb64, features
    data = os.path.join(root, 'taste', 'data')
    rows = {r['idx']: r for r in json.load(open(os.path.join(data, 'clusters_k5.json')))}
    members = json.load(open(os.path.join(data, 'style_members.json')))
    T = np.load(os.path.join(data, 'thumbs64.npy'))
    idx = [i for m in members.values() for i in m]
    lab = np.array([s for s, m in members.items() for _ in m])
    F = np.array([features(T[i], rows[i]['w'], rows[i]['h']) for i in idx])
    sc = StandardScaler().fit(F)
    pca = PCA(12, random_state=0).fit(sc.transform(F))
    X = pca.transform(sc.transform(F))
    cent = {s: X[lab == s].mean(0) for s in members}
    limit = {s: np.percentile(np.linalg.norm(X[lab == s] - cent[s], axis=1), 90) for s in members}

    def score(a, w, h):
        """Top 3 for a 64x64 thumbnail array, plus distance / the best style's 90th percentile (<= 1: inside)."""
        x = pca.transform(sc.transform([features(a, w, h)]))[0]
        d = sorted(((s, round(float(np.linalg.norm(x - c)), 2)) for s, c in cent.items()), key=lambda t: t[1])
        return d[:3], d[0][1] / limit[d[0][0]]

    def guess(path):
        a, w, h, thumb = thumb64(path)
        top, ratio = score(a, w, h)
        return top, bool(ratio > 1), thumb
    guess.score = score
    return guess


if __name__ == '__main__':
    g = model(sys.argv[1])
    for p in sys.argv[2:]:
        top, far, _ = g(p)
        print(os.path.basename(p), '->', ', '.join(s for s, _ in top), '(far from all)' if far else '')
