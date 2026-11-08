"""Build a prompt pack: one Nano Banana prompt per sub-style, plus 3 style-reference images each.

Usage: .venv/Scripts/python -I scripts/pack.py <project-root> <request.json>
request.json = {"slug": "ai-handshake", "ratio": "1:1",
                "subjects": {"bright-airy-minimal": "scene described in plain words", ...}}
Writes generated/<date>-<slug>/PROMPTS.md and refs/<style>/ (refs are kept out of git).
Marc pastes each prompt into the Gemini app with that style's refs attached and saves
the result next to PROMPTS.md as <style>.png.
"""
import sys, os, json, shutil, datetime

root, req_path = sys.argv[1], sys.argv[2]
req = json.load(open(req_path, encoding='utf-8'))
styles_dir = os.path.join(root, 'taste', 'styles')
ex_dir = os.path.join(root, 'taste', 'data', 'exemplars')
ratio = req.get('ratio', '1:1')
out = os.path.join(root, 'generated', f"{datetime.date.today().isoformat()}-{req['slug']}")
os.makedirs(out, exist_ok=True)

lines = [f"# Prompt pack: {req['slug']}", '',
         'For each style: open a new Gemini chat (https://gemini.google.com/app), choose image generation,',
         'drag in the 3 images from `refs/<style>/`, paste the prompt, then save the result here as `<style>.png`.', '']
for style, subject in req['subjects'].items():
    s = json.load(open(os.path.join(styles_dir, f'{style}.json'), encoding='utf-8'))
    refs = sorted(os.listdir(os.path.join(ex_dir, style)))[:3]
    rd = os.path.join(out, 'refs', style)
    os.makedirs(rd, exist_ok=True)
    for r in refs:
        shutil.copy2(os.path.join(ex_dir, style, r), rd)
    prompt = (
        f"Create one {ratio} image.\n"
        f"Subject: {subject}\n"
        f"Style: {s['description']}\n"
        f"Light: {s['light']}\n"
        f"Composition: {s['composition']}\n"
        f"Medium: {s['camera_or_medium']}\n"
        f"Mood: {s['mood']}\n"
        f"Texture and detail: {s['texture_detail']}\n"
        f"Colour palette: {', '.join(s['palette'])}\n"
        "Use the attached images only as style references (colour, light, texture, composition), "
        "never copy their content.\n"
        f"Avoid: {', '.join(s['avoid'])}. No text, no logos, no watermark."
    )
    lines += [f"## {s['name']} (`{style}`)", '', f"Refs: `refs/{style}/` ({len(refs)} images)", '',
              '```text', prompt, '```', '']
open(os.path.join(out, 'PROMPTS.md'), 'w', encoding='utf-8').write('\n'.join(lines))
print(out)
