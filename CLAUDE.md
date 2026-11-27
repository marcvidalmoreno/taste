# taste – rules for Claude Code

Public repo `marcvidalmoreno/taste`. Commit with Marc's personal git identity, no Claude attribution.
`taste/` is a separate **private** repo (`marcvidalmoreno/taste-private`, ignored here; Marc, 23 Nov 2026): styles,
`taste.json`, Gem instructions. Style changes are committed and pushed there (`git -C taste ...`) with an entry in
`taste/README.md`'s changelog; never copy style text (prompts, prefer/avoid lines) into public files or commit
messages. Images stay local (`generated/`, `taste/data/`), backed up by Google Drive.

## How Marc works: the app is the interface (Marc, 21 Nov 2026)
- Marc gives feedback in the web app, in the element where he feels it (thumbs, remix, change the style,
  suggestions). Claude and Codex do the rest behind the scenes. Motto: tech out of sight.
- Recurring taste feedback (ratings, remix, style changes) lives in the app, in the element where he feels it;
  never give him tech steps (marking, saving, running scripts).
- A one-off decision that blocks the work: one question in chat, with the images or options visible and my pick
  as the first button. Build an app element only when the same decision will come back (Marc, 25 Nov 2026).
- Start the app with /launch-localhost (own console window), never with preview_start: the server must outlive
  the session (Marc, 23 Nov 2026).

## Pushing (Marc, 13 Nov 2026)
- Pushes to `origin/main` are automatic in this repo and in `taste/`: no need to ask.
- Before every push, check the staged diff for private data (other people's images, anything under
  `taste/data/`, `generated/codex/`, ratings, names, paths to personal folders). Never force-push.
- Several sessions share this checkout: commit with `git commit -- <your files>` and check
  `git diff --cached --name-only` right before, so another session's staged work never rides along (Marc, 23 Nov 2026).

## Who owns what
- Claude Code owns the taste: `taste/styles/*.json`, reading ratings, proposing edits. Style edits need
  Marc's OK once per set: propose all of them together, one OK applies the whole set (Marc, 15 Nov 2026); then rerun `scripts/build_taste.py` (never hand-edit `taste/taste.json`).
- Codex CLI generates images (`scripts/codex_run.py`, one fresh `codex exec` per image) and, for the web app,
  writes subjects and prompt rewrites (`scripts/codex_text.py`, read-only; Marc, 21 Nov 2026). It never edits
  taste files and never reads the notes for Claude.
- Marc can change a style from the web app ("Change the style", Marc, 21 Nov 2026): Codex proposes (read-only),
  Marc applies in the page; that apply is his OK. The app rewrites the style file, runs `build_taste.py` and logs
  before / after in `generated/codex/style-edits.json`, but never commits. When Marc says "commit my style edits":
  review `git -C taste status` and `diff` (a fork from the app is a new file, `how: fork` in the log), add an entry to `taste/README.md`'s changelog from that log, commit and push in
  `taste/`; the public README gets at most one generic line ("style edits committed"), no style text.
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

## Public gallery (taste-gallery, 23 Nov 2026)
- `../taste-gallery` holds the public site (`docs/`) and a slimmed starter kit (`kit/`). The site syncs by itself
  (`scripts/gallery_sync.py`, from post-commit hooks and the app's Publish button); reinstall the hooks with
  `gallery_sync.py --install-hooks` if they go missing.
- When `scripts/build_taste.py` or `scripts/pack.py` change, bring the same change to `taste-gallery/kit/scripts/`
  in the same session if it applies (a hook notes it in `generated/kit-update-needed.md`). The kit never holds
  Marc's styles.

## Every change
An undo line in the reply and a changelog entry in the README.
A change to the web app that adds, removes or renames something Marc can see or do also updates the in-app
Guide (`app/guide.html`, its section and "Last updated" date) in the same commit (Marc, 21 Nov 2026).
`app/about.html` holds the why, not features.
Run `.venv/Scripts/python -I scripts/e2e.py --working` (about 2 min, fake data, nothing real touched) before committing a change to `app/` or `scripts/`; the check also runs after each commit, and a failing result is printed when a session starts: fix it first.
A change that adds or changes something Marc can do in the app adds or updates its test in `tests/e2e/` in the same commit, and names it in `tests/e2e/coverage.json`; the pre-commit coverage guard blocks a write route or page with no entry (Marc, 27 Nov 2026).
