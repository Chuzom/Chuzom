# PLAN — Adjudication (Iteration 2)

Fresh RED-1 (arch) + RED-2 (customer) audited HEAD 509b03f independently. **6 findings, all in Iteration-1's own fixes** — the fresh round did its job. Every material one independently re-reproduced by PLAN.

| PLAN ID | Merges | Sev | Root cause | PLAN repro |
|---------|--------|-----|-----------|-----------|
| **Q-SMART-PAID** | RED2-2-01 | **Critical** | TQ-007 `smart/soft` no-free branch never restricts the chain — it "falls through" to the already-queued PAID provider (openai), a silent metered call under an exceeded cap. My own test asserted the wrong behavior. | Confirmed: test asserts `resp.provider=="openai"` under smart+cap. |
| **Q-RESLEAK** | RED1-2-02 | High | The cap hard-block `raise` (and now the smart-block) exits before `_dispatch_model_loop`'s reservation release, leaking `_pending_spend` forever (no try/finally). | RED-1 live: 0.0→0.005→0.010→0.015 across 3 blocks. |
| **Q-MONTHLY** | RED1-2-01 | High | P-SPENDBLIND added rejected-attempt cost to daily but NOT `get_monthly_spend` — monthly cap blind to billed-rejected spend. | Confirmed: daily=50.0, monthly=0.0. |
| **Q-ROUTEID** | RED1-2-03 | Medium | route_id uses `int(time.time())` (1-s resolution); two same-session same-tool decisions in one second collide → second `route_realized` dropped by INSERT OR IGNORE. | Confirmed: identical route_id same-second. |
| **Q-OBSERV2** | RED2-2-02 | Medium | P-OBSERV set `cap_downgraded` on LLMResponse but `summary()`/`header()` (what the user sees) never render it. My test checked the field, not the output. | Source-confirmed. |
| **Q-MSG** | RED1-2 Low note | Low | Daily-cap error says "today UTC" but the query uses localtime. | Source-confirmed. |
| **Q-DRAFTFN** | RED2-2-03 | Low | 4/9 diagnostic prompts evade context+tool-need gates → text-only draft. MITIGATED: P-DRAFT makes it echo (not block) + response_formatter disclaimer. | Accept as documented residual; not a bare fabrication path post-P-DRAFT. |

## Interaction check (per PLAN mandate)
Q-SMART-PAID and Q-RESLEAK share the no-free branch. The fix for Q-SMART-PAID adds a *new* block/raise (smart with no Claude), which would ALSO leak the reservation — so Q-RESLEAK must be fixed to cover every cap-raise path, not just the existing hard one. Fix Q-RESLEAK's release to wrap all cap raises.

## Fix order (dependency-aware)
1. **Q-RESLEAK** first (so the reservation is released on every cap-exit, including the new one Q-SMART-PAID adds).
2. **Q-SMART-PAID** (Critical): smart/soft no-free → restrict to Claude/anthropic (genuine "fall through to Claude"); if no Claude in chain → block (never a silent non-Claude paid call). Rewrite the misleading test.
3. **Q-MONTHLY**: add a month-scoped rejected-attempt term to `get_monthly_spend`.
4. **Q-ROUTEID**: make route_id collision-proof (add a per-second nonce / monotonic counter component).
5. **Q-OBSERV2**: render the downgrade in `LLMResponse.summary()`/`.header()`; test the rendered output.
6. **Q-MSG**: correct the cap error message wording to local reset.
7. **Q-DRAFTFN**: accept as mitigated residual; document (no code change — P-DRAFT already removed the turn-replacement risk).

Each: test-first, independent repro, small commit, GATE re-runs.
Clean-audit counter reset to 0 (this round found substantive defects).
