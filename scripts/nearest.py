"""Closest sub-style for an image (same colour/composition model as inbox.py).

Usage: .venv/Scripts/python -I scripts/nearest.py <project-root> <image>
"""
import sys, os, json
import numpy as np

NAMES = {0: 'neon-dusk', 1: 'deep-space-dark', 2: 'warm-interiors-japan',
         3: 'bright-airy-minimal', 4: 'retro-sci-fi-painting'}


def nearest_style(root, path):
    """Return (style, distance, far_from_all) for one image."""
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    sys.path.insert(0, os.path.join(root, 'scripts'))
    from features import thumb64, features
    data = os.path.join(root, 'taste', 'data')
    rows = json.load(open(os.path.join(data, 'clusters_k5.json')))
    T = np.load(os.path.join(data, 'thumbs64.npy'))
    F = np.array([features(T[r['idx']], r['w'], r['h']) for r in rows])
    sc = StandardScaler().fit(F)
    pca = PCA(12, random_state=0).fit(sc.transform(F))
    X = pca.transform(sc.transform(F))
    labels = np.array([r['cluster'] for r in rows])
    a, w, h, _ = thumb64(path)
    x = pca.transform(sc.transform([features(a, w, h)]))[0]
    d = {c: float(np.linalg.norm(x - X[labels == c].mean(0))) for c in NAMES}
    c = min(d, key=d.get)
    limit = np.percentile(np.linalg.norm(X[labels == c] - X[labels == c].mean(0), axis=1), 90)
    return NAMES[c], round(d[c], 2), bool(d[c] > limit)


if __name__ == '__main__':
    print(nearest_style(sys.argv[1], sys.argv[2]))
