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
- [`app/`](app/) + [`scripts/app.py`](scripts/app.py): a local web app (127.0.0.1 only) to look at the Codex
  batches, mark keep / almost / no with a reason, ignore broken images, save ratings, start variations and see
  ratings per style. Plain HTML, CSS (Pico.css, vendored) and JavaScript modules; Python standard library + Pillow.
  Also read-only pages: **Gallery** (every image in justified rows, filters by style, rating and batch),
  **Taste** (the styles with my kept and rejected images as examples) and **About** (`app/about.html`: why,
  history, how it works, decisions, how we work).
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
| **View, mark and save ratings in the browser** (also starts variations, shows the overview) | `.venv/Scripts/python -I scripts/app.py` → http://127.0.0.1:8777 (`--dry-run`: the variations button spends nothing) |
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
- **14 Nov 2026** – Variations can add or remove one thing in every image: `variations.py --note "..."` and a new
  "In every variation" field in the Make variations dialog (e.g. "no planet in the sky"); the note goes in each
  prompt above the style notes. Local `.claude/launch.json` (not in git) gains `taste-app-real` (port 8791, spends allowance).
  Undo: revert this commit.
- **14 Nov 2026** – Web app: Gallery, Taste and About pages (read-only; images still come from the git-ignored
  `generated/codex/`, nothing uploaded). New `GET /api/gallery`; `GET /api/styles` now returns whole style files.
  About text is a draft for my review. Undo: `git revert e6192df`.
- **13 Nov 2026** – Web app, after the first real variations run (3 images, all made): a new batch shows the seed
  and placeholders before its first image, and each tile re-reads its style once `runs.csv` has the row.
  Undo: `git revert c38b518` and this README commit.
- **13 Nov 2026** – Rating web app: `scripts/app.py` serves `app/` on http://127.0.0.1:8777. Batches newest first,
  a grid per batch (to rate / rated / ignored), a large view with prompt, style, seed and change; keys K / A / N,
  Enter for the why, I to ignore, arrows, hold S for the seed. Marks are drafts (`generated/codex/app-drafts.json`)
  until "Save ratings" appends them to `ratings.csv` through `rate.append_ratings`, the writer `rate.py` now shares.
  Ignored images (`app-ignored.json`) stay on disk and out of ratings. Variations from the large view with the
  top-3 style guess, the allowance and a confirm step, one job at a time. Overview: ratings per style, distil
  countdown. Undo: `git revert` the commits from `713214d` to the README commit; then delete `app-drafts.json`,
  `app-ignored.json` and `.thumbs/` in `generated/codex/` by hand if wanted (`ratings.csv` keeps the saved ratings).
- **13 Nov 2026** – Taste rebuilt from zero: 14 styles replace the old five (bright-airy-minimal, deep-space-dark,
  neon-dusk, retro-sci-fi-painting, warm-interiors-japan). Styles defined by eye, not by colour clustering; colour
  alone finds the right style only 36 % of the time, so `nearest.py` / `inbox.py` / `variations.py` now show a
  top-3 guess and the style is confirmed by eye. `gem-instructions.md` regenerated from the new styles.
  Undo: `git revert 9133a5a` (old exemplar copies kept locally in `taste/data/exemplars-2026-11-08/`).
- **13 Nov 2026** – Codex route: `codex_run.py` (one image + run log), `variations.py`, `sheet.py`, `rate.py`,
  `distil.py`, `nearest.py`, `build_taste.py` → `taste/taste.json`; `generated/codex/` git-ignored; repo `CLAUDE.md`
  (automatic pushes). Undo: `git revert 24c1543` (local images and logs in `generated/codex/` are untouched;
  delete that folder by hand if wanted).
- **8 Nov 2026** – First version: five colour-clustered styles, `pack.py` prompt packs for the Gemini app,
  `inbox.py` sorter, `gem-instructions.md`. Undo: `git revert 08cbcf8` (superseded by the 13 Nov rebuild).
