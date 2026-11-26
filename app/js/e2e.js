// The regression check's chip (26 Nov 2026). After each commit a test run (scripts/e2e.py) tries the whole app on a
// copy with fake data. While its last result is a failure this chip says so, calmly: a break was found and a fix is
// pending (Claude is told at the start of its next session). It leaves by itself once a check passes.
import { api } from './api.js';

const chip = document.getElementById('e2e-chip');

async function check() {
  try {
    const r = await api('e2e');
    chip.hidden = !r.failing;
    if (r.failing) {
      chip.replaceChildren(Object.assign(document.createElement('span'), {
        className: 'e2e-chip',
        textContent: 'Regression found · fix pending',
        title: `The automatic check found a break after commit ${r.sha} (${r.tests} test${r.tests === 1 ? '' : 's'}). It is reported to Claude, who fixes it first; this note goes away once a check passes.`,
      }));
    }
  } catch { chip.hidden = true; }   // an older server without the route: say nothing
}

check();
setInterval(check, 5 * 60 * 1000);
window.addEventListener('focus', check);
