# 25 · Master plan — everything currently open, sequenced

Date: 2026-08-15. Supersedes doc 22's sequencing (which covered G-F alone) by placing it
inside the wider set of work. Doc 20 remains the pre-registered protocol and outranks
everything here.

Five workstreams are open. They are **not** independent: W2 blocks W3, and W3 blocks W4.
That dependency is the single most important thing in this document.

    W0  Land what is verified                     ~1 hour      NOW
    W1  G-F qualification                         days-weeks   independent
    W2  Data-integrity P0 (#51)                   unknown      BLOCKS W3, W4
    W3  Canonical attribution layer               ~1 day       blocked by W2
    W4  Runtime summary redesign                  ~2-3 days    blocked by W3
    W5  Owner decisions                           —            some block work

---

## W0 · Land what is verified — do this first

**Why first:** work sits staged and unverified while a mutation run holds `setup.cfg`.
Nothing else should start on top of an unlanded tree.

1. Wait for Step 0 (launched 13:52, ~39 min). Verify **all three**: `returncode == 0`,
   `mutant_names_count == 1986`, and **1986 outcome lines** in `mutmut_stdout.txt`. The
   previous attempt returned `-15` with **zero** outcomes captured — a metadata file
   exists either way, so the outcome count is the real check.
2. `git diff --quiet setup.cfg || git checkout setup.cfg`. The harness restores it in a
   `finally`, which a killed run skips.
3. Full suite, then all eight gates, then commit:
   * `src/chuzom/hooks/session-end.py` — MODELS panel fix
   * `src/chuzom/attribution.py` — canonical module
   * doc 23 §I/§J, doc 24, this doc
4. Record the Step 0 score against the 0.5866 baseline. **74 TRAIN mutants were killed
   since; the VALIDATION effect is unmeasured, so the combined figure is not predictable
   from that number.**

**Done when:** tree clean, suite green, score recorded or the run's failure recorded.

---

## W1 · G-F qualification — independent, resumable

Detail in `22_REMAINING_WORK_PLAN.md`. State: **0.5866** measured, floor **0.80**, TRAIN
survivors 614 → **540**.

| step | work | mutants |
|---|---|---|
| ✅ | uncovered functions ×2, C1 ×3 sites, C6 accumulators | 74 killed |
| next | Group A — C7 boundaries (33), C4 (13), C3 (12), C2 (10) | ~68 |
| then | Group C — 8 remaining C1 codes, 5 small uncovered fns | ~50 |
| then | **checkpoint re-measure** | — |
| then | Group B — 6 large functions | ~164 |
| then | **checkpoint + stopping rule** (doc 20 §5) | — |
| then | Group D long tail, only as far as the floor needs | ~199 |
| last | **holdout, scored EXACTLY ONCE** (doc 20 §7) | 450 |

Drafts already in scratchpad, unvalidated: `test_gf_c7_boundaries.py`,
`test_gf_c2c3_defaults_and_env.py`.

**Do not write tests for the 5 proven equivalent mutants** in `tool_surface.localize`
(`gf_equivalent_mutants_proven.md`).

**Verification discipline, non-negotiable:** every claimed kill verified **per mutant by
name** with a no-mutant control passing first. A total is not evidence — "11 of 41"
concealed that a third of the target survived.

---

## W2 · Data-integrity P0 (#51) — BLOCKS W3 and W4

**The finding:** 2,373 rows counted as *attributed* routing carry 0 distinct
`session_id`, 1 `prompt_hash`, 1 `task_type`, and hold an exactly **3.200:1** ratio with
claude-opus on 8 of 9 days. Separately, `classifier_type='gateway'` (6,310 decisions, the
largest population) disappears entirely after Aug 1.

**So `provenance IS NULL` does not mean real traffic.** Finding #30 caught one synthetic
population; this is a second, unmarked one *inside* the attributed set.

### W2.1 Identify the writer
Search for anything emitting routing_decisions in fixed ratios — benchmark harness, soak
replay, load test, a seeding/demo script. The 3.2:1 constancy and single `prompt_hash`
are the fingerprints: find the code that produces one prompt repeatedly at a fixed model
split.

### W2.2 Establish why provenance did not mark it
`0aab32f` added the marking. Determine whether this writer predates it, bypasses it, or
writes through a path the guard does not cover.

### W2.3 Decide the marking — OWNER DECISION
Mark retroactively / mark going forward only / leave and exclude by another key. Each
changes historical dashboard numbers; that consequence must be stated before choosing.

### W2.4 Re-derive the real numbers
Once marked, recompute attributed shares. **Only then is it knowable whether the local-
routing collapse (38.6% → 0.1%) is a real routing regression, synthetic volume swamping
real traffic, or both.** Do not assert a cause before this.

**Done when:** every synthetic population in `routing_decisions` is identified and
marked, and the attributed set contains only real traffic.

---

## W3 · Canonical attribution layer — blocked by W2

`src/chuzom/attribution.py` exists and is correct in rule. It computes over contaminated
data, so it is not yet trustworthy in output.

1. **Re-verify against clean data** after W2. The rule keys on `provenance`, not
   `classifier_type` — deliberately: the two are 100% correlated today only because the
   synthetic rows happen to carry no classifier, and filtering on `classifier_type` would
   misclassify the first *real* decision with an unrecorded classifier.
2. **Name the four quantities** and give each its canonical filter:
   attributed routing decisions · all routing decisions · paid invocations · all
   invocations. The MODELS panel measures the fourth; the dashboard measures the first.
3. **Migrate consumers.** `cost.get_quality_report()` first, then any CLI/API surface
   found by the §5 repo-wide sweep (**not yet done** — see W5).
4. **Consistency tests** (directive §13): one controlled fixture, every surface claiming
   the same quantity must return the same answer. Plus the invariants
   `attributed + unattributed == eligible` and `sum(shares) == 1.0` — already enforced by
   `check_invariants()`.
5. **`usage` has no `provenance` column.** Owner decision taken: do **not** add one. The
   MODELS panel reports *invocations*, a different named metric; no attribution needed.

---

## W4 · Runtime summary redesign — blocked by W3

Full spec in the user's directive. **Premise: "you saved $X, spent $Y today."** Those
numbers derive from the set W2 is cleaning, which is why this is last.

1. **`/council` on the UX hierarchy** — owner decision taken. The layout is well
   specified; the genuinely open design question is the §7 throttle/trigger thresholds.
2. **Audit the financial semantics before any UI work** (§3): *spent* = actually billed,
   *saved* = estimated avoided cost, *net* = saved − spent. Expose net **only if** both
   inputs are reliable after W2. §14: never render an estimate with the same visual
   certainty as billed spend.
3. **Three render modes** — compact (36–45 cols: saved/spent/top models/routing %),
   standard (adds cost, net, delta, quota warning), detailed (today's full dashboard,
   preserved intact per §11).
4. **Meaningful-update trigger** replacing print-everything-every-time. Thresholds
   configurable: `summary_interval`, `summary_call_threshold`, `summary_savings_delta`,
   `quota_warning_threshold`.
5. **Delta updates** — persist last-summary state in the existing store (§15, no second
   database).
6. **Tests** at 36 / 60 / 120 columns, first-vs-repeat summary, large values
   (`$1,483.40`, `126.2M`, `235,754`), empty state, and **compact metrics == detailed
   metrics**.

**Do not start before W3 §1 is green.** A glance view is only worth building on numbers
that mean something.

---

## W5 · Open owner decisions

| # | decision | blocks |
|---|---|---|
| **#51** | how to mark the second synthetic population | W3, W4 |
| **#38** | exclusion rule matches gate-script names in prose — 8 tests excluded textually. Fixing needs a doc 20 amendment; doc 21 flags a third amendment as a signal to reassess | affects the G-F score itself |
| **#37** | 153 sites ignore `CHUZOM_HOME` while `is_isolated()` certifies a sandbox. Recommendation: (d) central accessor for `usage.db`/`usage.json` (~38 sites, ~80% of risk), then (c) narrow what `is_isolated()` claims | — |
| **#32** | the fail-open linter cannot see a fail-open that logs; WP-13 used it as its instrument | — |
| **shims** | 66 mutants in the two notification functions — argv assertions vs narrower platform-dispatch tests vs scope exclusion | W1 ceiling |
| **agno** | budget pressure reads `total_cost_usd` including $3.62/$39.79 unattributed | — |
| **§5 sweep** | repo-wide inventory of independent attribution implementations — **not yet done** | W3 §3 |

---

## Sequencing at a glance

    W0 ─────────────────────────► (unblocks everything)
         │
         ├── W1 G-F ──────────────────────────────► independent, resumable
         │
         └── W2 #51 ──► W3 canonical ──► W4 redesign
                 ▲
                 └── owner decision required mid-stream

W1 can proceed in parallel with W2–W4 **only if** they do not run concurrently on this
machine. Two mutation runs or a mutation run plus a test suite is how the first Step 0
died; the suite is load-sensitive (finding #19), and even read-only subagents are CPU
load — "parallel-safe" was too strong a word for them.

## Standing rules

* Verify kills **per mutant by name**, never from a total.
* Read the **exit code**, not parsed text. `addopts` already carries `-q`; a second `-q`
  suppresses the summary line entirely.
* Full suite + eight gates before every commit. A file passing alone proves nothing about
  order-independence.
* Never change the tree, run pytest, or commit while a mutation harness is live.
* Leave an unexplained cause **open** rather than closing it with the best-sounding
  story. The first Step 0 SIGTERM is still unexplained and stays that way.

---

## Owner decisions taken 2026-08-15

| question | decision |
|---|---|
| W0 on Step 0 landing | **Full W0** — verify 1986 outcome lines, restore `setup.cfg`, full suite, 8 gates, commit |
| first workstream after W0 | **W2** — trace the synthetic rows. Unblocks W3/W4 and is highest-stakes: the dashboard currently reports synthetic data as real routing |
| mutation-run cadence | **Batch** — write several test classes, measure once per work session. Fewer 39-min runs, less machine contention |
| `/council` on redesign UX | **At W4 start**, after the data is clean — so the hierarchy is reviewed against metrics we trust |

**Consequence of the batching decision, recorded rather than silently applied:** doc 21
Step 3 says "score TRAIN after each class". That cadence is now relaxed to once per work
session. The formal CHECKPOINTS (doc 22 steps 3 and 5) are **unchanged** — they remain
mandatory, and they are where VALIDATION is scored under doc 20 §5. Relaxing a
measurement cadence quietly is how a plan drifts from what is actually being done.
