"""Runs last: the coverage ledger tells the truth. Every write route that tests/e2e/coverage.json says is tested
was really sent during this run (recorded in conftest.HITS). The fast half, that every route has an entry at all,
is scripts/coverage_guard.py, run by the pre-commit hook. Skipped on a partial run (-k) or when a test failed,
so a real break is not reported twice."""
import importlib.util
import json

import pytest

from conftest import COPY, HITS


def guard():
    spec = importlib.util.spec_from_file_location('coverage_guard', COPY / 'scripts' / 'coverage_guard.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_ledger_is_complete():
    found = guard().problems(root=COPY)
    assert not found, '; '.join(found[:5])


def test_tested_routes_were_really_sent(request):
    if request.config.getoption('keyword') or request.session.testsfailed:
        pytest.skip('partial run or an earlier failure')
    g = guard()
    routes = g.write_routes((COPY / 'scripts' / 'app.py').read_text(encoding='utf-8'))
    ledger = json.loads((COPY / 'tests' / 'e2e' / 'coverage.json').read_text(encoding='utf-8'))
    sent = {g.route_for(*k.split(' ', 1), routes) for k in HITS}
    unsent = sorted(r for r, v in ledger.items() if not v.startswith('skip:') and r not in sent)
    assert not unsent, f'named as tested in coverage.json but never sent during the run: {", ".join(unsent)}'
