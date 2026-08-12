# WP-14 / G-F — mutation baseline, and why the gate as written cannot be met

Date: 2026-08-12. Harness: `scripts/mutation_sample.py` (commit `f82f38d`).
Baseline SHA: `c2c28821f690f7cbda42b46da06fc36ef77d816e` (from `00_AUDIT_BASELINE.md`).
HEAD at measurement: `f82f38d`.

---

## Result

| | HEAD | Baseline `c2c2882` |
|---|---|---|
| Mutations applied | 10 / 10 | **3 / 10** |
| Killed | 10 | 2 |
| Score over own denominator | 1.00 | 0.67 |

**The two scores are not comparable.** Seven of the ten mutations target code that
did not exist before the remediation — `chuzom/coverage.py`, the single savings
baseline in `pricing.py`, the unclamped display path, the dynamic-pin narrowing.
Comparing 1.00-over-10 against 0.67-over-3 is arithmetic, not measurement.

## G-F as specified cannot be satisfied

> **G-F** — Mutation score on money/routing/verification modules ≥
> `mutation_baseline + 0.15`, floor 0.80

Two independent problems:

1. **No baseline existed.** `mutmut>=3.0` is a declared dev dependency that was
   never wired to anything, and no baseline value appears anywhere in the repo.
   "baseline + 0.15" had no left-hand side, so the gate could not be evaluated in
   either direction. It was not a gate.

2. **A targeted sample is structurally incomparable across a remediation.** Any
   remediation that adds modules makes mutations against those modules
   inapplicable at the baseline. The more thorough the remediation, the fewer
   mutations apply, and the less meaningful the comparison. This is not fixable
   by choosing better mutations — it is inherent to comparing a targeted sample
   across two SHAs with different code.

Reporting a single number for G-F would therefore require either crediting
inapplicable mutations as killed (manufacturing the improvement the gate exists
to measure) or scoring over a shrunken denominator (a rate that quietly
redefines itself — the exact defect WP-07 fixed in the product).

## What can honestly be claimed: the intersection

Restricted to the three mutations that apply at BOTH SHAs:

| Mutation | Baseline | HEAD |
|---|---|---|
| M5 — bogus tool name in the CORE tier | **SURVIVED** | killed |
| M7 — per-task rotation disabled | killed | killed |
| M10 — ledger drops every event *(positive control)* | killed | killed |
| | **0.67** | **1.00** |

**Δ = +0.33**, which exceeds G-F's required +0.15, and HEAD clears the 0.80 floor.

Recommended disposition: **G-F satisfied on the comparable subset, with this
limitation recorded.** A re-auditor who requires a single whole-sample number
across both SHAs should mark it NOT MET — that is a legitimate reading, and the
gate's wording invites it. What must not happen is a number being reported
without this note.

The M5 row is better evidence than the aggregate. It survived at the baseline,
confirming the audit's Q3(c) finding was real, and is killed at HEAD by
`tests/routing/test_tool_surface_ground_truth.py`. One mutation with a clean
before/after says more about the remediation than any score.

## Q3(c) was recorded closed and was not

Blind spot (c) was marked closed earlier the same day on the strength of an
injection that replaced the bare string `"llm_query"` — **twenty sites** in
`tool_surface.py`. That rewrote the entire tool surface, failed five tests, and
the collateral damage was mistaken for a gate working. The precise single-site
mutation on the `CORE_TOOLS` binding survives the FULL suite (pytest exit 0,
zero failures), which the baseline run independently confirms.

Root cause, unchanged from the audit's own diagnosis and now fixed:

```
registered_tools(slim) -> _TIERS[slim] -> CORE_TOOLS / ROUTING_TOOLS / ...
unregistered(names)    -> [n for n in names if resolve(n).name not in reg]
```

`unregistered()` validates the tier constants against `_TIERS`, which **is** the
tier constants. Rename a tool inside `CORE_TOOLS` and the "registered" set
contains the new name, so the check reports clean. Self-consistency wearing a
validation check's clothes.

## Harness defects found by using it

Every one produced a falsely reassuring number, and all four ran toward "fine":

1. **M2 was an equivalent mutant** — nulled the first of two lookups in
   `_claude_cost`; the `chuzom.pricing` fallback absorbed it. Reported as a
   coverage hole before anyone measured the mutated function's output.
2. **M2's anchor matched three sites** — `_apply` used `replace()` with no count,
   mutating three unrelated functions at once and reporting "killed".
3. **M5's anchor matched twenty sites** — masked the real survivor above.
4. **`score = killed / scored`** excluded n/a and invalid, so nine silent
   failures would report **1.00 off a single probe**.

Now: unique anchors enforced (`INVALID` otherwise, all ten verified), the
denominator printed beside the score, a refusal to issue a verdict below 8
scored, and the cleanliness check scoped to the files the run actually mutated.

**The methodological point for WP-16.** Three times in one session a verdict was
reported from a probe that had not been validated. A green result from an
unvalidated instrument is not weak evidence; it is not evidence. The original
audit's Q3 conclusions were produced the same way — by injection and observation
— and at least one of them was wrong in the direction of "closed". Q3(a), (b) and
(d) deserve re-checking against precise, uniqueness-verified mutations before the
re-audit credits them.
