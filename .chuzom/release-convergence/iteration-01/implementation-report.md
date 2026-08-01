# Iteration 1 — Implementation Report (FIX)

Baseline: GREEN (6364 passed, 0 failed). RED-1 (7 findings) + RED-2 (5 findings + 5 positives) complete and adjudicated (`adjudication.md`). PLAN independently reproduced the material findings before FIX.

## Fixes landed this iteration (each: test-first, independent repro, small commit)

| PLAN ID | Sev | Commit | Root-cause fix | Acceptance |
|---------|-----|--------|----------------|-----------|
| **P-CAP-INJECT** (RED1-01+02) | Critical | `2fe57b1` | Moved the TQ-007 free-local downgrade filter to run LAST — after precision-tier fronting, subject-specialist, and bandit reorder — so no later step can re-prepend a paid model after the filter. | `test_cap_hit_precision_prompt_stays_free`, `test_cap_hit_org_specialist_stays_free`, `..._no_free_hard_blocks`. Raw repro: precision+cap+hard now dispatches ollama $0 (was openai billed). |
| **P-DRAFT** (RED2-01) | Critical | `5291546` | `_resolve_auto_render_mode()` — block mode (turn replacement) only in zero-Claude; else advisory echo. Makes `_is_context_dependent`'s ~60% false-negative rate irrelevant to the fabrication risk. | `test_draft01_no_block_outside_zero_claude.py` (invariant + documents the persisting FNs). |
| **P-CLAIMS** (RED2-05) | High | `b1f1cb1` | Removed "60–90%" from install_hooks IDE templates + cli.py (3) + bash-compress. Broadened the G6 guard to scan all `src/chuzom/**` — which surfaced 4 MORE occurrences the audit missed. | `test_no_fabricated_magnitude_claims_anywhere_in_src`; 0 occurrences remain. |
| **P-PRIVACY** (RED2-04) | High | `b4a2c9f` | Inverted the `local`-mode gate from a 2-provider allowlist to "block context to any provider NOT in {ollama,codex,gemini_cli}", at both gate sites. Perplexity (all research prompts) no longer receives history under `local`. | `test_red2_04_privacy_local_blocks_all_external.py` — blocks perplexity/openai/gemini/unknown/None; still delivers to free-local. |

## Also fixed during baseline stabilization (Iteration 0, pre-audit)
6 plugin-manifest version desyncs, env-daily-limit test semantics, 3 test-robustness bugs (env-leak, asyncio-loop, non-hermetic accumulator), 8 ruff unused-imports. All classified as branch ripple effects; baseline confirmed green.

## Remaining release-blockers (carried to next FIX cycle)
| PLAN ID | Sev | Status |
|---------|-----|--------|
| P-LOCK (RED1-09) | High | Open — replace per-event-loop `asyncio.Lock` with a process-wide lock / SQLite reservation for the cap critical section under the ThreadingHTTPServer gateway. |
| P-SPENDBLIND (RED1-08) | High | Open — cap-check reads only `usage` (winning attempt); rejected paid attempts invisible. Union rejected-attempt cost or read the per-attempt ledger. |
| P-ROUTEID (RED1-06/05) | High/Med | Open — write a stable `route_id` in auto-route pending JSON; derive content-stable `event_id`. |
| P-BOUNDARY (RED1-07) | Medium | Open — make `get_monthly_spend` localtime-consistent with daily; fix stale docstring. |
| P-OBSERV (RED2-02) | Medium | Open — surface downgrade in `RouteResult`. |
| P-INSTALL2 (RED2-03) | Low | Open — `scripts/install.sh` backup parity or removal. |

## Convergence status
Iteration 1 is PARTIAL: both Criticals + 2 of 5 Highs fixed and validated. The convergence rule (no open Critical/High) is not yet met — 3 Highs remain. A fresh RED-1/RED-2 round must run only after all blockers are fixed and GATE is green. Clean-audit counter remains 0.
