# RED-7b — Test & CI Audit (v1.1.1, SHA c2c2882)

Worktree: `/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882`
Interpreter: `.venv-audit/bin/python` (3.11.15). Env isolation: `CHUZOM_HOME` pointed at scratch dirs under the worktree for every run; `~/.chuzom` and `~/.claude` were never touched.

## Q1 — Does the suite pass at this SHA?

Full run: `.venv-audit/bin/python -m pytest -q -p no:randomly --timeout=60` (no shell `timeout`/`gtimeout` binary available on this host — ran to completion instead, wall clock ~15 min).

The process reached the `100%` progress marker, printed the scenario-report line ("24 scenarios, 24 passed"), and began the warnings summary — then **the process exited without ever printing pytest's final result banner** ("N passed in Xs"). This matches the exact "aiosqlite exit-hang" failure mode `.github/workflows/ci.yml` has a documented watchdog for (kill after wait, read junit as fallback) — I did not pass `--junit-xml` so I could not recover a written junit file, but I recovered the full result set another way:

Reconstructed from the captured dot-stream (`grep -E '^[.sxXF ]+\[.*%\]$'`), counting markers:
- **6706 passed** (`.`)
- **172 skipped** (`s`)
- **1 xfail** (`x`)
- **0 failed**, **0 errors** (no `F`/bare `E` marker anywhere in the entire log)
- Total = 6879, which exactly matches `pytest --collect-only -q` → **6879 tests collected**. The reconciliation is exact, so the pass/fail verdict is trustworthy even without the missing final line.

**Verdict: suite passes, 0 failures, at this SHA** — but the run process itself hangs/never cleanly exits, which is a real (already-known, already-mitigated-in-CI) reliability defect, not a red herring. Ran the FULL suite, not a subset.

## Q2 — Skips: how many, why?

Static markers in `tests/`: 2 `@pytest.mark.skip`, 15 `@pytest.mark.skipif`, 1 `@pytest.mark.xfail`, 32 inline `pytest.skip(...)` calls, 9 `importorskip`. Runtime skip count from the full run: **172**.

Top skip reasons (by grep frequency):
| Reason | Count |
|---|---|
| tiktoken not installed | 2 |
| helm not installed | 2 |
| No test prompts available | 4 |
| `_classify_complexity` not importable from auto-route.py | 3 |
| No live auto-route hook installed locally | 2 |
| Agno not installed | 2 |
| Textual not installed (optional dependency) | 1 |
| symlinks not supported on this platform | 1 |
| No `~/.claude/settings.json` on this machine | 1 |
| `.rules` file not shipped at root | 1 |

Categories: optional-dependency gated (tiktoken, helm, Agno, Textual — expected, these are extras), platform gated (symlinks — expected on macOS/Windows), and **environment/fixture gated** (no live hook installed locally, no test prompts, no local `~/.claude/settings.json`) — these last ones mean some code paths are only exercised when a specific local dev environment exists, which is worth flagging but is not a hidden-defect pattern by itself.

**No API-key-gated skips were found** (`grep -in 'skipif.*API_KEY\|skip.*no.*api.*key' tests/` → empty) — good, nothing in this suite silently no-ops in CI for lack of a secret.

## Q3 — Do release gates fail when the defect is present? (fault injection, all done directly on worktree files, restored + verified clean after each)

**(a) Savings clamp (`summary.py:217`, `max(0.0, baseline - total)`).** No injection needed — the clamp is the current, undisputed production behavior. Searched for a test asserting *negative* net savings would be surfaced by this code path: **none exists**. Worse — `tests/test_session_report.py::test_savings_never_negative_in_display` explicitly pins the clamped/misleading behavior as correct ("Savings should be clamped to 0 (never show negative savings)" / asserts `"0% saved"` when cost > baseline). Ran it: **PASSES**, confirming the clamp-and-hide behavior is the *intended, tested* contract for `chuzom summary` (feeds `cli_summary` in `cli.py:866`).
   Important nuance: three OTHER modules — `chuzom.cost.calc_savings`, `chuzom.contract_gates.compute_receipt` (`tests/test_contract_gates.py:228 assert receipt.savings_usd < 0`), and the bench-savings gate (`tests/test_bench_savings.py::test_negative_savings_fails_gate15_honestly`) — DO correctly compute and gate on negative net savings, and are explicitly tested for it. So the codebase already knows how to be honest about overspend at the gate/contract layer, but the user-facing `chuzom summary` display layer independently clamps and hides it, and a test locks that inconsistency in as "working as intended."
   **Finding: real, but not "zero coverage" as framed — it's a layer-specific gap with a test that actively defends the wrong behavior for the one surface users actually read.**

