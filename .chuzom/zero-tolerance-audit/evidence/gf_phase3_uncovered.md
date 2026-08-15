# G-F Step 3.4 — the two largest 100%-uncovered functions

Date: 2026-08-15. Class defined in `gf_phase2_classes.md` §2 (107 no-coverage mutants
across nine functions). This closes the two largest.

## Result

| function | mutants | killed |
|---|---|---|
| `budget.format_budget_summary` | 18 | **18 (100%)** |
| `cost.refresh_baseline_pricing_from_api` | 20 | **20 (100%)** |

27 tests across two new files. Verified per-mutant by name, each with a no-mutant control
passing first.

**100% deserves suspicion and gets it.** Doc 21 §"What would make this fail honestly" (3)
says a jump not attributable to specific tests should be treated as suspect. This one is
attributable: both functions had *no test executing them at all*, so every mutant was
reachable by any coverage, and each kill was confirmed individually rather than inferred
from a total. The claim is narrow — 38 TRAIN mutants in two small functions — and says
nothing about the same functions' VALIDATION mutants, which are different mutants and are
not inspected here by protocol.

## Why these two were worth doing first

Neither is cosmetic, though both look it.

`format_budget_summary` renders the Budget Oracle block an operator reads to decide
whether spend is under control. A wrong bar or percentage is a confident wrong answer to
that question.

`refresh_baseline_pricing_from_api` overwrites `_HOST_INPUT_PER_M` /
`_HOST_OUTPUT_PER_M` — the baseline every savings figure is computed against. A mutant
here crashes nothing; it makes reported savings wrong by a multiple and entirely
plausible. The function's own comment names the precedent: RED2-01, a shipped 3x
overstatement.

## Three defects in the tests, all found by mutation rather than by review

### 1. A substring assertion satisfied by a superstring

    assert "free (local)" in out          # passed against "XXfree (local)XX"

mutmut's string mutation wraps a literal as `XX…XX`. The original is a *substring* of the
mutation, so the assertion held while the rendered output was wrong. Now compares the
field exactly, via the tail of the provider's line.

This is the third variant of one mistake in this audit: a guard satisfied by its own
comment (Phase 1), an exclusion rule triggered by a docstring (C1), and now an assertion
satisfied by a superstring. **Matching text where you mean to match a value.**

### 2. A lesson from one file not carried to the next

Two survivors were `failopen.record(code, None)` and `failopen.record(code, )` — dropping
the exception. That is *exactly* the class diagnosed and fixed for the three router sites
in `gf_phase3_c1_failopen.md`, roughly an hour earlier. A new fail-open assertion was
written, and it asserted only the code again.

Recorded because the fix is not the point: **asserting the recorded exception type has to
be part of how any fail-open site is tested**, not a patch applied once to the file where
the gap was first noticed.

### 3. A genuinely untested path — and the absence of a record is the discriminator

`getattr(model, "pricing", None)` versus the two-argument `getattr(model, "pricing")`:
the second raises `AttributeError` when the attribute is missing. Both spellings make the
function return `False`, so **the return value cannot tell them apart**. The mutant
reaches the `except` branch and records a fail-open; the original never does. The test
therefore asserts that *nothing* was recorded.

Every fixture in the file set `.pricing` — sometimes to `None` — so the attribute was
never actually absent and this path had no test. Beyond the mutant, it means a missing
`pricing` attribute would have been reported to operators as a degradation that did not
occur, inflating the fail-open store with a non-event.

## Test-design choices worth stating

* **Expected strings are written literally**, not rebuilt with the implementation's own
  expression. Recomputing `"█" * round(p * 10)` in the test would assert the code equals
  itself and survive a mutant that changed both.
* **The bar is pinned at 10 cells across five pressures.** The width appears twice in
  `"█" * filled + "░" * (bar_len - filled)`; a single fill-level assertion need not catch
  a change to one side.
* **Input and output rates use different fixture values** (15 vs 75). B1 in this audit
  was Opus input/output rates inverted; with equal values a swap is invisible.
* **The globals get real restoration discipline.** The function assigns two module
  scalars *and* mutates `_OPUS_PRICING` in place, so the dict needs `monkeypatch.setitem`
  — `setattr` would rebind the name while the in-place write still corrupted the original
  object. Rather than trust that, one test asserts the restoration and fails if this file
  leaks. That is the pollution class behind `63cbc8c`, which C6's own fixture already
  reintroduced once this session.
* **`import anthropic` is a plain import**, so patching `sys.modules` alone is sufficient
  — unlike the `from chuzom import calibration` case in C1, where the package attribute
  had to be deleted as well. Same-looking problem, different fix; checked rather than
  assumed.

## Still open in this class

| n | function | note |
|---|---|---|
| 38 | `cost.fire_budget_alert` | notification shim — OWNER DECISION, `gf_phase2_classes.md` §5 |
| 6 | `cost._restore_claim` | |
| 6 | `tool_surface.door_name` | |
| 3 | `budget.invalidate_cache` | |
| 3 | `router._auth_error_hint` | |
| 3 | `tool_surface.resolve_name` | |

`execution_ledger.get_turn_accounting` (10) left this class earlier: C6 covers it.

## What this does not claim

38 TRAIN mutants killed is not a score. The combined figure moves only when a full
mutation run measures it, and an estimate is not a measurement. **G-F remains NOT
QUALIFIED at 0.5866.**
