"""Build taste/taste.json, the one generated taste file, from taste/styles/*.json. Never edit taste.json by hand.

Usage: .venv/Scripts/python -I scripts/build_taste.py <project-root>
Each style becomes one short prompt block for the image model. Optional keys in a style file,
added only after Marc approves a distil proposal:
  "prefer": ["things that rated well", ...]   -> "Lean towards: ..."
  "subjects": ["subjects that suit this style", ...]  (used by variations and, later, random)
"""
import sys, os, json, glob

root = sys.argv[1]
styles = {}
for path in sorted(glob.glob(os.path.join(root, 'taste', 'styles', '*.json'))):
    key = os.path.splitext(os.path.basename(path))[0]
    s = json.load(open(path, encoding='utf-8'))
    parts = [s['description'],
             f"Light: {s['light']}.",
             f"Composition: {s['composition']}.",
             f"Medium: {s['camera_or_medium']}.",
             f"Mood: {s['mood']}.",
             f"Detail: {s['texture_detail']}.",
             f"Palette: {', '.join(s['palette'])}."]
    if s.get('prefer'):
        parts.append(f"Lean towards: {'; '.join(s['prefer'])}.")
    parts.append(f"Avoid: {'; '.join(s['avoid'])}. No text, no logos, no watermark.")
    styles[key] = {'name': s['name'], 'prompt': ' '.join(parts), 'subjects': s.get('subjects', [])}

out = os.path.join(root, 'taste', 'taste.json')
json.dump({'generated_from': 'taste/styles/*.json by scripts/build_taste.py; do not edit', 'styles': styles},
          open(out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print(out, f'({len(styles)} styles)')
