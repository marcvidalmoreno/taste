# taste – rules for Claude Code

Public repo `marcvidalmoreno/taste`. Commit with Marc's personal git identity, no Claude attribution.

## Pushing (Marc, 13 Nov 2026)
- Pushes to `origin/main` are automatic in this repo: no need to ask.
- Before every push, check the staged diff for private data (other people's images, anything under
  `taste/data/`, `generated/codex/`, ratings, names, paths to personal folders). Never force-push.

## Who owns what
- Claude Code owns the taste: `taste/styles/*.json`, reading ratings, proposing edits. Each style edit needs
  Marc's OK; then rerun `scripts/build_taste.py` (never hand-edit `taste/taste.json`).
- Codex CLI only generates images (`scripts/codex_run.py`, one fresh `codex exec` per image) and never edits taste files.
- Files are the hand-off: images, `generated/codex/runs.csv`, `generated/codex/ratings.csv` (all git-ignored).

## Codex runs
- One attempt and one recovery per failure, then stop and report. Don't view each image: one contact sheet
  (`scripts/sheet.py`) per batch.
- Ask Marc before anything that would use a large share of the Codex allowance (see "Allowance" in the README).
- Each run ends with a link to the batch folder and the rating command.

## Every change
An undo line in the reply and a changelog entry in the README.