**(b) Stale pricing.** Changed `BASELINE_PRICING["opus"]["input"]` in `src/chuzom/cost.py` 15.0 → 999.0 (66x). Ran `tests/test_savings.py tests/test_cost.py tests/test_bench_savings.py` (98 tests) — **all green, 0 failures**. No test asserts the actual numeric value of `BASELINE_PRICING["opus"]`. The one hit for "opus...15.0" (`tests/test_test_delta.py:174 assert OPUS_INPUT_PER_M == 15.0`) checks an unrelated, independently-hardcoded duplicate constant in `src/chuzom/test_delta.py:47`, not `cost.BASELINE_PRICING` — so it wouldn't catch this drift either. **Gate does NOT catch stale pricing. Confirmed defect.**

**(c) Wrong tool name.** Changed `tool_surface.py` `CORE_TOOLS` entry `"llm_query"` → `"llm_bogus_xyz"`. Ran `scripts/lint_tool_surface.py` → `CHZ-SURF-01: clean (409 files checked)`, exit 0. Ran `tests/` matching `tool_surface` (`test_tool_tiers.py` + `test_tool_surface.py`, 106 tests) — **all green**. Root cause: `lint_tool_surface.py`'s actual job (per its own docstring) is "no emitter may hardcode a tool name into prose" — a self-consistency lint, not a check against the MCP server's real registered tool names. Neither it nor the unit tests validate `CORE_TOOLS`/`EMITTABLE_TOOLS` membership against ground truth. **Gate does NOT catch a bogus/renamed canonical tool name. Confirmed defect.**

**(d) Ledger drop.** Made `execution_ledger.record_event()` `return False` unconditionally (before the try body). Ran `tests/test_execution_ledger.py` — **16 of ~20 tests FAILED immediately** (e.g. `test_rejected_attempt_is_recorded_and_counted`, `test_accepted_only_route`, `test_reconcile_matches_canonical`, `test_property_route_actual_equals_sum_of_attempts`). **This is a real, working gate** — it correctly goes red.

All four mutations were applied directly to worktree source, tested, then `git checkout --` restored; `git status --porcelain` confirmed empty after every one.

**Summary: 2 of 4 gates are proven blind (b, c); 1 is a defended-wrong-behavior rather than a blind spot (a); 1 works correctly (d).**

## Q4 — Does CI hide failures?

`continue-on-error: true` / `|| true` hits, checked in context — none mask actual test-suite results:
- `ci.yml` (7 hits) — all on the `astral-sh/setup-uv@v4` step with an explicit "Retry uv setup" fallback step immediately after (transient network resilience, not test masking).
- `security.yml` (3 hits) — `pip-audit --strict` (dependency CVE scan, explicitly documented as "REPORT-ONLY... a hard gate would break CI weekly on deps we don't control"), and two CodeQL/bandit SARIF-upload steps (403 without Code Scanning enabled in repo settings — documented, non-test). Note bandit's *scan* itself also has `|| true` on the command (`security.yml:62`) — findings never fail CI at all currently, only get logged; this is pre-existing tech debt the file's own comments flag for ratcheting later, not a hidden bug.
- `publish-pypi.yml` (1 hit) — same uv-setup retry pattern.
- The two `|| true` in `ci.yml:241,260` are on `kill $PYTEST_PID` inside the documented exit-hang watchdog — this path correctly `exit 1`s on real failures (verified by reading the surrounding logic); the `|| true` only suppresses "process already dead" noise from the kill itself.

**No masking of the actual pytest gate was found.** Security scanning is intentionally report-only (documented debt, not concealment).

