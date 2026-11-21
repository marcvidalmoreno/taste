# taste – rules for Claude Code

Public repo `marcvidalmoreno/taste`. Commit with Marc's personal git identity, no Claude attribution.

## How Marc works: the app is the interface (Marc, 21 Nov 2026)
- Marc gives feedback in the web app, in the element where he feels it (thumbs, remix, change the style,
  suggestions). Claude and Codex do the rest behind the scenes. Motto: tech out of sight.
- Never ask him in chat to decide image or style changes. A decision that is his goes into the app as a calm,
  one-click element; no tech steps (marking, saving, running scripts) on his side.

## Pushing (Marc, 13 Nov 2026)
- Pushes to `origin/main` are automatic in this repo: no need to ask.
- Before every push, check the staged diff for private data (other people's images, anything under
  `taste/data/`, `generated/codex/`, ratings, names, paths to personal folders). Never force-push.

## Who owns what
- Claude Code owns the taste: `taste/styles/*.json`, reading ratings, proposing edits. Style edits need
  Marc's OK once per set: propose all of them together, one OK applies the whole set (Marc, 15 Nov 2026); then rerun `scripts/build_taste.py` (never hand-edit `taste/taste.json`).
- Codex CLI generates images (`scripts/codex_run.py`, one fresh `codex exec` per image) and, for the web app,
  writes subjects and prompt rewrites (`scripts/codex_text.py`, read-only; Marc, 21 Nov 2026). It never edits
  taste files and never reads the notes for Claude.
- Marc can change a style from the web app ("Change the style", Marc, 21 Nov 2026): Codex proposes (read-only),
  Marc applies in the page; that apply is his OK. The app rewrites the style file, runs `build_taste.py` and logs
  before / after in `generated/codex/style-edits.json`, but never commits. When Marc says "commit my style edits":
  review `git diff taste/`, add a changelog entry from that log, commit and push.
- Distil runs in the web app too (Codex proposes per style, Marc applies; 21 Nov 2026). "Distil my ratings" in chat
  still works the old way, and when Codex proposals miss what the images show, that is the moment to offer it
  (parked options 2 and 3: the "taste – distil automation" doc).
- "Process my app notes": `scripts/notes.py` lists the notes Marc left in the web app; look at what each points
  at, propose the style edits as one set, apply after his OK, then answer each with `notes.py done <id> "..."`.
- Files are the hand-off: images, `generated/codex/runs.csv`, `generated/codex/ratings.csv` (all git-ignored).

## Codex runs
- One attempt and one recovery per failure, then stop and report. Don't view each image: one contact sheet
  (`scripts/sheet.py`) per batch.
- Ask Marc before anything that would use a large share of the Codex allowance (see "Allowance" in the README).
- Each run ends with a link to the batch folder and the rating command.

## Every change
An undo line in the reply and a changelog entry in the README.
