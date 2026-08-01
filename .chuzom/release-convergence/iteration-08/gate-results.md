# Iteration 8 — GATE results (final budgeted round)

`pytest -m "not slow and not requires_ollama and not requires_api_keys"`

| Stage | Result |
|-------|--------|
| Before iter-8 (48fb535) | 6458 passed / 0 failed |
| After 6 fixes + new tests | **6466 passed / 0 failed / 0 error** (397s) |

- RED1-8-01 (hot-path spend threading) introduced NO regression: 0 router/budget/quota test failures.
- Backup hard-stop + `.bak` no-clobber + drain-lifespan + banner-honesty + postgres-warn all green.
- RED2-8-01 (uninstall `--host` completeness) DEFERRED to a manifest/registry refactor.

Verdict: FIX round complete, GATE-green. Clean-audit counter = 0. This was the 8th (final budgeted) iteration; no fully clean RED round was ever achieved.
