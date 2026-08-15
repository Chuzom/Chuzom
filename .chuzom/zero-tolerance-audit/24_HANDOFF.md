# 24 · Handoff — state at 2026-08-15 14:14

Written because the session ran out of context mid-flight. Read this first.

## 1. IN FLIGHT RIGHT NOW — do not skip

**Step 0 mutation run is still executing** (launched 13:52, ~39 min, expect completion
~14:31). While it runs:

* `setup.cfg` is **DIRTY** — the harness swapped the G-F scope in. It restores this in its
  `finally`, but a killed run skips that. **Check `git diff --quiet setup.cfg` before
  committing anything; `git checkout setup.cfg` if dirty.**
* Do **not** run pytest, and do **not** commit.

When it finishes, verify all three before believing any number:

    mutant_names_count == 1986
    returncode == 0                     (the previous attempt returned -15, SIGTERM)
    outcome lines == 1986               (grep -cE '^(🎉|🙁|🫥|⏰|🤔)' mutmut_stdout.txt)

The first attempt scored nothing: SIGTERM at 2307s with **0 of 1986** outcomes captured.
Cause never established. A second mutmut run (the user's `~/family-office` project) was
active during the relaunch, at the user's explicit instruction.

## 2. STAGED, UNCOMMITTED

| file | what |
|---|---|
| `src/chuzom/hooks/session-end.py` | MODELS panel fix — inflation + free providers |
| `src/chuzom/attribution.py` | new canonical attribution module |
| `.chuzom/.../23_ATTRIBUTION_INVESTIGATION.md` | §I resolution, §J new P0 |
| `.chuzom/.../CRITERIA_MANIFEST.sha256` | rehashed |

**Verified arithmetically, NOT yet through pytest or the 8 gates.**

MODELS fix proof: model A reported 1,440 tokens, truth 450 (3.2× inflation, factor = the
tool's row count). After: per-model sums reconcile exactly to tool totals (480 == 480).

To land it: wait for Step 0 → `git checkout setup.cfg` → full suite → 8 gates → commit.

## 3. THE BLOCKER — task #51, P0

**2,373 rows counted as ATTRIBUTED routing are almost certainly synthetic.**

    0 distinct session_id · 1 prompt_hash · 1 task_type
    gpt-4o : opus = exactly 3.200 on 8 of 9 days

Also: `classifier_type='gateway'` (6,310 decisions, the largest population) vanishes
entirely after Aug 1.

**Therefore `provenance IS NULL` does NOT mean real traffic.** Finding #30 caught one
synthetic population (`gpt-4o-mini`, marked unattributed); this is a second, unmarked one
*inside* the attributed set. The dashboard's 75.1% gpt-4o figure and the new canonical
layer both compute correctly over contaminated data — the rule is right, the data is not.

Next action: trace the writer (benchmark? soak? replay? load test?), determine why
provenance did not mark it, then decide the marking.

## 4. THE NEW TASK — runtime summary redesign

The user has requested a full redesign of the session/runtime summary (glance view,
compact/standard/detailed rendering, throttled "meaningful update" triggers, delta
updates, 36-column mobile readability).

**Sequencing decided by the owner: fix #51 FIRST.** The redesign's premise is "tell me
what I saved and spent today"; those numbers currently derive from the contaminated set.
The user's own spec requires this — §3 ("fix the underlying data path rather than
displaying a misleading value") and §13 ("do not use the current MODELS panel as the
source of truth until its lineage is verified").

Also decided: **run `/council` on the UX hierarchy** before implementing the redesign.

## 5. RESOLVED THIS SESSION — do not re-investigate

* **38.6% hermes3:8b** was a **90-day** window, mislabelled as 30-day in the old notes.
  `chuzom.attribution.routing_attribution(..., "-90 days")` reproduces 38.6/35.6/13.9
  exactly. No contradiction.
* **The ⏰ mutant class does not exist** — 38/38 re-run individually, none hang, none are
  killed. Ordinary survivors.
* **5 proven equivalent mutants** in `tool_surface.localize` (0 prefix/substring/display
  collisions among 25 deprecated names). Unkillable; do not write tests for them.
* **8 tests excluded from G-F for a purely textual reason** (audit #38) — a docstring
  naming a linter excludes a whole file. Direction is conservative: 0.5866 is a floor.
* **usage.db is resolved ~24 ways** (audit #37); `is_isolated()` certifies a sandbox it
  does not govern.

## 6. G-F STATE

Last measured: **0.5866** (1165/1986), floor 0.80. TRAIN survivors 614 → **540**;
74 killed and individually verified (38/38 uncovered functions, 18/41 C1 with 11/11 aimed,
11/51 C6 with 9/9 aimed, 7/10 collateral in `get_turn_accounting`).

Group A drafts sit in the scratchpad, unvalidated:
`test_gf_c7_boundaries.py`, `test_gf_c2c3_defaults_and_env.py`.

Plan and sequencing: `22_REMAINING_WORK_PLAN.md`.

## 7. METHOD NOTES THAT COST REAL TIME

* Every substantive error this session was found by measurement, none by reading.
* A probe reported `pass=0` for 38 runs because `pyproject`'s addopts already carries
  `-q`; a second `-q` suppresses the summary line. **Read the exit code, not the text.**
* "11 of 41 killed" hid the fact that a third of the target survived — verify kills **by
  name**, never from a total.
* An assertion satisfied by a superstring (`"free (local)"` in `"XXfree (local)XX"`) is
  the same defect class as a guard satisfied by its own comment.
* A lesson fixed in one file did not carry to the next file written **in the same
  session**. Encode the check into how a class of site is tested, not as a one-off patch.
* Subagents doing read-only work are still CPU load; "parallel-safe" was too strong.
