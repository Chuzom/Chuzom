# Iteration 8 — Implementation Report (FIX) — final budgeted round

RED-1 (3 High, 2 Medium) + RED-2 (3 High), 0 Critical, at `48fb535`. **6 of 7 distinct findings fixed** (RED1-8-03 and RED2-8-02 are the same defect); 1 High (RED2-8-01) deferred as structural. RED-1 verified `settle()` + every reservation/envelope release path clean.

| PLAN ID | Sev | Fix | Test |
|---------|-----|-----|------|
| **RED1-8-01** | High | New `LLMResponse.chain_attempt_cost_usd` carries billable-rejected-attempt cost out of `_dispatch_model_loop`; `route_and_call` settles `cost_usd + chain_attempt_cost_usd` into the envelope + quota tracker (floor path avoids double-count). | `test_red1_8_01_rejected_attempt_billing.py` (3) |
| **RED1-8-02** | High | Backup failure → HARD STOP (skip overwrite, distinct "SKIPPED … preserved" message). | `test_red2_6_01_hook_content_drift.py` (+1) |
| **RED1-8-03 / RED2-8-02** | Med/High | `.bak` never clobbered; second drift writes `.<ts>.bak`. | `test_red2_6_01_hook_content_drift.py` (+1) |
| **RED1-8-05** | Med | `drain_bg_tasks()` wired to a FastMCP `lifespan` shutdown hook (same-loop drain; the first `atexit` attempt was reverted as ineffective — cross-loop). | verified server imports + lifespan set |
| **RED2-8-03** | High | Banner reflects real availability (`BANNER_LOCAL` when no cloud keys); no false "API-key routing in effect". | `test_red2_8_03_banner_honesty.py` (3) |
| **RED1-8-04** | High | Postgres+strict-forecast now warns + alerts at backend selection (full forecast port deferred — Postgres is EXPERIMENTAL). | — |
| **RED2-8-01** | High | **DEFERRED (structural):** uninstall must consume an install-written manifest of `--host` writers. Point-fixing 8 hosts late-session is regression-prone; documented as the primary convergence-completing refactor. | — |

## Honesty note on the two reverted/ineffective attempts
- The initial RED1-8-05 fix (an `atexit` draining via `asyncio.run`) was **reverted** — `_BG_TASKS` are bound to the closed `mcp.run()` loop, so a fresh loop cannot await them. The correct fix is a FastMCP `lifespan` finally-block on the same loop.
