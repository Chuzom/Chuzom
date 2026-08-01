# PLAN — Adjudication (Iteration 3)

Fresh RED-1 (3 High + 2 Med) + RED-2 (1 High + 1 Med + 2 Low, + 5 earned-clean) on HEAD 3f5a311. Material findings independently re-reproduced.

| PLAN ID | Merges | Sev | Root cause | Repro |
|---------|--------|-----|-----------|-------|
| **Q3-RESLEAK-CLASS** | RED1-3-01/02/03 | High | `route_and_call` has NO top-level try/finally; `_pending_spend` (and the distributed envelope) leak on every early exit: empty-chain ValueError, semantic-cache-hit `return cached`, `reserve_envelope` failure. My iter-2 Q-RESLEAK only patched the cap raises. ONE root cause, 3 instances. | RED-1 live (after>before on each path). |
| **Q3-RENDER** | RED2-3-01 | High | Q-OBSERV2 render says "free/local model" even when the smart-fallthrough routed to PAID Claude (anthropic, cost>0). One flag, two branches. | Confirmed: provider=anthropic, header says free-local. |
| **Q3-ATTR** | RED1-3-04 (+iter2 Q-ROUTEID residue) | High | Pending-route file keyed by session_id only; a late/out-of-order tool call credits turn N's honor to turn N+1's route_id; turn N's directive vanishes from the ledger. Architectural (hook only knows session_id). | RED-1 e2e: realized_routes mis-attributed. |
| **Q3-CLAIMS2** | RED2-3-02 | Medium | "50–100x" magnitude claim in installed rules/chuzom.md + enforce-route.py; my claims guard only matched "60-90%"/"3×". | Confirmed present. |
| **Q3-LEDGERORDER** | RED1-3-05 | Medium | `execution_ledger._load_rows` has no ORDER BY; `_aggregate`'s last-write-wins realization merge flips `realized_savings_usd` under row reordering. Compounds Q3-ATTR. | RED-1: 0.0 vs 0.038. |
| **Q3-QUOTABUCKET** | RED2-3-03 | Low | gemini_cli is free-local for routing but absent from quota_savings buckets → quota-hint line silently dropped (fails open). | Confirmed. |

## Risk-tiered fix plan
**Tier A — clean, safe, fix now (test-first):**
- Q3-RENDER: distinguish the two downgrade branches in the render (free-local vs Claude).
- Q3-CLAIMS2: reword "50–100x" + extend the guard's MAGNITUDE_FORBIDDEN to `\d+[-–]\d+\s*[x×]`.
- Q3-LEDGERORDER: add `ORDER BY ts` (deterministic) to `_load_rows`.
- Q3-QUOTABUCKET: add gemini_cli to the quota_savings free bucket.

**Tier B — root-cause refactor (higher risk, careful):**
- Q3-RESLEAK-CLASS: single idempotent reservation-release + top-level try/finally, handling the `_env_key`-not-yet-reserved ordering. Subsumes iter-2 Q-RESLEAK. Only attempt if it can be done cleanly with a focused concurrency/leak test; a double-release is worse than the leak.

**Tier C — architectural, scope honestly:**
- Q3-ATTR: the per-session pending-file → out-of-order attribution needs a hook-protocol change (a per-turn directive queue keyed so the right honor maps to the right route). Not safely fixable as a tail-patch. If not fixed this cycle, document as the recurring architectural root cause + blocker-remediation plan (workflow §14).

Clean-audit counter stays 0. Convergence note: iter-1=12, iter-2=6, iter-3≈9 findings — NOT monotonically converging; the reservation-lifecycle and ledger-attribution are recurring root causes that targeted patches keep only partially closing. This is the signal §14 describes.
