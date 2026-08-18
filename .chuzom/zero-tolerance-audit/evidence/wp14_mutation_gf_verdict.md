# G-F — the mutation gate, measured at both SHAs

Date: 2026-08-12. Covers #16 action 2 and the G-F verdict.

G-F: *"Mutation score on money/routing/verification modules ≥ `mutation_baseline
+ 0.15`, floor 0.80."*

---

## The two measurements

| | scored | killed | score |
|---|---|---|---|
| **HEAD** (`0c6dac1`) | 10/10 | 10 | **1.00** |
| **BASELINE** (`c2c2882`) | 3/10 | 2 | **0.67** |

Both runs ended `worktree clean after run ✓`.

At the baseline, **7 of 10 mutations did not apply** — their anchors did not
exist yet, because the code they target is code the remediation *created*.

## G-F cannot be honestly evaluated as written

Arithmetically it passes: `1.00 ≥ 0.67 + 0.15 = 0.82` and `1.00 ≥ 0.80`.

**That comparison is not valid.** The two scores have different denominators (10
vs 3) and are therefore not the same measurement. The harness says so itself:

> WARNING: only 3/10 mutations were scored. A score over a reduced denominator is
> not comparable across SHAs.

And by the harness's own floor — *"refuses a verdict below 8 scored"* — the
baseline run does not qualify as a verdict at all. **A gate whose baseline term
cannot be computed is not a gate that passes; it is a gate that cannot be
evaluated.** Recording it as PASS on the arithmetic would repeat exactly the
error G-C embodied: a check that returns a number without being able to fail.

## What CAN be compared: the like-for-like subset

Three mutations applied at **both** SHAs — M5 (routing), M7 (routing), M10
(verification):

| | M5 | M7 | M10 | score |
|---|---|---|---|---|
| BASELINE | **SURVIVED** | killed | killed | 0.67 |
| HEAD | killed | killed | killed | **1.00** |

Same mutations, same tests, both SHAs: **0.67 → 1.00, Δ +0.33**, clearing both
`+0.15` and the `0.80` floor.

This subset is a genuine result, and M5 is the most meaningful single data point
in the whole sample: it is the **bogus CORE tool name** of blind spot Q3(c). At
the baseline it survived with *behaviour confirmed changed*
(`['llm_code','llm_query',...]` → `['llm_bogus_xyz','llm_code',...]`) and no
named test caught it — a real coverage hole, exactly as the audit claimed. At
HEAD it is killed. That is the blind spot closing, measured rather than asserted.

But three mutations is far below the ten the plan intends, so the subset supports
a **statement about those three behaviours**, not a module-level score.

**G-F should be recorded UNEVALUABLE, with the subset result stated.** This needs
an owner decision; the criterion is immutable and I will not reinterpret it.

## Read the 1.00 sceptically

The ten mutations were chosen to target the audit's *known* blind spots, and the
remediation then fixed those blind spots. A perfect score from a sample designed
around what you just fixed is partly self-fulfilling.

It is evidence that **the specific identified blind spots are closed**. It is
*not* evidence that the money/routing/verification modules are well-tested in
general. The re-audit must not read it as the latter.

## #16 action 2 — survivors now have to prove they changed something

The harness classified every non-killed mutant as `SURVIVED`, which asserts
"a test is missing". That inference is what produced the wrong M2 claim: the
original M2 nulled only the *first* lookup in `_claude_cost`, the
`chuzom.pricing` fallback absorbed it, and I reported a coverage hole after
inferring the consequence from the mutation's stated **intent** rather than
measuring its output.

Equivalence is undecidable in general, so the harness cannot detect it
automatically. What it can do is demand evidence:

- Each `Mutation` may carry a **`probe`** — an expression whose printed value must
  DIFFER between clean and mutated source. The clean value is taken **before**
  the mutation is applied, so the reference point is not derived from the mutated
  tree.
- **Only survivors need one.** A killed mutant is self-evidently non-equivalent:
  a failing test *is* the proof that behaviour changed. This is what keeps the
  requirement cheap.
- New statuses, both excluded from the denominator **and printed**:
  - `EQUIVALENT` — probe identical before and after. Not a coverage hole.
  - `UNVERIFIED` — no probe, or the probe failed to evaluate. Cannot distinguish
    a missing test from an equivalent mutant, so it is not counted either way.
- An errored probe is **not** treated as a difference. "It used to return 0.03 and
  now it raises" is a real change, but "the probe was written wrong" looks
  identical from there — and this audit has already been misled once by a probe
  that emitted nothing and was read as a result.

Silent exclusion would have been its own defect: dropping mutations from the
denominator without saying so lets the score be improved by writing mutations
that *cannot* change behaviour. Hence both lists are printed.

### The new branches were verified to fire

The real run scored 10/10 killed, so **neither new branch executed**. An untested
branch inside a guard is this audit's entire subject, and "it would have caught
it" is not a measurement. Replayed deliberately
(`scratchpad/verify_equivalent_path.py`):

| replay | result |
|---|---|
| original M2 (nulls only the first lookup) | `EQUIVALENT`, probe `'0.03'` identical before and after |
| same mutation, no probe | `UNVERIFIED` |
| both | `scored=0` — correctly outside the denominator |

The probe that catches it returns **0.03** — the value that was identical before
and after the original M2. It would have caught that equivalent mutant instantly.

The corrected M2, which bypasses *both* lookups, is **killed**.
