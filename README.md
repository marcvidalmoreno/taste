# taste

My visual taste, written so an image model can use it. I'm Marc, a UX designer, and I use it to make
images for my posts and wallpapers, with ChatGPT's image generation through Codex CLI or Google's Nano Banana (Gemini app, prompt packs).

## What's here
- `taste/` (**private**, not in this repo): the styles, `taste.json` and the Gem instructions live in a private
  repo, cloned into this folder as `taste/` so every path stays the same (since 23 Nov 2026; older versions are
  still in this repo's history). What they are:
- `taste/styles/`: fifteen styles (fourteen found in about 1,000 wallpapers I've saved over the years,
  each with a palette, light, composition, medium, mood, an **avoid** list, starter subjects and the uses it suits
  (Teams background, desktop, phone, post). Rebuilt on 13 Nov 2026: every image tagged by eye on contact sheets
  (subject, medium, mood, light), grouped into styles I approved one by one; palettes measured from the images; plus "Fractal worlds", added 14 Nov 2026).
- `taste/gem-instructions.md`: instructions for a Gemini Gem that uses the styles.
- `taste/taste.json`: one short prompt block per style, generated from the style files by
  `scripts/build_taste.py`. Never edited by hand.
- [`scripts/`](scripts/): `pack.py` builds a prompt pack for a post, `inbox.py` feeds a few newly liked images into
  their styles (see "Feed a style"), `ingest.py` adds a whole folder of images (see "Add a collection"), `build/` is how the styles were found (`restyle.py`: tags to style
  members, measured palettes, exemplars; the older scripts did the 8 Nov colour clustering).
  Codex route: `codex_run.py`, `variations.py`, `sheet.py`, `rate.py`, `distil.py`, `nearest.py` (below).
- [`app/`](app/) + [`scripts/app.py`](scripts/app.py): a local web app (127.0.0.1 only) to start runs (batches
  with fresh subjects, single images, remixes, variations; one queue), look at the Codex batches, mark thumbs up /
  down with a reason, ignore broken images, save ratings, leave notes for Claude and see ratings per style. Plain HTML, CSS (Pico.css, vendored) and JavaScript modules; Python standard library + Pillow.
  Also read-only pages: **Gallery** (every image in justified rows, filters by style, rating and batch),
  **Taste** (the styles with my kept and rejected images as examples) and **About** (`app/about.html`: why,
  history, how it works, decisions, how we work).
- [`docs/how-it-works.md`](docs/how-it-works.md): how a folder of images becomes a style (thumbnails,
  numbers, clusters, tagging by eye, palettes, exemplars) and what Claude did and didn't see.
- [`docs/progress.html`](docs/progress.html): the progress so far, by week and day, as a read-only page in an
  email layout (copy or open in a mail app), plus where it's going and the idea behind it.

## What's not here, on purpose
The wallpapers themselves and every reference image belong to their creators. They stay on my laptop
(git-ignored) and are never published. Since 23 Nov 2026 my styles, prompts and generated images are private too:
this repo holds the code, the app and the docs.

## How it works
1. For a post, Claude Code picks the styles that fit, writes one subject per style and runs
   `scripts/pack.py`, which writes `generated/<date>-<slug>/PROMPTS.md` plus three style references per style.
2. I paste each prompt into the Gemini app with its references (free with my Google AI plan; the Gemini API has
   no free tier for image models) and save the result next to the prompts.
3. Images I like later go into the inbox, in the folder of their style (see "Feed a style").

## Feed a style (a few new images)
For a handful of pictures now and then; a whole folder goes through "Add a collection" instead.
- The inbox has one folder per style, kept up to date by `scripts/inbox.py --setup` (a new style gets its folder
  on the next run). Drop an image in its style's folder: it joins that style as is, no guessing. Not sure? Leave
  it loose. A folder with another name = a candidate new style.
- Then: `.venv/Scripts/python -I scripts/inbox.py` (or tell Claude Code "process my inbox"). Each image is checked
  against everything ingested before, then moved (never deleted) to `taste/data/added/` and recorded in the
  `inbox` collection. Loose images land on one numbered sheet for tagging by eye.
- `scripts/build/remeasure.py <style>` re-measures a palette from all of a style's images (wallpapers, ART,
  inbox) and prints old vs new; `--write` only after my OK, then `build_taste.py`.
- The inbox can live anywhere, e.g. a synced cloud folder so I can save pictures from my phone or browser:
  `taste/data/local.json` → `{"inbox": "<path>"}` (local, git-ignored). Default: `inbox/` in the project.

## Add a collection (a folder of images I like)
The same five steps every time, for any folder: more wallpapers, an art folder, a Pinterest export.
1. **Inventory and dedupe** and 2. **triage**: one command.
   `.venv/Scripts/python -I scripts/ingest.py <folder> --name <collection>`
   It reads every image (sub-folder names are kept as a group, e.g. the artist), drops duplicates within the
   folder and against everything ingested before, and guesses the closest styles for each image. Images close to a
   style land on "fits" contact sheets for that style. Images far from every style land on "new" sheets: they're
   the candidates for new styles. Output: `taste/data/collections/<name>/` (git-ignored) with `REVIEW.md`, the
   counts and links to the numbered sheets.
3. **Tag by eye**: Claude Code reads the sheets ("new" first) and tags subject, medium, mood and light per image.
   This is the costly step in Claude usage. The triage only sees colour and composition: for a folder close to
   the existing styles, tagging the "new" sheets may be enough; for a folder of a different kind (ART, 14 Nov:
   Dubuffet, Escher and Léger landed under "japanese-print" by colour) every sheet needs tagging, with the
   sub-folders (artists) as the better hint.
4. **Propose styles**: new styles and edits to existing ones, one by one, for my OK. The tags go in
   `taste/data/collections/<name>/tags.json` (`{style: [image numbers]}`), then
   `scripts/build/collection_styles.py <name>` measures palettes and copies 8 exemplars per style, the style files
   are written, and `scripts/build_taste.py` rebuilds `taste/taste.json`.
5. **Test**: 2–3 Codex images per new style, rated in the web app; distil after ~20 ratings.

### Make your own taste
Fork the repo, create an empty `taste/styles/` folder, and run `ingest.py` on your own folder. With no styles yet, every image
goes to the "new" sheets, and Claude Code (or you) tags them and proposes your first styles. Your reference images
stay on your machine (`taste/` and `generated/` are git-ignored); keep your styles in a private repo of your own
if you like, cloned as `taste/`.

## Codex route (ChatGPT plan, no API key, no bill)
Claude Code owns the taste; Codex CLI only generates. One fresh `codex exec` per image. Images, the run log and
ratings stay on my laptop in `generated/codex/` (git-ignored). Run everything from the project root.

