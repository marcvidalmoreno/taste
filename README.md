# taste

My visual taste, written so an image model can use it. I'm Marc, a UX designer, and I use it to make
images for my posts and wallpapers, with ChatGPT's image generation through Codex CLI (since 13 Nov 2026) or
Google's Nano Banana (Gemini app, prompt packs).

## What's here
- [`taste/styles/`](taste/styles/): fourteen styles found in about 1,000 wallpapers I've saved over the years,
  each with a palette, light, composition, medium, mood, an **avoid** list, starter subjects and the uses it suits
  (Teams background, desktop, phone, post). Rebuilt on 13 Nov 2026: every image tagged by eye on contact sheets
  (subject, medium, mood, light), grouped into styles I approved one by one; palettes measured from the images.
- [`taste/gem-instructions.md`](taste/gem-instructions.md): instructions for a Gemini Gem that uses the styles.
- [`taste/taste.json`](taste/taste.json): one short prompt block per style, generated from the style files by
  `scripts/build_taste.py`. Never edited by hand.
- [`scripts/`](scripts/): `pack.py` builds a prompt pack for a post, `inbox.py` sorts newly liked images into
  a style (top-3 guess, confirmed by eye), `build/` is how the styles were found (`restyle.py`: tags to style
  members, measured palettes, exemplars; the older scripts did the 8 Nov colour clustering).
  Codex route: `codex_run.py`, `variations.py`, `sheet.py`, `rate.py`, `distil.py`, `nearest.py` (below).
- [`generated/`](generated/): images **I** generated with these styles, with the prompts used.

## What's not here, on purpose
The wallpapers themselves and every reference image belong to their creators. They stay on my laptop
(git-ignored) and are never published. Only the derived descriptions and my own generated images are public.

## How it works
1. For a post, Claude Code picks the styles that fit, writes one subject per style and runs
   `scripts/pack.py`, which writes `generated/<date>-<slug>/PROMPTS.md` plus three style references per style.
2. I paste each prompt into the Gemini app with its references (free with my Google AI plan; the Gemini API has
   no free tier for image models) and save the result next to the prompts.
3. Images I like later go into `inbox/`; `scripts/inbox.py` files them under the closest style and the style
   descriptions get updated.

## Codex route (ChatGPT plan, no API key, no bill)
Claude Code owns the taste; Codex CLI only generates. One fresh `codex exec` per image. Images, the run log and
ratings stay on my laptop in `generated/codex/` (git-ignored). Run everything from the project root.

| Step | Command |
|---|---|
| Variations of an image I like (3, or `--n 4`) | `.venv/Scripts/python -I scripts/variations.py <image> --style S [--subject "..."]` (no `--style`: prints the top-3 guess) |
| One image from a style and subject (e.g. for a text) | `.venv/Scripts/python -I scripts/codex_run.py gen --out generated/codex/<batch> --name <name> --style <style> --subject "..." [--ratio wide\|square\|portrait] --mode text` |
| Contact sheet of a batch | `.venv/Scripts/python -I scripts/sheet.py generated/codex/<batch>` |
| Rate (numbers from the sheet) | `.venv/Scripts/python -I scripts/rate.py <batch> 1=keep 2=almost:too-busy 3=no:dark` |
| Ratings since the last distil | `.venv/Scripts/python -I scripts/rate.py status` |
| Distil (every ~20 ratings) | `.venv/Scripts/python -I scripts/distil.py`, Claude proposes style edits, I approve, `build_taste.py`, then `distil.py --mark` |
| Allowance now | `.venv/Scripts/python -I scripts/codex_run.py read` |

Variations change one thing each: palette, subject, composition (and mood with `--n 4`). The seed is attached as a
reference and the model follows it closely. Each run logs tokens, five-hour and weekly allowance (read from
Codex's session log, never typed) and the real pixel size to `generated/codex/runs.csv`.

### Allowance (measured 13 Nov 2026, ChatGPT Plus)
- Native size **1672 × 941** (16:9); the image tool has no size option. About 60 s and ~95k tokens per image
  (mostly cached context), ~116k with a reference image.
- 4 images moved the five-hour allowance from 0 to 2 % and the weekly from 33 to 33 %. Codex reports whole
  percentages, so: five-hour ≈ 0.25–0.75 % per image (≈ 130–400 per five-hour window); weekly < 0.25 % per image,
  so **at least ~400 images a week, ~1,700 a month**, if nothing else used Codex. The weekly allowance is shared with
  other Codex work, so in practice: budget 10 % of the week for images = **at least ~40 a week, ~170 a month**.
- The figure firms up as `runs.csv` grows; recompute after ~20 images.

## Changelog
- **13 Nov 2026** – Taste rebuilt from zero: 14 styles replace the old five (bright-airy-minimal, deep-space-dark,
  neon-dusk, retro-sci-fi-painting, warm-interiors-japan). Styles defined by eye, not by colour clustering; colour
  alone finds the right style only 36 % of the time, so `nearest.py` / `inbox.py` / `variations.py` now show a
  top-3 guess and the style is confirmed by eye. `gem-instructions.md` regenerated from the new styles.
  Undo: `git revert <this commit>` (old exemplar copies kept locally in `taste/data/exemplars-2026-11-08/`).
- **13 Nov 2026** – Codex route: `codex_run.py` (one image + run log), `variations.py`, `sheet.py`, `rate.py`,
  `distil.py`, `nearest.py`, `build_taste.py` → `taste/taste.json`; `generated/codex/` git-ignored; repo `CLAUDE.md`
  (automatic pushes). Undo: `git revert <this commit>` (local images and logs in `generated/codex/` are untouched;
  delete that folder by hand if wanted).
