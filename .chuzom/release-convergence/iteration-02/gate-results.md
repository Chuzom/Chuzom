# Iteration 2 — GATE Results

**PASS.** Full suite: 6398 passed, 0 failed, 0 errors (after fixing 1 GATE-caught test regression).

| Finding | Sev | Pre-fix repro | Post-fix |
|---|---|---|---|
| Q-SMART-PAID | Crit | smart+cap → openai billed | → blocks (no Claude) / anthropic (Claude present) |
| Q-RESLEAK | High | pending 0→0.015 over 3 blocks | → 0.0 (released) |
| Q-MONTHLY | High | daily=50 monthly=0 | monthly=50 |
| Q-ROUTEID | Med | same-second ids collide | nonce → distinct |
| Q-OBSERV2 | Med | downgrade not rendered | summary/header show it |
| Q-MSG | Low | 'today UTC' | 'today, local time' |

Clean-audit counter reset to 0 (iteration-2 found substantive defects). Next: fresh iteration-3 RED round.
