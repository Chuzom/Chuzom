# PLAN — Adjudication & Mitigation (Iteration 1)

**Inputs:** `red-1-report.md` (7 findings), `red-2-report.md` (5 findings + 5 positives).
**Method:** each material finding independently reproduced by PLAN (not trusting auditor scripts).

## Dedup & root-cause grouping

| PLAN ID | Merges | Sev | Root cause | Status |
|---------|--------|-----|-----------|--------|
| **P-CAP-INJECT** | RED1-01 + RED1-02 | Critical | The TQ-007 free-local downgrade filter runs BEFORE precision-tier fronting and subject-specialist override, which re-prepend paid models. | **Reproduced** — paid `openai` billed under `enforce=hard` cap. Mine (introduced by TQ-007 placement). |
| **P-DRAFT** | RED2-01 (= CHZ-DRAFT-01) | Critical | Block-mode fabrication fires whenever `_is_context_dependent` false-negatives (measured 60%); a stateless draft replaces the user's turn. | Reproduced earlier + RED-2's battery. Fix: block only in zero-Claude (proposed) — makes the gate's FN rate irrelevant for the fabrication risk. |
| **P-CLAIMS** | RED2-05 | High | "60–90%" still written into 3 IDE-config templates; G6 guard scans only pyproject+README. | Reproduced. Gap in my CHZ-AUD-010 fix. |
| **P-PRIVACY** | RED2-04 | High | `CHUZOM_SESSION_CONTEXT=local` gate hardcodes `("openai","gemini")`; Perplexity (all research prompts) bypasses it → full history to paid API. | Trace-confirmed. |
| **P-LOCK** | RED1-09 | High | `_budget_lock()` per-event-loop under `ThreadingHTTPServer`+`asyncio.run()` → distinct lock per request → cap check-and-reserve not atomic; lost `_pending_spend` updates. | RED-1 reproduced (5 distinct locks, lost update). |
| **P-SPENDBLIND** | RED1-08 | High | `cost.log_usage` records only the winning attempt; billed-then-rejected paid attempts invisible to `get_daily_spend*` the cap-check reads. Compounds P-CAP-INJECT. | Structural trace. |
| **P-ROUTEID** | RED1-06 (+RED1-05) | High/Med | `auto-route` pending JSON never writes `route_id`, so per-route realization/override attribution collapses; `event_id=uuid4()` also defeats INSERT-OR-IGNORE dedup. Touches my EXT-204. | Reproduced. |
| **P-BOUNDARY** | RED1-07 | Medium | `get_monthly_spend` UTC vs `get_daily_spend*` localtime → inconsistent cap windows; daily docstring says "UTC" but code says localtime. | SQL-confirmed. |
| **P-OBSERV** | RED2-02 | Medium | Downgrade not surfaced in `RouteResult` — user sees quality drop with no reason. | Source-confirmed. |
| **P-INSTALL2** | RED2-03 | Low | `scripts/install.sh` (orphan, undocumented) lacks the settings.json atomic/backup fix. | Source-confirmed. |

**Rejected/невozможно:** none rejected — all 12 findings hold. RED1-03/04 were withdrawn by RED-1 itself (unsubstantiated). `provider_from_model` closed clean.

## Release-blocker set (must fix to satisfy convergence rule: no open Critical/High, no core-promise Medium)
Criticals: **P-CAP-INJECT, P-DRAFT**. Highs: **P-CLAIMS, P-PRIVACY, P-LOCK, P-SPENDBLIND, P-ROUTEID**.
Core-promise Mediums: **P-BOUNDARY** (cap correctness), **P-OBSERV** (observability promise).

## Fix order (dependency-aware)
1. **P-CAP-INJECT** — move the free-local downgrade filter to AFTER all chain-mutation steps (precision-tier, subject-specialist, policy reorder), immediately before dispatch. One relocation fixes both RED1-01 and RED1-02. Acceptance: precision-prompt + org-specialist cases under cap → free/block, never paid.
2. **P-DRAFT** — `"auto"` render mode resolves to block only when `zero_claude`; else echo. Acceptance: outside zero-Claude, no `decision:block` fabrication regardless of `_is_context_dependent`.
3. **P-CLAIMS** — drop the magnitude claim from the 3 templates; broaden G6 guard to scan `src/chuzom/**` templates. Acceptance: guard fails if "60–90%" appears anywhere in shipped src.
4. **P-PRIVACY** — replace the provider allowlist with an inverted free-local check (block context to any non-`{ollama,codex,gemini_cli}` provider under `local`); document that `local` affects history only, not routing destination. Acceptance: `local` + perplexity target → empty context.
5. **P-SPENDBLIND** — make the cap-check see all billed attempts (union rejected-attempt cost, or read the execution-ledger's per-attempt totals). Acceptance: after a rejected paid attempt, `get_daily_spend` reflects it.
6. **P-LOCK** — replace per-loop `asyncio.Lock` with a process-wide `threading.Lock` (or SQLite `BEGIN IMMEDIATE` reservation) for the cap critical section. Acceptance: N concurrent gateway requests at a 1-request cap → ≤1 paid dispatch.
7. **P-ROUTEID** — write a stable `route_id` in the pending JSON and thread it; derive a content-stable `event_id`. Acceptance: N overrides in a session attribute to N distinct route_ids; replayed event dedups.
8. **P-BOUNDARY** — make `get_monthly_spend` localtime-consistent with daily; fix the stale docstring.
9. **P-OBSERV** — add a `downgraded`/reason field to `RouteResult` (+ surface in hook/CLI).
10. **P-INSTALL2** — bring `scripts/install.sh` to parity or remove it.

Each fix: test-first (a test that fails pre-fix, passes post-fix), small commit, GATE re-runs the reproduction + regression suite.
