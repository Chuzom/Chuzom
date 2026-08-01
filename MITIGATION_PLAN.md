# Chuzom v1.0.1 Mitigation Plan — from the 2026-07-29 Audit (FAIL, 76 findings)

**Source of truth:** `~/Downloads/AUDIT_REPORT.md`, `SYNTHESIS.md`, `AUDIT_FINDINGS.json`, `CORRECTIONS_TO_FIRST_PASS.md`
**Audited commit:** `2b079b5` (≡ published tag `8c0bde3`, src-identical)
**Acceptance baseline:** `audit/2026-07-29/regression_tests/` — 5 fail on `2b079b5`, 2 controls pass. **v1.0.1 ships when all 7 pass and every gate below is green.**

**Core validation rule (inherited from the audit, non-negotiable):**
> Provider execution counts ONLY if a canary string from a recording fake provider appears in the hook's stdout. Never a banner, routing hint, `routing_decisions` row, status line, or successful classification.

---

## Phase 0 — Stop the bleeding (Day 1–2)

| # | Finding | Fix | Fact-based validation |
|---|---------|-----|----------------------|
| 0.1 | **CHZ-PKG-003** MCP server DOA on fresh install | Pin `mcp>=1.0.0,<2` in `pyproject.toml`; republish 1.0.1 to PyPI | Clean venv, **no `uv.lock`**: `pip install chuzom-router==1.0.1` → import `chuzom.server` OK, MCP server starts, responds to `tools/list`. Repeat via `uv pip` and `pipx` (audit reproduced the break 4/4 — validate all 3 installers) |
| 0.2 | **CHZ-SEC-07** command injection via `transcript_path` in `statusline-command.sh` | Pass hook fields via argv/env; never interpolate into `python3 -c` source | Re-run audit's end-to-end PoC (crafted filename) → command must NOT execute; add regression test |
| 0.3 | Yank/deprecate the broken 1.0.0 artifact on PyPI; note in CHANGELOG | — | PyPI shows 1.0.0 yanked; `requires_dist` of 1.0.1 shows `mcp<2` |

## Phase 1 — Fix the central defect: the routing latch (Day 2–5)

**CHZ-EXT-201/202/203** — three lines compose into permanent routing shutdown:
`_is_short_code_followup` (word count ≤15 only) → gate disables direct exec on `*-context-inherit` → `_save_last_route` re-saves the **inherited** `task_type`, re-arming forever. Measured: 2.32% sustained external execution; 0.0% from turn 10 in all 46 sessions.

| # | Fix | Fact-based validation |
|---|-----|----------------------|
| 1.1 | Require a real follow-up marker (anaphora/deixis/reference to prior turn), not word count alone | Word-boundary harness: the audit's 15/16-word boundary must disappear. Self-contained 10-word questions after a code turn → **canary-proven routed** |
| 1.2 | Never `_save_last_route` an inherited `task_type` — persist only fresh classifications | State pinpoint test: after `[code] + [short]`, `last_route_<sid>.json` must NOT contain `task_type="code"` from inheritance |
| 1.3 | Re-run the audit soak: 5,000 prompts, 46+ sessions, incl. one 500-turn session, `[code] + [simple]×12` pattern | **Gate G2 (below):** turn-10+ canary-proven execution rate > 0 in every session; `[code]+[simple]×12` → 12/12 routed (was 0/13); whole-run rate within 10pts of turn-1 rate |

## Phase 2 — Make the product able to see itself (Day 3–7)

| # | Finding | Fix | Fact-based validation |
|---|---------|-----|----------------------|
| 2.1 | **CHZ-EXT-204/CHZ-PRV-06** telemetry designed but unpopulated | Populate `realization_status`, `used_by_host`, `accepted` in `execution_events`; write `session_id` on direct rows | Soak run: **0 NULL** in these columns across all rows (was 4,887/4,887 NULL). A 97.7%-bypass run must be *visible* in telemetry |
| 2.2 | **CHZ-PKG-005/010** `verify` always exits 0 | Propagate return code; add a real canary route to `verify` | Broken install (`hooks not found`) → exit ≠ 0; healthy install → canary appears in verify output |
| 2.3 | **CHZ-EXT-209** banner names a model + savings for calls that never happened | Banner/status line only reports canary-confirmed executions | Latch scenario replay: no model name / token savings displayed on non-executed turns |

## Phase 3 — Security & data isolation (Week 1–2)

| # | Finding | Fix | Fact-based validation |
|---|---------|-----|----------------------|
| 3.1 | **CHZ-ST-004/005** cross-project secret leak via unscoped `semantic_cache`; global `result_cache` tier for research/query/generate | Scope every cache key by project; global tier opt-in | Replay audit PoC: project-B query after project-A secret → **cache MISS** (was HIT at similarity=1.000) |
| 3.2 | **CHZ-ST-003/002/001** fail-hard paths: read-only `~/.chuzom` crash, NUL `session_id`, path traversal → arbitrary file write | Guard `.unlink()`; reuse `session_store._sanitize()` in `auto-route.py` (one sanitizer, both paths) | `chmod -w ~/.chuzom` → hook exits 0 with fail-open hint; traversal payload with pre-existing dirs → write rejected |
| 3.3 | **CHZ-SEC-01/02/09, CHZ-ST-006** three drifted scrubbers; `transcript_*.jsonl` unscrubbed 0644; `pending_route_*.json` raw + never GC'd | **One shared scrubber module**, applied to every content store; 0600 everywhere; GC pending files | Canary-secret battery: 4 secrets as prompts + 1 in provider response → 0 unredacted occurrences in ANY file under `~/.chuzom`; all content stores 0600 |
| 3.4 | **CHZ-SEC-03/04/05/06** env blocklist leaks, unauthenticated local HTTP triggering model calls, dashboard serving own auth token, `CHUZOM_OLLAMA_URL` accepting `file://` | Allowlist env for child CLIs; auth on local servers; scheme/host validation | Targeted regression tests per finding (in `AUDIT_FINDINGS.json` each carries a required regression test) |

