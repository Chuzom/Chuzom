# Iteration 5 — GATE results

`pytest -m "not slow and not requires_ollama and not requires_api_keys"`

| Stage | Result |
|-------|--------|
| Before iter-5 (d80ab4b) | 6408 passed / 0 failed |
| After 7 fixes + 5 new test files | **6428 passed / 0 failed / 0 error** (240s) |

- +20 tests: RED1-5-01 (4), RED1-5-03 (7), RED2-5 uninstall (3), RED2-5-03 preflight (4), claims-guard (+2).
- RED1-5-02 (`_pending_spend` single-release) introduced NO leak: zero budget/cache/router test regressions in the full suite — the exact class that would have broken had the removal leaked.
- Critical RED1-5-01 independently reproduced pre-fix (pending eroded to 0.00, C admitted past cap) and verified post-fix (pending stays 1.00, C refused).

Verdict: FIX round complete, GATE-green. Clean-audit counter = 0 (code changed). Convergence needs the next fresh RED round to come back clean, then a second clean round with no code change between.
