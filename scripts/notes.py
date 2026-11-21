"""Notes for Claude Code, written in the web app (21 Nov 2026): feedback on an image, a batch or a style.

Usage (from the project root):
  .venv/Scripts/python -I scripts/notes.py              # open notes, oldest first, with what they point at
  .venv/Scripts/python -I scripts/notes.py --all        # answered ones too
  .venv/Scripts/python -I scripts/notes.py done <id> "<answer>"   # mark answered; the app shows the answer

When Marc says "process my app notes": read the open notes, look at the images they point at, propose the
style edits as one set (CLAUDE.md: one OK per set), apply after his OK, rerun build_taste.py, then answer
each note with `done`. Notes live in generated/codex/claude-notes.json (git-ignored).
"""
import json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / 'generated' / 'codex' / 'claude-notes.json'


def load():
    try:
        return json.load(open(NOTES, encoding='utf-8'))
    except FileNotFoundError:
        return {'notes': []}


def save(d):
    tmp = NOTES.with_suffix('.tmp')
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, NOTES)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    d = load()
    if args[:1] == ['done']:
        if len(args) < 3:
            sys.exit('usage: notes.py done <id> "<answer>"')
        note = next((n for n in d['notes'] if n['id'] == args[1]), None)
        if not note:
            sys.exit(f'no note {args[1]}')
        note.update(status='done', answer=' '.join(args[2:]).strip(), answered=time.strftime('%Y-%m-%d %H:%M'))
        save(d)
        print(f'answered {args[1]}')
        sys.exit(0)
    show = d['notes'] if '--all' in args else [n for n in d['notes'] if n['status'] == 'open']
    if not show:
        print('no open notes')
    for n in show:
        where = ' / '.join(x for x in (n.get('style') and f'style {n["style"]}',
                                       n.get('batch') and f'batch {n["batch"]}',
                                       n.get('name') and f'image generated/codex/{n["batch"]}/{n["name"]}.png') if x)
        print(f'[{n["id"]}] {n["created"]}  {n["status"]}  {where or "general"}\n    {n["text"]}'
              + (f'\n    answer: {n["answer"]}' if n.get('answer') else ''))
