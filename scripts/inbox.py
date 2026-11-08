"""Sort new images from inbox/ into the closest sub-style.

Usage: .venv/Scripts/python -I scripts/inbox.py <project-root>
- Moves each inbox image to taste/data/added/<style>/ (kept out of git: not Marc's images).
- Flags images far from every style as "new style?".
- Writes a contact sheet taste/data/contact-sheets/inbox-<date>.jpg and appends to taste/data/added.json.
Afterwards Claude looks at the sheet and updates taste/styles/<style>.json by hand.
"""
import sys, os, json, shutil, datetime
import numpy as np
from PIL import Image
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

root = sys.argv[1]
sys.path.insert(0, os.path.join(root, 'scripts'))
from features import thumb64, features  # noqa: E402

data = os.path.join(root, 'taste', 'data')
names = {0: 'neon-dusk', 1: 'deep-space-dark', 2: 'warm-interiors-japan',
         3: 'bright-airy-minimal', 4: 'retro-sci-fi-painting'}
EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.avif'}

rows = json.load(open(os.path.join(data, 'clusters_k5.json')))
T = np.load(os.path.join(data, 'thumbs64.npy'))
F = np.array([features(T[r['idx']], r['w'], r['h']) for r in rows])
sc = StandardScaler().fit(F)
pca = PCA(12, random_state=0).fit(sc.transform(F))
X = pca.transform(sc.transform(F))
labels = np.array([r['cluster'] for r in rows])
cent = {c: X[labels == c].mean(0) for c in names}
limit = {c: np.percentile(np.linalg.norm(X[labels == c] - cent[c], axis=1), 90) for c in names}

inbox = os.path.join(root, 'inbox')
files = [f for f in sorted(os.listdir(inbox)) if os.path.splitext(f)[1].lower() in EXTS]
if not files:
    print('inbox is empty'); sys.exit(0)

log_path = os.path.join(data, 'added.json')
log = json.load(open(log_path)) if os.path.exists(log_path) else []
today = datetime.date.today().isoformat()
sheet = Image.new('RGB', (4 * 220, ((len(files) + 3) // 4) * 160), (20, 20, 20))
for i, f in enumerate(files):
    p = os.path.join(inbox, f)
    try:
        a, w, h, t = thumb64(p)
    except Exception as ex:
        print(f'SKIP {f}: {ex}'); continue
    x = pca.transform(sc.transform([features(a, w, h)]))[0]
    d = {c: float(np.linalg.norm(x - cent[c])) for c in names}
    c = min(d, key=d.get)
    new = d[c] > limit[c]
    style = names[c]
    dest = os.path.join(data, 'added', style)
    os.makedirs(dest, exist_ok=True)
    shutil.move(p, os.path.join(dest, f))
    log.append({'file': f, 'style': style, 'distance': round(d[c], 2), 'new_style': bool(new), 'date': today})
    t.thumbnail((216, 136)); sheet.paste(t, ((i % 4) * 220, (i // 4) * 160))
    print(f'{f} -> {style}{"   (far from all styles: new style?)" if new else ""}')
json.dump(log, open(log_path, 'w'), indent=1)
os.makedirs(os.path.join(data, 'contact-sheets'), exist_ok=True)
out = os.path.join(data, 'contact-sheets', f'inbox-{today}.jpg')
sheet.save(out, quality=80)
print('sheet:', out)
