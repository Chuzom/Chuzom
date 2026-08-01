# Iteration 4 — GATE results

## G-suite (full pytest, hermetic markers)
`pytest -m "not slow and not requires_ollama and not requires_api_keys"`

| Run | Commit / tree | Result |
|-----|---------------|--------|
| baseline (pre-iter4) | `c025f68` | **6404 passed, 0 failed** (237s) |
| iter4 first GATE | `7c513bc` | 11 failed, 6398 passed, 1 error (214s) |
| iter4 re-run (determinism) | `7c513bc` | 11 failed — **identical set** → deterministic, not flaky |
| after RED1-4-01 code revert | working tree | 11 failed — **same set** → code patch exonerated |
| after test-leak fix | working tree | **6408 passed, 0 failed, 0 error** (296s) |

## Root cause of the 11-test regression
NOT the RED1-4-01 code patch (identical failures with/without it). The new
`tests/test_red1_3_reservation_leaks.py::test_no_double_decrement_on_success`
drove 8 concurrent **real** `route_and_call`s with an unmocked dispatch; its
fire-and-forget `_BG_TASKS` (ledger/session-spend/telemetry) were never drained
or DB-isolated, leaking aiosqlite connections into later tests. All 11 failing
tests passed in isolation — the signature of cross-test global-state pollution.

## Fix (test hygiene, not product code)
- tmp `CHUZOM_DB_PATH` + `chuzom.config._config` reset around each drive;
- mocked `semantic_cache.check` miss so the real cache read can't open the DB;
- `await router.drain_bg_tasks()` in the drive `finally`;
- removed the 8-concurrent success-path test (validated a deferred invariant and
  was the pollution source). 3 hermetic tests remain (RED1-3-01/02, RED1-4-02).

## Verdict
GATE-green restored. RED1-4-01 deferred to the single-owner reservation refactor.
Iteration-4 changed code (RED1-4-02 + rebrand/claims) → clean-audit counter = 0.