## Phase 4 — Wire-or-delete + claims (Week 2)

| # | Finding | Fix | Fact-based validation |
|---|---------|-----|----------------------|
| 4.1 | **CHZ-TQ-007/CHZ-EXT-003** `routing.yaml` `enforce`/`daily_caps` inert; also `max_tool_calls`, `max_children_concurrent`, `drain_bg_tasks()` | Wire them in, or delete config surface + docs | The repo's own `..._BUG` test inverted: rename to a positive test that FAILS if config is ignored |
| 4.2 | **CHZ-PY-001/002** `requires-python >=3.10` is false | Raise to `>=3.11` (cheaper than fixing `asyncio.timeout()` + `tomllib`) — and add 3.12 to CI matrix | CI matrix = declared support matrix, exactly |
| 4.3 | **CHZ-PKG-008/007** `settings.json` overwritten w/o backup; `install --help` performs real install | Backup before write; `--help` inert | Regression tests |
| 4.4 | **CHZ-PRV-02/01** `"gemini"` vs `"gemini_cli"` vocabulary mismatch strips paid fallback in every mode | Single provider-name enum, used everywhere | Provider-failure matrix rerun: paid fallback reachable when configured |
| 4.5 | Claims (**CLAIMS_VERIFICATION.md**): "every prompt", "always routes", "60–90% savings", "zero config", "no cloud", pull-IDE "Production" badges | Reword to measured numbers; split push vs pull guarantees everywhere; claim linter must scan `pyproject.toml` + CLI strings | Every quantified README claim links to a reproducible artifact in `bench/` or `audit/`; linter runs in CI |
| 4.6 | **CHZ-PY-004** aiosqlite daemon-thread fix reached 1 of 6 call sites | Fix the *class*: one connection factory, all 6 sites | grep: zero raw `aiosqlite.connect()` outside the factory; standalone exit-hang repro exits cleanly |

---

## Quality gates — permanent, in CI/release pipeline (prevent recurrence)

These target the six failure patterns the audit identified (parallel impls that drift; declared-but-never-wired; dev loop hiding shipped reality; tests that cannot fail; site-not-class fixes; marketing > mechanism).

**G1 — Fresh-resolver install gate (blocks publish).**
In `publish-pypi.yml`, BEFORE upload: build sdist+wheel → clean venv → install **without any lockfile** (fresh dependency resolution against live PyPI) → import all entry points → **start the MCP server and call `tools/list`**. This is exactly what `scripts/ci_install_smoke_test.sh` claimed to do but (a) fails at step 2 today, (b) is referenced nowhere in the pipeline, (c) skips MCP startup. Fix and wire it. *Would have caught CHZ-PKG-003.*

**G2 — Multi-turn sustained-routing gate (blocks release).**
Nightly + pre-release soak: ≥1,000 prompts, ≥20 sessions, mixed `[code]→[short]` sequences, one long session (≥100 turns), canary-proven scoring. Pass criteria: (a) turn-10+ external-execution rate > 0 in every session; (b) whole-run rate within 10pts of turn-1 rate; (c) `[code]+[simple]×N` ≥ N-1 routed. *Would have caught CHZ-EXT-201. Single-turn testing is structurally blind to session-age effects.*

**G3 — Telemetry completeness gate.**
After G2's soak: 0 NULL `realization_status`/`used_by_host`/`accepted`; 0 NULL `session_id` on direct rows; measured bypass rate from telemetry must match harness-measured rate ±2pts. *Makes any future latch field-visible.*

**G4 — Test-quality gate.**
(a) CI lints for assertion-free tests and `try/except Exception: pass` in tests (140 + 9 exist today); (b) coverage floor: `enforce-route.py` ≥ 70% (now 15%); (c) ≥1 test per routing path that executes an HTTP-faked provider and asserts on `.content` (today: 0 of 620); (d) hermetic fixtures must clear `CHUZOM_ENFORCE`/all `CHUZOM_*` env (CHZ-TQ-006).

**G5 — Security regression gate.**
The audit's `regression_tests/` become a permanent CI job: injection (SEC-07), traversal (ST-001), cache scoping (ST-004), scrubber battery (SEC-01), fail-open (ST-003). All must pass on every PR.

**G6 — Claims gate.**
Claim linter (fixed to match `%`/`×`, scan `pyproject.toml` + CLI strings) + rule: no quantified public claim without a linked, re-runnable benchmark artifact. Push vs pull guarantee split enforced in README structure.

---

## Sequencing & effort

| Window | Work | Exit criterion |
|--------|------|----------------|
| Day 1–2 | Phase 0 | 1.0.1 on PyPI installs + MCP starts on all 3 installers |
| Day 2–5 | Phase 1 + G2 harness | Soak passes G2 |
| Day 3–7 | Phase 2 + G3 | Telemetry non-NULL; verify exits non-zero on broken install |
| Week 1–2 | Phase 3 + G5 | All security regression tests green |
| Week 2 | Phase 4 + G1/G4/G6 wiring | All 7 audit regression tests pass; full gate suite green |

**Definition of done for v1.0.1:** all 6 criticals closed with their named validations, all 6 gates wired into CI, `audit/2026-07-29/regression_tests/` 7/7 green, README claims match measured numbers.

Items 2.1 (telemetry) and 4.5 (claims) are the two the audit flagged as *preventing recurrence* — everything else is repair. Do not deprioritize them.