Python matrix: `ci.yml:171` → `python-version: ["3.11", "3.12", "3.13", "3.14"]` — matches README's "3.11–3.14" claim exactly.

## Q5 — Does the release pipeline test the shipped artifact?

Built with `uv build --wheel` (the pinned venv's Python had no `pip`/`build` module — used the project's own `uv`, consistent with the repo's tooling). Wheel built clean: `chuzom_router-1.1.1-py3-none-any.whl`, 424 files.

Checked each named asset class against source-tree counts — **all present, counts match exactly**:
| Asset | Source count | Wheel count |
|---|---|---|
| `src/chuzom/rules/*` | 13 | 13 |
| `src/chuzom/data/benchmarks.json` | present | present |
| `src/chuzom/prompts/*` | 3 | 3 |
| `src/chuzom/static/*` | 1 | 1 |
| `src/chuzom/banner_art.txt` | present | present |

Non-Python asset extensions (`.md/.json/.txt/.sh`) in wheel: 26 files. **Nothing missing.**

`smoke-test.yml` (runs on every push/PR to `main`) installs via `pip install -e ".[dev]"` / `uv pip install -e ".[dev]" --system` — **editable install from the source checkout, NOT the built wheel.** The actual wheel is only installed and smoke-tested in `publish-pypi.yml`'s **G1 gate** (`pip install dist/*.whl` into a clean venv, fresh dependency resolution, then imports `chuzom.server` and lists MCP tools) — but that workflow only runs on a `v*` tag push (i.e., at release time, not on every PR). G1's own comment states its origin: it exists because v1.0.0 shipped with an unbounded `mcp>=1.0.0` that resolved to a breaking `mcp` 2.0.0 in the wild, undetected until then. So packaging correctness is real-tested, but late (release time only) and narrowly (import + tool-list, not the full pytest suite against the installed wheel).

## Verdict

**Does a green CI run on this repo actually mean anything?** Mostly yes for correctness (pytest is a real, unmasked gate; the ledger-drop fault was caught instantly) but **no for the specific claims the audit was asked to probe** — a wrong canonical tool name and a wildly stale baseline price constant can land, merge, and ship with 100% green CI, and the one user-facing dishonesty pattern (clamped savings hiding overspend) is not just uncaught, it's asserted as correct by a test.

## Findings

```
ID: RED7-01
Severity: HIGH
Confidence: PROVEN
Area: cost/pricing correctness
Title: BASELINE_PRICING has no value-correctness test — a 66x stale price passes every gate
Claim-Invariant violated: "savings numbers are trustworthy / gated"
Observed: Changed BASELINE_PRICING["opus"]["input"] 15.0 → 999.0 in src/chuzom/cost.py; ran tests/test_savings.py, tests/test_cost.py, tests/test_bench_savings.py (98 tests) — 0 failures.
Expected: A test pinning BASELINE_PRICING values (or cross-checking against a pricing source of truth) so drift/typos are caught.
Why it matters: This dict directly feeds every "savings" number shown to users and reported in the Gate-15/16 acceptance tests. A copy-paste or stale-pricing-update error is invisible to CI.
Reproduction: sed -i 's/"opus":   {"input": 15.0/"opus":   {"input": 999.0/' src/chuzom/cost.py && pytest tests/test_savings.py tests/test_cost.py tests/test_bench_savings.py
Evidence: worktree run 2026-08-11, all green after mutation; restored via git checkout, git status clean.
Root cause: no test asserts BASELINE_PRICING numeric contents; the one test that checks "opus...15.0" (test_test_delta.py:174) checks an unrelated duplicated constant (OPUS_INPUT_PER_M in src/chuzom/test_delta.py:47), not this dict.
Why existing tests missed it: tests exercise the calc_savings/receipt/gate *logic* with mocked or independently-supplied cost inputs, never assert the pricing table's own values.
Blast radius: every savings % and $ figure shown in chuzom summary, dashboards, and release gate acceptance criteria (gate15/16) that route through this table.
Systemic fix: add a pinned-value test for BASELINE_PRICING (and MODEL_COST_PER_1K / OPUS_INPUT_PER_M) with a comment requiring update-in-lockstep when vendor pricing changes; consider deriving OPUS_INPUT_PER_M from BASELINE_PRICING instead of duplicating it.
Regression test: assert BASELINE_PRICING == {"haiku": {...}, "sonnet": {...}, "opus": {"input": 15.0, "output": 75.0}} (or narrower per-key asserts with an explanatory comment).
Release blocking: YES
```

```
ID: RED7-02
Severity: HIGH
Confidence: PROVEN
Area: tool-surface / MCP registration
Title: lint_tool_surface.py and tool_surface tests do not validate CORE_TOOLS/EMITTABLE_TOOLS names against reality
Claim-Invariant violated: "CHZ-SURF-01 guards the tool surface"
Observed: Renamed "llm_query" → "llm_bogus_xyz" inside CORE_TOOLS (src/chuzom/tool_surface.py:74). scripts/lint_tool_surface.py reported "CHZ-SURF-01: clean (409 files checked)", exit 0. tests/test_tool_tiers.py + tests/test_tool_surface.py (106 tests) — 0 failures.
Expected: Some check (lint, unit test, or CI step) that verifies every name in CORE_TOOLS/ROUTING_TOOLS/EMITTABLE_TOOLS is a real MCP-registered tool.
Why it matters: lint_tool_surface.py's own docstring describes exactly this failure class ("A hint that names one of them produces Error: No such tool available; the caller then does the work on the expensive model... The failure is invisible in every metric we have") — but the lint only checks that emitters resolve names through chuzom.tool_surface before display, not that the canonical names themselves are valid. A single bad edit to the source-of-truth tuple defeats the entire protection this lint exists for.
Reproduction: sed -i '74s/"llm_query"/"llm_bogus_xyz"/' src/chuzom/tool_surface.py && python scripts/lint_tool_surface.py && pytest tests/test_tool_tiers.py tests/test_tool_surface.py
Evidence: worktree run 2026-08-11; restored via git checkout, git status clean.
Root cause: lint validates hardcoding-in-prose (a syntactic/AST check), not semantic correctness of the tool-name constants against the actual MCP server registration (chuzom.server / list_tools()).
Why existing tests missed it: tests exercise tier composition/membership logic using the module's own constants as ground truth — circular, so a bad constant propagates cleanly through everything downstream.
Blast radius: any routing hint or emitted door name derived from CORE_TOOLS/ROUTING_TOOLS with a typo/bad rename ships silently; matches the exact incident class (CHZ-SURF-01) this file was built to prevent, just one level removed from where it protects.
Systemic fix: add a test that calls chuzom.server (or the fastmcp app used in publish-pypi.yml's G1 gate) and asserts CORE_TOOLS | ROUTING_TOOLS | EMITTABLE_TOOLS ⊆ {registered tool names}.
Regression test: async def test_core_tools_are_actually_registered(): tools = await mcp.list_tools(); assert CORE_TOOLS <= {t.name for t in tools}.
Release blocking: YES
```

```
ID: RED7-03
Severity: MEDIUM
Confidence: STRONG EVIDENCE
Area: summary/reporting honesty
Title: chuzom summary clamps and hides negative savings; the one test on that path asserts the misleading behavior is correct
Claim-Invariant violated: "savings reporting is honest, never fabricated" (explicitly the standard other savings paths meet, per tests/test_bench_savings.py::test_negative_savings_fails_gate15_honestly and tests/test_contract_gates.py::test_receipt_no_savings_when_expensive)
Observed: src/chuzom/summary.py:217 data.savings_usd = max(0.0, baseline - total). tests/test_session_report.py::test_savings_never_negative_in_display asserts the displayed text shows "0% saved" (not a negative number) when actual cost exceeds baseline. This SessionSummaryData feeds cli_summary (src/chuzom/cli.py:866), the user-facing `chuzom summary` command.
Expected: Given that cost.calc_savings, contract_gates.compute_receipt, and bench_savings.evaluate_savings all correctly surface negative net savings and are tested for it, the top-level session summary a user actually reads should not independently clamp-and-hide the same fact.
Why it matters: A user whose session cost more than the baseline sees "$0.00 saved (0%)" — indistinguishable from "no routing occurred" — instead of a negative number. This is a real inconsistency between what the codebase's own gate layer considers honest and what its most-visible display shows.
Reproduction: pytest tests/test_session_report.py -k test_savings_never_negative_in_display (passes, confirming clamp-and-hide is the tested/intended contract for this path).
Evidence: read directly, no mutation needed — this is standing behavior, not an injected fault.
Root cause: summary.py's aggregation was written/updated independently of the later "Fix #3 — drop max(0.0,...) clamp" work referenced in tests/test_savings.py's TestNegativeSavingsAndRoutingOverhead docstring, which fixed the identical pattern in chuzom.cost.calc_savings but didn't propagate to summary.py.
Why existing tests missed it: the fix landed and was tested at the cost.py/contract_gates.py/bench_savings.py layer; summary.py was never revisited, and its own test locks in the pre-fix behavior as intentional.
Blast radius: chuzom summary CLI output only (did not find other consumers of SessionSummaryData.savings_usd in a narrow grep of src/chuzom/cli.py); does not affect gate15/16 release-blocking acceptance criteria, which use the honest evaluate_savings path.
Systemic fix: either (a) change summary.py to report and label negative savings explicitly (e.g. "-$X (overspend)"), consistent with the rest of the codebase's stated philosophy, or (b) if hiding negative numbers in this specific human-facing summary is a deliberate UX decision, rename the test and add an adjacent explicit "overspend" line so the number isn't simply dropped.
Regression test: a session with cost > baseline should show a non-zero negative indicator somewhere in cli_summary output, not silently read as break-even.
Release blocking: NO (cosmetic/UX honesty issue, not a release-gate defect — the actual release gates (15/16) use the correct, unclamped path)
```

```
ID: RED7-04
Severity: LOW
Confidence: STRONG EVIDENCE
Area: test infra / CI reliability
Title: Full local pytest run reaches 100% then hangs on exit without emitting the final result summary
Claim-Invariant violated: none (this is infra flakiness, not a correctness gap) — noted because it directly affects auditability
Observed: `.venv-audit/bin/python -m pytest -q -p no:randomly --timeout=60` (full 6879-test suite) printed 100% progress and the scenario-report line, then the process exited without ever printing pytest's "N passed in Xs" banner. Reconstructed the true result from the dot-stream instead (6706 passed / 172 skipped / 1 xfail / 0 failed, reconciling exactly to the 6879 collected count).
Expected: n/a — this is the exact, already-documented "aiosqlite exit-hang" class that ci.yml's watchdog (lines ~205-260) exists to work around (kill + read junit fallback). Confirms the documented issue is real and still present at this SHA, not just theoretical.
Why it matters: locally reproducing "does the suite pass" requires either --junit-xml or careful dot-stream reconstruction; a naive `pytest ... ; echo $?` on this host would report a nonzero/hung exit despite 0 real failures.
Reproduction: run the full suite without --junit-xml and watch for the missing final summary line.
Evidence: /Users/yaliandrona/Projects/Chuzom/.chuzom/zero-tolerance-audit/evidence/red7/q1_pytest_full.log
Root cause: known aiosqlite background-thread-on-exit issue (see tests/test_py004_aiosqlite_daemon.py and ci.yml's own comments).
Why existing tests missed it: it's not a test gap — it's already known and specifically mitigated in CI (not in ad hoc local runs, which is exactly the situation I was in).
Blast radius: local dev / audit reproducibility only; CI's watchdog already handles it.
Systemic fix: none needed beyond what exists; consider always passing --junit-xml in documented "how to run the full suite locally" instructions so this doesn't surprise auditors/contributors.
Regression test: n/a (already covered by CI watchdog + test_py004_aiosqlite_daemon.py).
Release blocking: NO
```

## Sign-off

`git status --porcelain` in the worktree: **EMPTY** (confirmed after every fault-injection restore and at final sign-off).

Q1–Q5 not fully answered from first-hand testing: none — all five were directly reproduced/verified in this session (Q1 via full run + dot-stream reconciliation, not a subset).