| Step | Command |
|---|---|
| **The web app: start runs, remix, rate, leave notes for Claude** | `.venv/Scripts/python -I scripts/app.py` → http://127.0.0.1:8777 (`--dry-run`: every run and text job spends nothing) |
| Fresh subjects or a rewritten prompt (what the web app asks Codex) | `.venv/Scripts/python -I scripts/codex_text.py subjects --style S --n 4 [--hint "..."]` or `rewrite --prompt "..." --change "..."` |
| A style edit proposal (what the web app's "Change the style" asks Codex; nothing is written) | `.venv/Scripts/python -I scripts/codex_text.py style --style S --change "..."` |
| Notes Marc left in the web app ("process my app notes") | `.venv/Scripts/python -I scripts/notes.py`, then `notes.py done <id> "<answer>"` |
| Variations of an image I like (3, or `--n 4`) | `.venv/Scripts/python -I scripts/variations.py <image> --style S [--subject "..."]` (no `--style`: prints the top-3 guess) |
| One image from a style and subject (e.g. for a text) | `.venv/Scripts/python -I scripts/codex_run.py gen --out generated/codex/<batch> --name <name> --style <style> --subject "..." [--ratio wide\|square\|portrait] --mode text` |
| **Batch with fresh subjects, mixed looks and one wildcard per style** | Claude writes `generated/codex/<batch>/subjects.json` (`{style: [subjects]}`), then `.venv/Scripts/python -I scripts/batch.py --out generated/codex/<batch> --subjects generated/codex/<batch>/subjects.json [--styles a,b] [--dry-run]` |
| Contact sheet of a batch | `.venv/Scripts/python -I scripts/sheet.py generated/codex/<batch>` |
| How a style's next runs lean (from the thumbs) | `.venv/Scripts/python -I scripts/leaning.py <style>` |
| Rate (numbers from the sheet) | `.venv/Scripts/python -I scripts/rate.py <batch> 1=up 2=down:too-busy 3=down:dark` |
| Ratings since the last distil | `.venv/Scripts/python -I scripts/rate.py status` |
| Distil (every ~20 ratings) | In the web app: Overview → **Distil** (Codex proposes, you apply). By hand: `.venv/Scripts/python -I scripts/distil.py`, Claude proposes, `build_taste.py`, then `distil.py --mark` |
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
- **Remeasured 20 Nov 2026:** 690 images in 7 days with the weekly allowance at only 35 %, so ≤ 0.05 % of the
  week per image (≥ ~2,000 a week if nothing else used Codex). 10 % of the week for images ≈ **200 a week**; the
  web app's budget warning (`WEEK_BUDGET` in `scripts/app.py`) now uses 200.

## Changelog
- **23 Nov 2026** – `scripts/publish.py`: grid thumbnails are now 800 px (were 480 px and looked blurry on wide or
  high-DPI screens); older thumbs are rebuilt on the next `--sync`. Undo: set `THUMB` back to 480.
- **23 Nov 2026** – Gallery: the address follows the large view, one link per image
  (`#/gallery/<batch>/<image>`, filters kept), so an image can be linked, bookmarked and reloaded; Back closes the
  view. Guide updated. Undo: `git revert` this commit.
- **23 Nov 2026** – Large view: after clicking an image in **More like this**, a **← Previous image** button
  (or `Esc`, `Backspace`) walks back to the image you came from, one step at a time. Undo: `git revert` this commit.
- **23 Nov 2026** – `scripts/publish.py` (`--dry-run`, `--sync`) exports the picked images as WebP plus aggregate
  evolution data for the planned public gallery site, after a privacy check that stops before writing anything.
  Nothing is published yet. Undo: `git revert` this commit.
- **23 Nov 2026** – Publish toggle for the planned public gallery site: in both large views a **Publish** button
  (key `P`) picks an image, the Gallery has a **◉ Published** filter and a small dot on picked tiles. Picks are saved
  in `generated/codex/publish.json` (git-ignored); nothing leaves the computer yet. Undo: `git revert` this commit
  (the picks file can stay or be deleted).
- **23 Nov 2026** – FLUX no longer stitches the examples together: in 2 of 18 A/B images FLUX pasted two of the
  attached images side by side, near copies. When FLUX gets examples of a look (the default ones, or kept examples),
  its prompt now starts with one line saying they show the style only, one new scene, don't copy or combine them
  (`FLUX_STYLE_ONLY` in `scripts/codex_run.py`; not for a seed image in Variations). Remake of those 2:
  `2026-11-23-ab-flux-nocopy`, both one scene. Undo: `git revert` this commit.
- **23 Nov 2026** – On FLUX, the make button in Remix and Variations says "Make 4 free images" instead of
  "Spend allowance: make 4 images" (FLUX costs nothing). ChatGPT keeps the old label.
- **23 Nov 2026** – FLUX takes Marc's examples along: an A/B test (18 prompts of a rated ChatGPT batch, FLUX with
  words only vs. with 3 of his thumbs-up images of the style) showed the references pull FLUX much closer to the
  style in science-fiction, cyberpunk-poster and anime-megacity, a little in retro-future-rooms and erotic, mixed in
  dubuffet. So every FLUX image with no image of its own now gets up to 3 examples of its style (kept examples
  first, then the newest thumbs-up images made by ChatGPT, turning through the 12 newest by image number), named in
  its log. ~16 neurons more per image: about 80 free images a day instead of 95. `TASTE_FLUX_REFS=0` turns it off.
  Guide updated. Undo: `git revert` this commit.
- **23 Nov 2026** – One app per port: on Windows, Python's server let a second copy of the app listen on a port that
  was already taken, without an error, so two apps split the clicks and "next free port" never happened. The app now
  takes its port exclusively: a second copy moves to the next free port (8778…) and says so in its first line;
  restarts after a script change still get their own port back. Applies from the next start of the app window.
  Undo: `git revert` this commit.
- **23 Nov 2026** – The app survives a half-finished script edit: when the server crashes (say a session's edit
  lands in two steps more than 10 s apart, and the reload hits the gap), the supervisor no longer quits. It prints
  "starts again by itself once scripts/ change", waits for the next change to settle, and starts the app again on
  the same port. Applies from the next start of the app window. Undo: `git revert` this commit.
- **23 Nov 2026** – FLUX stands out (e4aa9c0 + this): new FLUX runs get folders ending in `-flux` (kept after the
  24-character cut), and FLUX images carry a small **FLUX** badge on their tile in batches and the Gallery (tiles
  and Gallery items now carry `route`). New run's folder line says `-flux` when FLUX is picked. Guide updated.
  Undo: `git revert` both commits.
