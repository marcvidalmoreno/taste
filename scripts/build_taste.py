"""Build taste/taste.json, the one generated taste file, from taste/styles/*.json. Never edit taste.json by hand.

Usage: .venv/Scripts/python -I scripts/build_taste.py <project-root>
Each style becomes one short prompt block for the image model. Optional keys in a style file,
added only after Marc approves a distil proposal:
  "prefer": ["things that rated well", ...]   -> "Lean towards: ..."
  "subjects": ["subjects that suit this style", ...]  (used by variations and, later, random)
  "light" / "composition" / "mood" as a list, and "palettes": [[...], [...]]  -> looks: taste.json gets
      "looks" (one full prompt per look); codex_run.py --look N picks one. "prompt" stays look 0.
      taste.json also gets "template" (the prompt with {light} {composition} {mood} {palette} slots) and
      "axes" (the options per slot), so codex_run.py --mix picks each axis on its own (18 Nov 2026).
"""
import sys, os, json, glob

root = sys.argv[1]
styles = {}
for path in sorted(glob.glob(os.path.join(root, 'taste', 'styles', '*.json'))):
    key = os.path.splitext(os.path.basename(path))[0]
    s = json.load(open(path, encoding='utf-8'))
    # Looks: light, composition, mood and palette may each hold several options (a list; palettes in
    # "palettes"). The core (description, medium, detail, prefer, avoid) stays fixed. Look i takes option
    # i % n of every axis, so the images of a batch differ in light, framing, mood and colour at once.
    as_list = lambda v: v if isinstance(v, list) else [v]
    options = {'light': [f"Light: {v}." for v in as_list(s['light'])],
               'composition': [f"Composition: {v}." for v in as_list(s['composition'])],
               'mood': [f"Mood: {v}." for v in as_list(s['mood'])],
               'palette': [f"Palette: {', '.join(p)}." for p in (s.get('palettes') or [s['palette']])]}
    parts = [s['description'], '{light}', '{composition}', f"Medium: {s['camera_or_medium']}.", '{mood}',
             f"Detail: {s['texture_detail']}.", '{palette}']
    if s.get('prefer'):
        parts.append(f"Lean towards: {'; '.join(s['prefer'])}.")
    parts.append(f"Avoid: {'; '.join(s['avoid'])}. No text, no logos, no watermark.")
    looks = max(len(v) for v in options.values())

    def render(i):
        out = []
        for p in parts:
            axis = p[1:-1] if p.startswith('{') and p.endswith('}') else None
            out.append(options[axis][i % len(options[axis])] if axis in options else p)
        return ' '.join(out)

    styles[key] = {'name': s['name'], 'prompt': render(0), 'subjects': s.get('subjects', [])}
    if looks > 1:
        styles[key]['looks'] = [render(i) for i in range(looks)]
    styles[key]['template'] = ' '.join(parts)
    styles[key]['axes'] = options

out = os.path.join(root, 'taste', 'taste.json')
json.dump({'generated_from': 'taste/styles/*.json by scripts/build_taste.py; do not edit', 'styles': styles},
          open(out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print(out, f'({len(styles)} styles)')
