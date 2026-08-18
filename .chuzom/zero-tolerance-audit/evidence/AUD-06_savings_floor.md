# AUD-06 — "TOTAL saved" is a sum of wins, not a net. Losses are silently discarded.

```
ID: AUD-06
Severity: P0
Confidence: PROVEN
Area: Economics — savings aggregation / user-facing dashboard
Title: Per-item savings are clamped at zero before aggregation, so the reported total
       cannot be negative; a session that cost MORE than the counterfactual is displayed
       as a saving.
```

## Claim / invariant violated

- Product contract #15 — dashboard arithmetic must be reconstructable.
- Failure model **FT-4.10 / I-2** — *unknown or adverse outcomes must not silently become favourable ones.*
- NORTH_STAR anti-goal — *"claims a guarantee that isn't measured."*

## Observed behaviour

Three independent clamp sites at `c2c2882`:

| Site | Code |
|---|---|
| `src/chuzom/dashboard_data.py:199` | `saved = max(0.0, opus_baseline - cost)` |
| `src/chuzom/dashboard_data.py:307` | `b["saved"] += max(0.0, opus_baseline - float(cost))` |
| `src/chuzom/summary.py:217` | `data.savings_usd = max(0.0, data.baseline_cost_usd - data.total_cost_usd)` |

`dashboard_data.py:307` is decisive: `+=` accumulates **already-floored per-item values**, so a loss on
one item can never offset a gain on another. The aggregate is a **sum of positive terms**, not a net.

## The product's own README demonstrates the defect

`README.md` publishes this dashboard sample as marketing material:

```
  Tier              | Calls | Tokens |   Actual |  Baseline |    Saved
  Free local        |    16 |    240 | $ 0.0000 | $  0.0013 | $ 0.0013
  Free subscription |     5 |   3516 | $ 0.0000 | $  0.0190 | $ 0.0190
  Paid API          |    27 |  13421 | $ 0.1735 | $  0.0725 | $ 0.0000   <-- true value -0.1010
  TOTAL             |    48 |  17177 | $ 0.1735 | $  0.0928 | $ 0.0203
```

Reconstructed arithmetic:

| Quantity | Value |
|---|---|
| Total actual | `$0.1735` |
| Total baseline | `$0.0928` |
| **True net position** | **`-$0.0807`** (spent MORE than the counterfactual) |
| **Dashboard prints** | **`+$0.0203` saved** |
| Misstatement | **`$0.1010`** |
| `0.0013 + 0.0190` | `= 0.0203` — exactly the sum of the floored positive rows |

The Paid-API row's real result is **−$0.1010**. It is rendered as `$0.0000` and excluded from the total.

**In the published example, the user spent 87% more than the counterfactual and the product told them
they saved money.** This shipped in the README and nobody noticed — which is itself evidence that the
number is not being independently reconstructed by anyone, including its authors.

## Why this matters to a real user

This is the product's central commercial claim. A user checking whether Chuzom is worth running gets a
figure that **cannot** tell them it is not. The one condition a cost-optimizer must be able to report —
*"this cost you more than doing nothing"* — is the exact condition the display is structurally unable to
express. Negative savings are not an edge case: they are guaranteed whenever routing escalates, retries,
or picks a paid tier over a cheaper counterfactual, all of which are normal operation.

## Compounding with RED8-01

`dashboard_data.py` carries **both** defects at once: the stale `$15/$75` Opus baseline (RED8-01, P0) and
this clamp. They multiply — an inflated baseline makes each row's "saving" larger, and the clamp deletes
every row that would have pulled the total back down. Errors that would partially cancel in an honest
net calculation instead reinforce.

## Root cause

`max(0.0, ...)` applied at the **per-item** level, before aggregation. If clamping is desired at all it
belongs (if anywhere) at the **presentation** layer of a single already-netted figure, never inside an
accumulator. There is no code path that records that a clamp occurred — the discarded loss leaves no
trace, no counter, no log.

## Why existing tests and gates missed it

`git log -L 217,217:src/chuzom/summary.py` → introduced `56fe4ae` (2026-06-05), when the project was
still named `tessera` (`src/tessera/summary.py`). Long-standing.

**Decisively:**

```
$ git show 7c6fdaa:src/chuzom/summary.py | grep -n 'max(0.0, .*baseline'
217:    data.savings_usd = max(0.0, data.baseline_cost_usd - data.total_cost_usd)
```

The clamp was **present at `7c6fdaa`** — the commit certified **RELEASE QUALIFIED**. That commit's own
subject is *"feat(summary): baseline counterfactual from recorded tokens, not a latency guess
(#28, **Gate 7**)"*, and **Gate 7** is defined as *"surfaces reconcile (no estimate-as-measured)"*.

**Gate 7 passed on code that is structurally incapable of reporting a loss.** The qualification is
therefore not merely stale (AUD-01) — it was **insufficient at the moment it was granted**. A gate that
certifies "surfaces reconcile" while the surface cannot represent a negative result is not a gate.

Every test asserting `savings >= 0` would pass. Any test asserting the total equals the sum of true
per-row nets would fail — no such test exists.

## Blast radius

Every savings surface fed by `summary.py` / `dashboard_data.py`: session summary, dashboard, statusline,
digest, retrospective, CLI output, and the README's own example. RED8-01 independently traced
`dashboard_data.py` to ~26–28 downstream reporting surfaces.

## Can this defect class exist elsewhere?

Yes — anywhere an adverse value is clamped before aggregation. Audit every `max(0`, `abs(`, and
`if x < 0: x = 0` in cost, quota, token, and latency accounting. The same epistemic error as
"unknown becomes zero" (I-2): **an unfavourable measurement is being converted into a favourable one
with no record that it happened.**

## Recommended systemic fix

1. Remove per-item clamping. Aggregate **signed** values.
2. Allow the reported total to be negative and **render it as such** ("cost you $0.08 more").
3. If a non-negative figure is wanted for a headline, compute it from the signed net and label it
   distinctly — never by discarding terms.
4. Add an invariant: `reported_total == sum(signed_per_item)` — enforced in CI, mirroring the
   `tool_surface.py`/CHZ-SURF-01 playbook the team has already proven works.

## Regression test that would prevent recurrence

Property test: for randomly generated per-item `(actual, baseline)` pairs including cases where
`actual > baseline`, assert the rendered total equals `sum(baseline_i - actual_i)` **including sign**.
Add one fixture reproducing the README's exact sample and assert the displayed total is **−$0.0807**.

**Release blocking? YES.**