- **23 Nov 2026** – Queue on hold: before each queued run the app checks that every script compiles; if one doesn't,
  the queue waits (header: "runs on hold · waits for a script fix") and goes on by itself once it compiles. A run
  that made nothing and failed on a Python error also holds the queue, with **Continue** in the header. No more
  ten runs failing in a row on one broken script. Undo: `git revert` this commit.
- **23 Nov 2026** – Batches: removed the page's own **New run…** button; the header's **New run** is the one way in.
  Undo: `git revert` this commit.
- **23 Nov 2026** – Rule: sessions sharing this checkout commit only their own files (`git commit -- <files>`).
  Undo: `git revert` this commit.
- **23 Nov 2026** – Try blocked images with FLUX: Batches has a line counting the images ChatGPT's safety filter
  blocked that FLUX hasn't tried (16 today) with **Try with FLUX**, one run per batch, same prompts and references;
  each blocked tile has the same button. FLUX failures say so ("Blocked by FLUX's filter too"). New
  `GET /api/blocked`, `POST /api/blocked/flux`; failed images carry their route. Undo: `git revert` this commit.
- **23 Nov 2026** – Cloudflare route built ([`docs/cloudflare-route.md`](docs/cloudflare-route.md)): **Made with**
  at the top of the cost block in New run, Remix and Variations, *ChatGPT* (default) or *FLUX* (FLUX.2 klein 4B on
  Cloudflare Workers AI's free allowance, ~95 images a day). New `scripts/cf_run.py`; `codex_run.py gen --route`
  (or `TASTE_ROUTE`); runs.csv gains a `route` column (header rewritten once, old rows read as codex; FLUX rows keep
  estimated neurons in `tokens`). Connect Cloudflare card (account ID and token saved in `%USERPROFILE%\.taste\`,
  outside the repo), "How it was made" says which model, Guide updated. Also: New run › One image no longer shows a
  stray "null" when no kept examples exist. Undo: `git revert` this commit (then delete `%USERPROFILE%\.taste\cloudflare.json`
  if you connected).
- **23 Nov 2026** – Failure messages: runs that fail share one message that counts them and says the reason when
  it's the same for all ("a bug in the image script… nothing was spent" for a script error), with **Details**
  listing each run, instead of one message per run piling up. Messages can now be closed while a dialog is open
  (an open dialog made them unclickable). Undo: `git revert` this commit.
- **23 Nov 2026** – Why an image failed: the batch page's empty tiles now say exactly why, read from Codex's log –
  blocked by the safety filter (what it flagged, and whether it refused the prompt or the finished image), usage
  limit, or timed out. `codex_run.py` now logs a timeout (over 900 s) and writes its runs.csv row instead of
  crashing, so a timed-out image shows as failed, not "never made". Undo: `git revert` this commit.
- **23 Nov 2026** – Resume all: when Codex's usage limit cuts a queue short, Batches shows one line ("8 runs
  stopped… 30 images never made", with the cost) and **Resume all** queues every cut-short run again, in its own
  folder with the same prompts and numbers. Covers the images refused for the limit and the ones the run never
  reached (runs stop after 2 failures), not the ones the filter blocked. Remixes, variations and single images
  also get the batch page's Finish line. New: `GET /api/stopped`, `POST /api/resume-all`, run kind `resume`,
  `variations.py --out --only`; `run.json` keeps `limit_hit` so a later retry can't hide it. Undo: `git revert`
  this commit.
- **23 Nov 2026** – New [`docs/cloudflare-route.md`](docs/cloudflare-route.md): plan for a free third image route,
  FLUX on Cloudflare Workers AI's daily allowance (~95 images a day), chosen in the app as "Made with". Plan only,
  nothing built. Undo: `git revert` this commit.
- **23 Nov 2026** – Rule: start the app with `/launch-localhost` (own console window), never `preview_start`, so the
  server outlives the session (CLAUDE.md, commit 3c2b602). Undo: `git revert` that commit and this one.
- **23 Nov 2026** – Download: both large views (batch and Gallery) have **Download** in the top bar, which saves the
  full-size image as `<batch>-<file>.png`. A batch's folder line has **Download all** (one zip of its images; on a
  filter, **Download these N** zips only what the grid shows). New server route `/zip/<batch>`. Guide updated.
  Undo: `git revert` this commit.
- **23 Nov 2026** – Fix: About › How it grew showed each date as a narrow vertical strip, one letter per line. The
  style page's Evolution list shared its class name; its layout now applies only there.
- **23 Nov 2026** – New run: **Per style** goes up to 24 (1–8 one at a time, then 10, 12, 16, 20, 24); the
  server and Codex's subject writer accept the same. Guide updated. Undo: `git revert` this commit.
- **23 Nov 2026** – Gallery: **Small / Medium / Large** at the top right sets the image size (about 5, 3 or 2
  images a row on a laptop screen). Rows reflow at once and the choice is remembered in this browser. Guide updated.
  Undo: `git revert` this commit.
- **23 Nov 2026** – Fix: a remix's long instruction under a tile spilled over the next tile and hid the style name.
  The pill now ends in an ellipsis (full text on hover), in the grid and in the large view. Undo: `git revert` this
  commit.
- **23 Nov 2026** – Large view: a **Batches** link in its top bar (Batches › batch name), so the home page is one
  click away even when the view was opened from a link; the header is hidden behind the view. Leaving the view for
  another page now opens that page at the top. Guide updated. Undo: `git revert` this commit.
- **23 Nov 2026** – Batch page: new **All** filter (every image except the ignored ones), now where a batch opens,
  so images you rate stay in view. **Ignored** only shows when the batch has ignored images. Guide updated.
  Undo: `git revert` this commit.
- **23 Nov 2026** – Batch page: **Finish this batch**. When a batch run stopped early (usage limit, 3 failures in a
  row, Stop), a line above the grid says how many images were never made and why, with one button that makes them
  with the first run's subjects, mix seed, wildcard and kept examples (`batch.py --only`, new run kind `finish`;
  `run.json` keeps the first run's record and gains `finished_later`). Guide updated. Undo: `git revert` this commit.
- **23 Nov 2026** – Fix: **Retry once** on a failed image overwrote the batch's `run.json` ("How it was made") with a
  record of just that retry; it now leaves it alone. Undo: `git revert` this commit.
- **23 Nov 2026** – Styles page: a style's history no longer fails with "Could not read the history" when two of its
  images were made in the same minute and one isn't rated yet.
- **23 Nov 2026** – Batch page: the **To rate** number drops as soon as you rate an image (it counted the images
  rated during the visit, which stay in that grid so nothing jumps). Guide updated.
- **23 Nov 2026** – New **Styles** page (header, after Gallery, `#/styles`): every style in one list with an on / off
  switch, images, 👍 rate with n, ★ kept, last run and a trend; click a name for its history (timeline of commits,
  app edits, suggestions and switches with the 👍 rate before and after each, a per-batch chart, the runs). Switching
  off moves the style file to `taste/styles/archived/` (every script then skips it), logs it in
  `style-edits.json`, and refuses while a run or suggestion round uses the style; Undo in the message. Archived styles
  drop out of New run, Suggestions and the Remix / Variations guesses, stay in the Gallery and Overview, and sit folded
  at the bottom of Taste with "Switch back on". Guide updated. Undo: `git revert` this commit (styles switched off stay
  in `taste/styles/archived/`: move them back).
- **23 Nov 2026** – Gallery: the large view is now the batch large view's twin. Same layout (image on a stage with
  Fit / 1 : 1, panel on the right) and the same buttons and keys: Remix, Variations, Change the style, Note for
  Claude, Keep, More like this, the details (made as, seed, size, time) and Copy prompt. It still steps through the
  Gallery's filtered list. Ignore and Hold S stay in the batch view. Guide updated. Undo: `git revert` this commit.
- **23 Nov 2026** – Gallery: a **Find** field before the filters. Every word typed must appear in the image's
  prompt, why, style name, batch or variation (any order, dashes count as spaces); it works with the rating, style
  and batch filters, narrows the grid as you type and stays in the address (`?q=`). Guide updated. Undo:
  `git revert` this commit.
- **23 Nov 2026** – Styles go private: `taste/` (styles, `taste.json`, Gem instructions) is now its own private
  repo, cloned into this folder, and ignored here. No paths changed, the app works as before. Style changes are
  committed there from now on, with their own changelog; this README only notes that they happened. Guide updated
  (style edits go to the private repo). Undo: remove the `taste/` line from `.gitignore` and `git add taste/`.
- **23 Nov 2026** – Style edits from the app committed (21 Nov): `dubuffet` prefers unequal, nested cells with
  white interiors and fine red or blue stripes (distil); `erotic` gets one more "lean towards" line (Marc's edit);
  `fractal-worlds` names Mandelbrot variations (classic, Tricorn, Burning Ship, higher powers) in its description;
  `retro-future-rooms` avoids dense clutter on every surface (distil). `taste.json` rebuilt. Undo: `git revert` this
  commit.
- **23 Nov 2026** – `generated/` is now local only, like `generated/codex/`: the folder is ignored and its few
  tracked files (fractal samples, the ai-handshake prompts and request) are no longer in git. They stay on the
  laptop; older versions remain in git history. Undo: remove the `generated/` line from `.gitignore` and
  `git add generated/`.
- **23 Nov 2026** – The app restarts itself after an update: when code in `scripts/` changes and nothing is
  running (no run, no distil round, no open request), the server starts again on the same port within ~20 s and
  keeps the last runs' messages and logs. The started process now only watches over the server, and closing it
  stops the server too. Nothing to do on your side.
- **23 Nov 2026** – More like this: an app server started before the feature existed answered "not found", and
  every large view showed it as a message. Now the row just says it shows up the next time the app starts, with
  no message.
- **23 Nov 2026** – Messages: every message at the bottom of the app has a **×** to close it (failure messages
  stay until closed and had no way to close them other than their button). A run where nothing was made now offers
  **Details** (the log) instead of **See them**, which opened a batch that doesn't exist ("not found"). Guide updated.
- **21 Nov 2026** – New run: **Select all** next to the style filter picks every style (with a filter on, it reads
  "Select the N shown" and picks only those). The cost box shows the size straight away (30 styles × 4 = 120 images).
  Keyboard focus moves to Clear after Select all, and back. Guide updated.
- **21 Nov 2026** – More like this (Marc picked idea 2 of the inspiration research, "go"). A **More like this** row in
  the Large view and the Gallery large view: the 8 existing images closest in colour and framing, a **Same style
  only** chip, a click opens the neighbour in the Gallery large view (← → steps through the row, which has its own
  row). New `scripts/similar.py` (same number recipe as `nearest.py` / `features.py`: 35 numbers per image from its
  thumbnail, standardised, colour and composition weighted equally; cached in `generated/codex/.look-index.json`,
  safe to delete; the first look measures all images, about 7 s) and `GET /api/similar/<batch>/<name>[/same]`. It sees
  colour and framing, not subject. Free: no Codex, no images. Also fixed: the Gallery large view opened from Taste
  or from a row now keeps the grid's own list, and shows the style name and "Change the style…" there. Guide updated.
  Undo: `git revert` this commit.
- **21 Nov 2026** – Keep as example (Marc picked idea 1 of the inspiration research). A **★ Keep as example** button
  (key **X**; K was already "up") in the batch Large view and the Gallery large view, and a ☆ / ★ on every example
  thumbnail on Taste. Kept images show first in the style's Evidence ("★ Kept as examples") and a star on their
  Gallery tile. New batch and single-image runs of that style send up to 2 kept images along as references (turning
  through them), through a tick in New run that is on by default and never spends extra images; Preview shows which
  images go with which prompt, and a retried image gets the same ones. Stored in `generated/codex/kept.json`
  (git-ignored). `codex_run.py` takes several `--ref`; runs.csv writes `kept a.png + b.png` in the seed column.
  Guide updated (Large view, New run, Gallery, Taste, keys, use case, undo table). Undo: press the star again per
  image, untick "Send my kept examples" per run, or `git revert` this commit.
- **21 Nov 2026** – New style from images (Marc: "Yes, build it", after asking how a Midjourney `--sref` look could
  become a taste style). Taste → **New style from images…**: add 1-4 references (choose, drop or paste), optional
  name and "what draws you to them"; Codex looks at them (`codex_text.py new`, `codex exec -i`, read-only, medium
  effort, ~30 s) and writes every field; the palette is measured from the pixels (`features.palette`); Marc edits
  any field, **Create style** writes `taste/styles/<key>.json` and rebuilds `taste.json`, then **First run**. The
  references stay in `generated/codex/references/<key>/` (git-ignored) and show as "Started from" on the card.
  Undo moves the style file and references to `generated/codex/removed-styles/`. Guide: new section, a use case,
  a row in the undo table. Undo: `git revert` this commit.
- **21 Nov 2026** – Research note [`docs/research/2026-11-inspiration.md`](docs/research/2026-11-inspiration.md):
  public features of Midjourney and Lummi (in depth) and Krea, Cosmos, Recraft and Google Whisk/Mixboard (lighter),
  what taste already does, 13 ideas, a ranked shortlist of 8 and a "Rejected and why" list. Public pages only;
  nothing in `app/` or `scripts/` changed, so no Guide update. Undo: `git revert` this commit.
- **21 Nov 2026** – Style guess fixed (Marc: "No guess: ModuleNotFoundError: No module named 'numpy'"). The app
  on 8791 had been started with the system Python, which has no numpy or scikit-learn. `scripts/app.py` now
  restarts itself with the project `.venv` Python when started with another one, and `scripts/nearest.py` falls
  back to the `.venv` packages, so the guess also worked on the already-running server without a restart.
  Nothing visible changed, so no Guide update. Undo: `git revert` this commit.
- **21 Nov 2026** – Thumbs in the Gallery (Marc: "I click on a picture and I cannot like/dislike"). The Gallery's
  large view now has the Up / Down buttons, U / D keys and a why field, saved at once through the
  same `PUT /api/mark` as the batch view; the tile badge updates in place, the grid does not reflow. Also fixed:
  since marks save at once, `/api/gallery` read the always-empty `saved` field, so every Gallery image showed as
  "Not rated" (975 of 975); it now reads the current mark. Guide updated. Undo: `git revert` this commit.
- **21 Nov 2026** – Faster home page (Marc: "Load batches takes ages"): `scripts/app.py` read `runs.csv` and
  `ratings.csv` once per batch (120+ times per load); `list_batches` and the Gallery now read them once and share
  them (`all_runs`, `batch_images(batch, shared)`). `/api/batches` 1.4 s → 0.18 s, same data. Nothing visible
  changed, so the Guide stays as it is. Undo: `git revert` this commit.
- **21 Nov 2026** – Two text pages in the web app (Marc): **About** (`app/about.html`) rewritten as an introduction
  to why the project exists (taste is recognised before it is described, evidence over guesses, the human decides,
  nothing hidden, tech out of sight), still a draft for Marc's review; new **Guide** (`app/guide.html`, `#/guide`,
  header link) with everything the app can do page by page, all keys and 14 use cases. `js/about.js` loads both
  and now opens a page at the top. Rule in `CLAUDE.md` ("Every change"): app changes Marc can see update the Guide
  in the same commit. Undo: `git revert` this commit.
- **21 Nov 2026** – About page brought up to date: history up to today (thumbs, the app as the interface), How it
  works with runs from the page, leaning, change the style and suggestions; "Draft, then save" replaced by "Every
  mark counts at once" and "The app is the interface"; Codex's text jobs named in "How we work". Still marked as a
  draft for Marc's review. Undo: `git revert` this commit.
- **21 Nov 2026** – Tech out of sight (Marc: feedback happens in the app, Claude and Codex orchestrate the rest):
  the distil runs by itself every 20 ratings (`maybe_auto_distil`, after a thumb and on start; never in dry run);
  a calm **"N style suggestions"** chip in the header appears only when one waits; the page is now
  **Suggestions for your styles** (`#/suggestions`): the suggestions to Apply or Skip, the styles that are fine
  folded in one line, the last look summarised. No "mark done": a round closes on its own when nothing waits,
  and the next one starts after the ratings that existed when it started (none are lost). CLAUDE.md: new section
  "How Marc works: the app is the interface". Undo: `git revert` this commit.
- **21 Nov 2026** – Distil in the app ("option 1"; options 2 and 3, scheduled Claude and fully automatic, are parked
  in a doc). New **Distil** page (`#/distil`, from the Overview card): one button asks Codex about every style with
  2+ ratings since the last distil (`codex_text.py distil`, medium reasoning, 3 at a time, about 10–30 s each). Each
  style's card shows the images rated (ups and downs, with the why), Codex's reading and its proposed edit field by
  field; untick, Apply (undoable, logged in `style-edits.json`) or Skip; "No change needed" when the ratings are too
  few or mixed. "Mark the distil done" runs `distil.py --mark` from the page (Marc's call; not in dry-run mode).
  Proposals live in `generated/codex/distil-run.json`, so they survive closing the page or a restart. The router
  now matches the longest path first. Undo: `git revert` this commit.
- **21 Nov 2026** – Thumbs count at once and steer the style. Web app: Up / Down is saved the moment you press it
  (no drafts, no "Save ratings" step; the save bar and review dialog are gone) and can be changed or taken back any
  time: `ratings.csv` stays append-only, the latest row per image wins, `cleared` means taken back (`rate.latest`,
  `rate.since_last`, so distil and the Overview count each image once). The 40 marks waiting as drafts were saved
  on start (copy: `generated/codex/app-drafts.before-autosave.json`). New `scripts/leaning.py`: each mark moves the
  weight of the light, framing, mood, palette (and detail) options its prompt used, matched by text;
  `codex_run.py --mix` picks options by these weights (liked about 1.6× as often in a 4-image batch, disliked about
  half, every option keeps a chance; `--no-lean` to switch off; "lean" in the change column), and Codex's fresh
  subjects go further from liked subjects and away from disliked ones. The viewer says what a mark moves; the Taste
  page shows "How new runs lean" per style. Distil stays (written edits to the style; the leaning only re-weights
  options). Viewer: an image outside the current filter steps through the whole batch. Run chip stays one line.
  Undo: `git revert` this commit (the 40 saved drafts stay in ratings.csv; the copy has them).
- **21 Nov 2026** – Web app: **Change the style** from wherever you see its images (viewer key E, gallery large view,
  a single-style batch, each style on the Taste page). Write what should change ("fewer elements, less
  repetition"); Codex proposes the smallest edit to the style's fields (`codex_text.py style`, read-only, ~15 s),
  shown field by field with the changed words marked; untick what you don't want and apply. Or add your words as
  they are, as a "lean towards" or an "avoid" line. The app rewrites `taste/styles/<style>.json` in the repo's
  format, rebuilds `taste.json`, and the next image in that style uses it (also images still to come in a running
  run). Every edit keeps its before / after in `generated/codex/style-edits.json`: Undo in the toast and on the
  Taste page. The app never commits; "commit my style edits" in chat does. Taste page shows "Lean towards".
  Undo: `git revert` this commit.
- **21 Nov 2026** – Web app: start and steer runs from the page instead of from chat (Marc chose "Codex text + queue").
  **New run** page: pick styles, images per style, shape, wildcard; subjects one per line, empty lines written by
  Codex (new `scripts/codex_text.py`, read-only text jobs, ~15 s) or the style's examples; free prompt preview;
  cost always in view; a **One image** mode. **One queue**, one image run at a time (runs from chat hold it):
  header chip shows "+N queued", Log has Stop and the queue, desktop notification and a mark in the tab title when
  a run ends. **Batches** page: "Now and next" on top, search, filter by kind, grouped by day. **Batch** page:
  folder path (copy, open in Explorer), "made from" with a link to the source image, "how it was made", batches made
  from its images, failed images with **Retry once**. **Viewer**: **Remix** (R: say what changes, Codex rewrites the
  prompt, read the word diff, edit, make 1–4), **Variations** (V: any mix of palette, subject, composition, mood) and
  **Note for Claude** (C). Notes wait in `generated/codex/claude-notes.json` (new `scripts/notes.py`); the Overview
  page lists them with Claude's answers. Every run started here writes `run.json` in its folder. New
  `scripts/run_list.py`; `batch.py --ratio`; `variations.py --changes`; `progress.py` records the run's pid (for
  Stop). CLAUDE.md: Codex may write subjects and prompts, never style files. Taste page: list-valued facts shown as
  lists, swatch sizes scoped to the Taste cards. Restart the app server once to pick it up.
  Undo: `git revert` this commit.
- **21 Nov 2026** – New [`docs/local-route.md`](docs/local-route.md): plan for a local, unfiltered image model on Marc's
  personal PC (set-up steps, limits, what Claude Code builds there). Undo: `git revert` this commit.
- **21 Nov 2026** – New style `kalahari-documentary` from the 95 Kalahari documentary photos of the 19 Nov collection
  (local only): golden-hour and firelight portraits, hunters in single file, red sand; adults only, no nudity, no
  real named people. Palette measured. 30 styles. Undo: `git revert` this commit, then `build_taste.py .`
- **21 Nov 2026** – Style tweaks from Marc's feedback on the 20 Nov round: cyberpunk poster less pink and more
  varied (acid green / amber light, a red-orange sun, a toxic-green palette, top-down and close-up compositions,
  avoid pink as the main colour); fractal worlds purely abstract (no cities, objects or plants); iridescent abstract
  more variety (UV and prism-caustic light, geometric and oil-slick compositions, new materials, a loud mood);
  japanese landscape gets worm's-eye, bird's-eye and tilted compositions. Undo: `git revert` this commit.
- **20 Nov 2026** – Image budget raised from 40 to 200 a week (`WEEK_BUDGET` in `scripts/app.py`, "Allowance"
  above), so the variations dialog stops warning on normal use. Undo: `git revert` this commit.
- **20 Nov 2026** – Live progress for runs started from chat: `batch.py`, `variations.py` and a lone
  `codex_run.py gen` write `generated/codex/.progress.json` (new `scripts/progress.py`, 10 s heartbeat). The web
  app's header chip shows "Making 3 of 16 · fern-3 · 4:12" for any run, a **Log** button opens the live log
  (each image's subject, ok / failed and time), the batch grid shows a placeholder per image to come, and a toast
  says when the run ends or stopped. The page checks every 10 s when idle, so no reload needed. Restart the app
  server once to pick it up. Undo: `git revert` this commit.
- **20 Nov 2026** – `sci-fi-interface-panels` broadened (the first tests looked alike and close to the sources):
  five kinds of interface (colour-block panels, holographic glass displays, green wireframe terminals, radial
  displays, white medical screens) and three more palette families (cyan hologram, green phosphor, white with red;
  picked by hand, not measured). Undo: `git revert` this commit, then `build_taste.py .`
- **20 Nov 2026** – `batch.py` spreads the looks: within a style, each image takes a different light, framing,
  mood and palette (`codex_run.py --slot K`) instead of a random pick that could repeat. Undo: `git revert` this commit.
- **19 Nov 2026** – `dubuffet` as a family of combinations (Marc: each Dubuffet work combines the traits
  differently): small fixed core (many nested cells, thin stripes, white main fill, red and blue lead) plus axes
  for ground/fills (4), structure (5), line and stripe treatment (4, new), mood (4) and palette (6); use `--mix`.
  `build_taste.py`: `texture_detail` may be a list, which becomes a fifth `detail` axis. First mix overshot (giant
  patches, zebra stripes); re-tweak avoids thick zebra stripes, black-and-white dominance, pink/teal/yellow pop
  accents. Undo: `git revert` this commit, then `build_taste.py .`
- **19 Nov 2026** – New collection `new-2026-11-19` (308 files, 282 after duplicates; local only), tagged by eye.
  Five new styles: `vintage-city-postcards` (38 old Brussels postcards; day and night palette families),
  `art-nouveau-interiors` (10), `minoan-fresco` (10), `digital-rain` (14) and `sci-fi-interface-panels` (15, kept
  generic: no franchise designs, labels as blocks, not words). 56 images join ten existing styles; nine of them
  get re-measured base palettes (tiny shifts; `anime-megacity` left as is, its originals aren't in the sources).
  The 91 documentary photos of a real people are left out. `remeasure.py` now also counts `_join:<style>` tags.
  29 styles. Undo: `git revert` this commit, then `build_taste.py .`
- **18 Nov 2026** – `batch.py --start K`: begin at subject K, so a second batch uses a subjects file's later
  subjects (image names K+1…). Undo: `git revert` this commit.
- **18 Nov 2026** – More variation (the 18 Nov x4 run repeated 44 of 96 earlier prompts word for word): new
  `scripts/batch.py` runs a batch from a fresh `subjects.json` per run; `codex_run.py --mix SEED` picks light,
  framing, mood and palette each on its own (about 190 combinations per style instead of 4 fixed looks);
  `--extreme light|framing|palette|scale|detail|mood` pushes one dimension to an extreme (the last image of each
  style in a batch); `--print` shows the prompt without running Codex. What was picked goes in the `change`
  column (e.g. `mix l2 c0 p1 x:mood0`), and `distil.py` counts up/down per picked part. `build_taste.py` also writes
  `template` and `axes` per style to `taste.json`. Undo: `git revert` this commit, then `build_taste.py .`
- **18 Nov 2026** – `dubuffet` round 3 (v4 overshot into pale worm mazes): mix of big blocky cells, medium cells
  and a few corridors of varying width; most large cells hold nested smaller ones; saturated red and blue stripes;
  dashed line hugs the inside edge, never down the middle; avoid road-marking centre lines, worm/snake corridors,
  snaking mazes, pastel stripes. Undo: `git revert` this commit, then `build_taste.py .`
- **18 Nov 2026** – Rating is now thumbs up / down (was keep / almost / no). Web app: Up / Down buttons, keys
  U / D (K / N still work); `rate.py` takes `up` / `down`. Stored values stay `keep` / `no`, so older ratings read
  the same; older `almost` ratings still show as "Almost (old)" in the overview, gallery, Taste page and distil.
  Undo: `git revert` this commit.
- **18 Nov 2026** – `dubuffet` round 2 (v3 rated: tidy ones almost, loose ones keep): irregular asymmetric cells
  (bent corridors, L/U/branching shapes), thin stripes at a different angle per cell, many diagonal; dashed red
  line on about a third of outlines; avoid symmetry, grid rows, boxy rectangles, only-horizontal/vertical or thick
  candy stripes. Undo: `git revert` this commit, then `build_taste.py .`
- **16 Nov 2026** – `erotic` subject 2: the bare-back mirror scene (blocked by the Codex filter twice today) becomes
  a side view at the mirror in a long silk evening dress. Undo: `git revert` this commit, then `build_taste.py .`
- **16 Nov 2026** – `dubuffet` closer to the real paintings: cells with straight edges and rounded corners, nested
  like a floor plan, many small around a few large; fills of straight parallel stripes, brushy white or small solid
  patches; red dashed line inside the black outlines; avoid bubbles, scribbled, cross- and zigzag hatching, same-size
  cells (replaces the "even stripes" ban). Undo: `git revert` this commit, then `build_taste.py .`
- **16 Nov 2026** – From the first test sheets: `dubuffet` no longer reads as a jigsaw (irregular organic cells,
  uneven hand hatching; avoid puzzle tabs, regular tiles, even stripes); `cyberpunk-poster` keeps the big sun to
  one look and the big face to the double-exposure look. Undo: `git revert` this commit, then `build_taste.py .`
- **16 Nov 2026** – Two new styles from 18 anime/cyberpunk images Marc shared (local only, `taste/data/added/`):
  `anime-megacity` (hand-painted anime film backgrounds: aerial megacities, sign-filled streets, cyborg labs; cold
  night and warm glow palettes) and `cyberpunk-poster` (screen-print and flat digital posters: silhouettes,
  double exposure, symmetry, neon; ink-and-neon and violet-dusk palettes). Palettes measured from the images;
  no text, logos or recognisable characters. 24 styles. Undo: `git revert` this commit, then `build_taste.py .`
- **16 Nov 2026** – Drop `botanical-fresco`. 22 styles. Undo: `git revert` this commit, then `build_taste.py .`
- **16 Nov 2026** – `art-brut` and `dubuffet` are now purely abstract: no faces, people, eyes, creatures or hidden
  objects (description, composition, subjects and avoid list). Palettes unchanged. Undo: `git revert` this commit,
  then `build_taste.py .`
- **16 Nov 2026** – Drop five styles: `cubist-machine`, `psychedelic-dreams`, `escher`, `goyon`, `cave-painting`.
  New `dubuffet` (Dubuffet cells): the 42 DUBUFFET images split out of `art-brut` plus 7 untagged ones (49);
  `art-brut` keeps the other 35 (Basquiat, graffiti, coloured-pencil tangles), its text and palettes re-measured.
  Both have 3 palette families. `fractal.py` example now uses `fractal-worlds`. 23 styles. Local tags backup:
  `taste/data/collections/art/tags.before-dubuffet.json`. Undo: `git revert` this commit, copy the backup over
  `tags.json`, then `build_taste.py .`
- **15 Nov 2026** – `erotic` subjects: the two boundary-ladder prompts that passed the Codex filter (robe off one
  shoulder; bare back at a mirror), the first replacing the plainer chaise-longue subject. Ladder result: bath,
  sheets, open shirt, lingerie and nude back were all blocked (shirt and lingerie already at the prompt).
  Undo: `git revert` this commit, then `build_taste.py .`
- **15 Nov 2026** – New [`docs/progress.html`](docs/progress.html): progress from 8 to 15 Nov by week and day
  (from git history and this changelog), ideas for where it's going, and the idea behind it. Email layout with
  "Open in my mail app" and "Copy text"; counts only, no private data. Undo: `git revert` this commit.
- **15 Nov 2026** – Batch large view: on a narrow or zoomed-in window (≤ 900 px CSS width) the panel slid up
  over the image and the image spilled past its box (Pico centres dialog children; `max-height: 100%` didn't
  resolve). Same fix as the gallery's large view: the image fills the space above the panel, whole, and the
  panel scrolls on its own (max 45 % of the height). Wide layout unchanged. Undo: `git revert` this commit.
- **15 Nov 2026** – `erotic`: one woman alone, sensual through pose, gesture and glance (new "Lean towards"),
  long draped fabric instead of bare skin (Avoid gains "large areas of bare skin"), 4 new solo subjects.
  The old slip-dress subject was blocked twice by the image filter; the chaise-longue and terrace prompts passed.
  Undo: `git revert` this commit, then `build_taste.py .`
- **15 Nov 2026** – Looks for the other 24 styles (one OK for the set): 4 lights, compositions and moods each,
  look 0 word for word today's text, palettes = today's plus the 2 measured colour families furthest from it
  (`fractal-worlds` keeps its one palette: no source images). Default prompts unchanged except
  `botanical-fresco` (Avoid gains "nude figures", the likely cause of its 2 safety blocks) and
  `neon-night-cities` (description: the synthwave sunset is one variant, not the default).
  Test (76 images, looks 1–3 on the subjects of the `-more` batches, `generated/codex/2026-11-15-<style>-looks/`):
  all made, no safety blocks (the 2 botanical-fresco subjects blocked before now pass); one Codex stall
  (15-minute timeout) recovered on the one retry. Clear variety in most styles; least change in art-brut,
  cubist-machine, retro-future-rooms and microscope-rocks. Neon's sun now shows only in its sunset look.
  Weekly 59→66 %. Undo: `git revert` this commit, then `build_taste.py .`
- **15 Nov 2026** – Looks: more variety inside a style. A style's `light`, `composition` and `mood` may now be
  lists, plus `palettes` (several measured palettes); the core (description, medium, detail, avoid) stays fixed.
  `build_taste.py` writes one full prompt per look into `taste.json` (`looks`; `prompt` is still look 0, so
  styles without lists build exactly as before), `codex_run.py --look N` picks one, and
  `build/remeasure.py --groups N` splits a style's liked images into N colour families with a palette each.
  Trial on 3 styles that came out too alike (quiet-landscapes, neon-night-cities, japanese-rooms): 4 looks
  each, 3 measured palettes; quiet-landscapes' description no longer names the Milky Way and stars are "only at
  night". 12 test images reuse the subjects of the `-more` batches, in `generated/codex/2026-11-15-<style>-looks/`.
  Undo: `git revert` this commit, then `build_taste.py .`
- **15 Nov 2026** – Rule in `CLAUDE.md`: style edits need one OK per set of edits, not one per edit.
  Undo: restore the old line ("Each style edit needs Marc's OK").
- **15 Nov 2026** – Four more images for each of the 27 styles (108, Codex), each changing one thing against the
  style's own subjects: a new subject, a composition, a mood or time of day, or the format (square / portrait).
  One batch folder per style, `generated/codex/2026-11-15-<style>-more/`; the plan and runner sit in the hidden
  `generated/codex/.plans/` (local only; rerunning the runner skips finished images and stops at the first
  failure or at 95 % of the five-hour allowance). An image rejected by OpenAI's safety filter
  (`moderation_blocked`, checked on the output, not the prompt) is skipped and listed in `.plans/blocked.txt`
  instead of stopping the run: the first one was a lemon tree with a fox, sent unchanged. Result: 106 of 108
  made in ~1h45, both blocks in `botanical-fresco` (likely its "classical figures"); five-hour 19→80 %, weekly
  48→58 %. Square and portrait come out at their own sizes (e.g. 1254 × 1254). Undo: delete those folders and
  this line.
- **15 Nov 2026** – Copy check report for `japanese-landscape-1`: the image traced from style file to PNG via
  Codex's session log (prompt reached `image_gen` unchanged) and compared with the 884 ART sources (pHash,
  outlines, layout; no near-copy). One self-contained HTML in the batch folder (`generated/codex/`, local only:
  it embeds source scans). New `report-static` entry in the git-ignored `.claude/launch.json` serves
  `generated/codex/` on 127.0.0.1:8792 for the preview pane. Undo: delete `report.html` in the batch folder,
  the launch entry and this line.
- **15 Nov 2026** – Batch grid: Keep / Almost / No buttons under each tile, the same as in the large view
  (one shared `markButtons()` in `app/js/marks.js`), so an image can be marked without opening it. Hidden on
  saved and ignored images; kept out of the Tab order because K / A / N already mark the focused tile.
  Undo: `git revert` this commit.
- **15 Nov 2026** – Gallery large view: on a narrow or zoomed-in window (≤ 900 px CSS width, image above the
  bar) the image was cropped behind the bar because Pico centres dialog children, so the image row never got a
  height. Now the image fills the space above the bar, whole, and the facts panel scrolls on its own (max 40 % of
  the height). Wide layout unchanged. Undo: `git revert` this commit.
- **15 Nov 2026** – Feed a style: `inbox.py` rewritten. One inbox folder per style (created by `--setup`), images
  join the style of their folder, loose ones go to a numbered sheet, duplicates are caught against everything
  ingested; images move to `taste/data/added/` and are recorded as the `inbox` collection. Inbox path settable in
  `taste/data/local.json`. New `scripts/build/remeasure.py` (palette from all sources), `features.palette()`,
  `ingest.known_hashes()`. Undo: `git revert` this commit; the old inbox.py is in `22955be`.
- **15 Nov 2026** – Four more styles from ART, palettes measured: `pastel-retro-sci-fi` (110 images),
  `cubist-machine` (27), `cave-painting` (40), `botanical-fresco` (26). 27 styles. Undo: `git revert` this commit,
  then `build_taste.py .`
- **15 Nov 2026** – New [`docs/how-it-works.md`](docs/how-it-works.md): the pipeline from a folder to styles, the
  8 Nov colour clusters and their limit, the 13 Nov tagging by eye, the ART triage, and an honest note on what
  Claude saw (150 px thumbnails, folder names, its own knowledge; no web search). Undo: `git revert` the
  "docs: how it works" commit.
- **15 Nov 2026** – DP-GOYONweb is Goyon too: its 10 artworks join `goyon` (99 images) and its robot sculpture
  joins `robots` (20); logos and press photos stay out. Both palettes re-measured. Undo: `git revert` this commit,
  then `build_taste.py .`
- **15 Nov 2026** – Eight styles from the ART collection, tagged by eye on 17 sheets (798 images, about 60 left out:
  photos of people and exhibitions, screenshots; Asterix and DP-GOYONweb excluded): `art-brut`, `goyon`,
  `japanese-landscape`, `science-fiction` (clear-line comics), `microscope-rocks`, `erotic` (suggestive, not
  explicit), `robots`, `escher`. Palettes measured from the images. New `scripts/build/collection_styles.py`
  (tags → palettes, exemplars, members); `ingest.py` writes `meta.json` with the source folder. 23 styles.
  Undo: `git revert` the "ART styles" commit, then `build_taste.py .`
- **14 Nov 2026** – Add a collection: `scripts/ingest.py <folder> --name <c>` (inventory, dedupe against everything
  ingested, triage into "fits <style>" and "new" contact sheets, `REVIEW.md` with counts and groups), all output in
  the git-ignored `taste/data/collections/`. `nearest.py` exposes `score()` for thumbnail arrays. README: "Add a
  collection" and "Make your own taste". First run, ART: 828 unique images in 37 groups; the colour triage is a
  weak hint there, so every sheet needs tagging. Undo: `git revert` the "Add a collection" commit and delete
  `taste/data/collections/`.
- **14 Nov 2026** – Variations can add or remove one thing in every image: `variations.py --note "..."` and a new
  "In every variation" field in the Make variations dialog (e.g. "no planet in the sky"); the note goes in each
  prompt above the style notes. Local `.claude/launch.json` (not in git) gains `taste-app-real` (port 8791, spends allowance).
  Undo: `git revert d1d6f7b`.
- **14 Nov 2026** – Web app: Gallery, Taste and About pages (read-only; images still come from the git-ignored
  `generated/codex/`, nothing uploaded). New `GET /api/gallery`; `GET /api/styles` now returns whole style files.
  About text is a draft for my review. Undo: `git revert e6192df`.
- **14 Nov 2026** – Fractal exploration, computed route: `scripts/fractal.py` renders real Mandelbrot, Julia and
  Burning Ship fractals coloured with a style's palette (numpy + Pillow, no Codex allowance); samples in
  `generated/fractals/`. New style `fractal-worlds` (the 15th), built on the Psychedelic dreams palette; avoid list
  is just "busy noise" and "text and logos". Undo: delete `scripts/fractal.py`, `generated/fractals/` and
  `taste/styles/fractal-worlds.json`, then `build_taste.py .` Four Codex test images (git-ignored) in `generated/codex/2026-11-14-fractal-worlds`: five-hour 14→18 %, weekly 44→45 %.
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
