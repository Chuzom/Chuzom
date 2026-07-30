# Iteration 2 — Implementation Report (FIX)

Fresh RED-1 (7 areas → 2 High + 1 Med + 1 Low) + RED-2 (1 Crit + 1 Med + 1 Low) audited HEAD 509b03f. **Every finding was in Iteration-1's own fixes** — the fresh adversarial round did exactly its job. PLAN independently re-reproduced the material ones.

## Fixes landed (each test-first, independent repro, small commit)

| PLAN ID | Sev | Commit | Root-cause fix |
|---------|-----|--------|----------------|
| **Q-SMART-PAID** (RED2-2-01) | **Critical** | `80017ed` | smart/soft cap no-free branch restricts to Claude/anthropic (genuine fall-through); no Claude → block. Never a silent non-Claude paid call under a cap. |
| **Q-RESLEAK** (RED1-2-02) | High | `80017ed` | `_release_cap_reservation()` before every cap raise — no more `_pending_spend` leak. |
| **Q-MONTHLY** (RED1-2-01) | High | `3c20fc4` | `get_monthly_spend` adds month-scoped rejected-attempt cost (was daily-only). |
| **Q-ROUTEID** (RED1-2-03) | Medium | `edaf8ae` | route_id gets a `token_hex(4)` nonce — no same-second collisions dropping ledger rows. |
| **Q-OBSERV2** (RED2-2-02) | Medium | `6c82ef4` | `summary()`/`header()` render the cap downgrade (was set but never shown). |
| **Q-MSG** (RED1-2 note) | Low | `6c82ef4` | cap error text "UTC" → "local" (matches the localtime query). |
| **Q-DRAFTFN** (RED2-2-03) | Low | — | Accepted as documented residual: P-DRAFT already removed the turn-replacement risk; response_formatter disclaimer covers the echo path. No code change. |

Plus a GATE-caught test regression (`839b7a7`): `test_enforce_mode_..._soft_warns_and_proceeds` asserted the exact RED2-2-01 buggy behavior (soft → openai); rewritten to the corrected semantics.

## Verification highlights (raw-repro parity)
- Q-SMART-PAID: smart+cap+no-Claude now BLOCKS (was: called openai). ✓
- Q-RESLEAK: `_pending_spend` returns to 0.0 after 3 hard blocks (was: 0.015). ✓
- Q-MONTHLY: monthly=$50 for a rejected $50 attempt (was: $0). ✓
- Q-ROUTEID: same-second same-tool route_ids now differ. ✓

## CI
- G5 gate extended with all 10 iteration-2 regression suites (`987db59`).
- G4 hygiene baseline 33→34 (justified: legit file-read guard, not a can't-fail test).

## Convergence status
Iteration 2 FIX complete: all confirmed findings fixed + validated. Clean-audit counter **0** (this round found substantive defects). Next: fresh Iteration-3 RED round against the new HEAD.
