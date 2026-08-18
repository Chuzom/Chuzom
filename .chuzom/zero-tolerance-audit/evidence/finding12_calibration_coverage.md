# Finding #12 — the calibration corpus covers exactly one pair

Date: 2026-08-12. Raised while landing WP-05; part (a) fixed then, part (b) here.

---

## The measurement

`INITIAL_CALIBRATION` holds **one** empirical profile:

| pair | n_samples |
|---|---|
| `(claude-sonnet-4-6, QUERY)` | 1114 |

Every other `(model, task)` pair falls through to `_LEGACY_FALLBACK_OUTPUT = 80`,
a static assumption carried over from pre-calibration code.

Measured after the fix:

```
profiled 1/230 pairs = 0.4%
unprofiled models: 22 of 23
```

## What was actually wrong

Not the sparse corpus. Sparse data is a normal state for a young calibration
surface, and **inventing profiles to fill it would be fabricating measurements**,
which is worse than an honest gap.

The defect was that `predict_cost` returned a **bare float for both cases**. A
projection resting on a hardcoded 80 was indistinguishable from one resting on
1114 observations, and `auto-route` rendered either as a plain `$0.0012`.

This is the quiet form of the pattern this audit keeps hitting. RED2-02 was the
loud version — an unreadable ledger rendering `$0.00 saved`, a zero that reads as
data. Here the number is not even wrong. It is **unmarked**: its confidence was
dropped on the floor between computation and display.

`chuzom.provenance` already implemented WP-05's rule (`~$X (estimated)`).
Calibration simply never used it.

## What landed

- `predict_cost_measured()` returns a `Measured` — same value, plus how it was
  arrived at. A test pins that the value is **identical** to `predict_cost`'s, so
  this is a labelling change and cannot smuggle in a pricing change.
- `calibration_coverage()` makes the blind spot countable and **names the
  unprofiled models**, because a bare percentage does not get a corpus extended.
- `auto-route` propagates `provenance` as an **additional** dict key. `savings`
  stays a bare parseable `"$X"` string — callers `lstrip('$')` it, and
  reformatting to embed a label would trade one defect for another.
- The legacy static map is tagged too. It is the least-measured path in the
  system, used when calibration will not even import; if the calibrated path has
  to admit it is estimating, that one certainly does.

## The denominator, and the trap it avoids

Coverage is **not** measured against `INITIAL_CALIBRATION`'s own keys. That would
report 100% forever — the identical self-resolving trap found twice already:
`tool_surface.unregistered()` checking tier constants against `_TIERS`, and
`lint_tool_surface.py` checking emitters against emitters. Both reported clean
while blind. The denominator is the priced-model list crossed with the routable
task types.

`test_calibration_coverage_is_reportable` asserts `total > profiled` **with that
failure named in its message**, so if someone later repoints the denominator at
the corpus, the test says why it broke rather than just that it did.

## A second defect found while building the denominator

**The savings baseline is not in `_CALIBRATED_MODELS`.** Measured: `claude-opus-5`
is absent from that tuple and from `_PRICING_PER_M`. It resolves a price *only*
through the `chuzom.pricing` fallback added in #12(a).

So the module's own model list is stale with respect to the one model every
savings figure is computed against, and the system works only because a fallback
added days ago catches it. Remove that fallback and `predict_cost` returns `0.0`
for the baseline again — which is exactly how #12(a) manifested: auto-route
silently dropped to `_legacy_static_savings` and rendered the static `$0.0005`
the Cat-F work had removed. No error, plausible number.

`calibration_coverage()` therefore unions the baseline into its model set
explicitly, and a test asserts it appears in `unprofiled_models`. Leaving it out
would have hidden the single most consequential gap.

## Correcting my own process, not the code

`uvx ruff@0.16.0 check src/ tests/` is a CI lint step, and **HEAD was failing
it** — three dead imports across three of this session's commits:

| file | orphaned by |
|---|---|
| `src/chuzom/secret_scrubber.py` (`os`) | WP-15's deletion of `scrub_environment()` |
| `tests/agentic/test_escalation_bounds.py` (`MilestoneStatus`) | WP-10 |
| `tests/test_doctor_truth.py` (`pytest`) | WP-11 |

I ran the test suite after each change and never ran the linter, so three commits
accumulated a CI failure that no test could see. Fixed here. Worth recording
because it is the same shape as the findings themselves: a check that exists,
that nobody invoked, reporting nothing.

## A test narrowed, not broken

`test_cat_f_deferred_sites.py::test_legacy_fallback_renders_when_calibration_unavailable`
asserted `out == {"savings": "$0.010"}` — exact dict equality — while its own
docstring states the purpose as *"the static map still ships a string"*.

The equality was stricter than the stated purpose and rejected any
strictly-more-informative return. Narrowed to `out["savings"] == "$0.010"`, which
still pins the value.

Checked first that it is **not** an immutable audit asset (it is not listed in
the plan's `Immutable test assets` lines). The three tests found earlier this
session that genuinely asserted a defect as the contract are a different
category; this one asserted slightly more than it meant to.

## Still open

The corpus still covers one pair. Extending it needs real benchmark runs, not
code. What changed is that the gap is now **countable, named, and admitted at the
point of display** rather than silent.
