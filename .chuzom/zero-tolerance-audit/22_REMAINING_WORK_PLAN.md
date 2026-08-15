# 22 · Remaining work to a qualified G-F — sequenced, with a parallelism assessment

Written 2026-08-15, after six commits took TRAIN survivors from 614 to 547. Doc 20 is the
pre-registered protocol and outranks this file; doc 21 is the campaign plan and this is
its execution schedule. Where any two disagree, doc 20 wins.

---

## Where we actually are

| | |
|---|---|
| last measured combined score | **0.5866** (1165/1986), 95% LB 0.5649 |
| floor | 0.80 |
| TRAIN survivors at baseline | 614 |
| TRAIN survivors now | **540** — 74 killed and individually verified |
| VALIDATION effect of those 74 | **unmeasured** |

Per-mutant verified kills, by class:

| class | killed |
|---|---|
| uncovered functions (2 of 6) | 38/38 |
| C1 fail-open (3 of 11 sites) | 18/41 — 11/11 aimed |
| C6 accumulators in `_aggregate` | 11/51 — 9/9 aimed |
| C6 collateral in `get_turn_accounting` | 7/10 |
| **total** | **74** |

That last row of the first table is the reason Step 0 exists. These are TRAIN mutants. The
same tests almost certainly kill VALIDATION mutants in the same functions, so the combined
score has moved by more than 74/1986 — but "almost certainly" is not a measurement, and
this campaign does not put estimates in evidence.

The `get_turn_accounting` figure is itself an example: it was assumed covered because the
C6 tests call the function, and measuring it returned 7 of 10, not 10 of 10. Assumption
would have overstated progress by three mutants and left three real gaps unrecorded.

---

## Step 0 — Re-measure before writing anything else  ⏱ ~40 min, SERIAL

    .venv/bin/python scripts/gf_mutmut.py --out .chuzom/gf/checkpoint1 \
      --names-file .chuzom/zero-tolerance-audit/gf/train.txt \
      --names-file .chuzom/zero-tolerance-audit/gf/validation.txt

At the measured 0.85 mutations/sec this costs ~39 minutes and replaces four estimates
with one number. It is also the **first checkpoint** under doc 20 §5, which permits
scoring VALIDATION at checkpoints and forbids inspecting it to choose work.

Verify all three preconditions before believing the result — each has been wrong before:
`mutant_names_count == 1986`, `git diff --quiet setup.cfg`, both stages clean.

**Why first:** every downstream decision depends on the real remaining gap. If the score
is 0.68 the plan below is roughly right; if it is 0.62 the large-function work matters
more than the mechanical classes. Ordering work against an estimate is how doc 21 came to
say "~1,650 mutants" when the truth was ~425.

---

## The remaining 540, grouped by what the work actually is

### Group A — mechanical classes, one pattern each  (~68 mutants)

| class | n | the pattern |
|---|---|---|
| C7 boundary + null flips | 33 | test AT the boundary: 0, and the threshold exactly |
| C4 ordering arguments | 13 | two names where one is a prefix of the other |
| C3 dict `.get()` defaults | 12 | call with an unknown key |
| C2 env-var overrides | 10 | set the variable, assert it takes effect |

Highest value per test in the set. C7 in particular is where real off-by-one defects live.

### Group B — large single functions  (~164 mutants)

| function | n |
|---|---|
| `execution_ledger._aggregate` (remainder) | 40 |
| `tool_surface.resolve` | 37 |
| `router._extract_retry_after` | 27 |
| `router._emit_ledger_attempt` | 22 |
| `cost._validate_routing_insert` | 19 |
| `coverage.snapshot` | 19 |

Each needs real understanding of the function, not a pattern.

### Group C — finish what is started  (~50 mutants)

The eight untouched C1 fail-open codes (~29) and the five small uncovered functions (21:
`_restore_claim` 6, `door_name` 6, `invalidate_cache` 3, `_auth_error_hint` 3,
`resolve_name` 3). The C1 pattern is established and proven at 11/11.

### Group D — the rest  (~199 mutants)

54 functions holding 145, plus `_task_aware_default_order` (22) and
`_reorder_for_agent_context` (16) — the ex-⏰ mutants, now known to be ordinary survivors.

### Group E — BLOCKED on an owner decision  (66 mutants)

`cost.fire_budget_alert` (38) and `router._native_notify` (28). Killing these means
asserting subprocess argv. Options priced in `gf_phase2_classes.md` §5; recommendation is
(b) — test platform dispatch and binary name only. **Not started, and should not be.**

---

## Sequence

    Step 0   re-measure                                    ~40 min   SERIAL
    Step 1   Group A — mechanical classes (68)             ~1 day
    Step 2   Group C — finish C1 + small uncovered (50)    ~1 day
    Step 3   CHECKPOINT re-measure                         ~40 min   SERIAL
    Step 4   Group B — large functions (164)               ~2-3 days
    Step 5   CHECKPOINT re-measure + stopping rule         ~40 min   SERIAL
    Step 6   Group D as needed to clear the floor          ~1-2 days
    Step 7   HOLDOUT, scored EXACTLY ONCE                  ~9 min    SERIAL

Doc 20 §5's stopping rule is fixed in advance: stop when TRAIN and VALIDATION both clear
the threshold **with validation's 95% lower bound above 0.80**. Never on train alone. Doc
20 §7: scoring the holdout twice, or after seeing a failing number, voids the
qualification.

---

## Can this be parallelised with agents? Partly — and the bottleneck is not the writing

### What genuinely parallelises

**Read-only audits.** No test execution, no shared state, independent outputs:

* **#38** — which of the 8 test files naming a gate script actually INVOKE one versus
  merely mention it. This one matters most: if any test is excluded from G-F for a purely
  textual reason, **the 0.5866 itself is measured over a smaller suite than intended.**
* **#37** — categorise the 153 `~/.chuzom` sites: which are chuzom state that should
  honour `CHUZOM_HOME`, which are other tools' directories that correctly should not.
* **Mutant analysis per function** — read a Group B function and its surviving mutants,
  produce a written test plan. Analysis only, no code.

**Drafting for Group A**, where the pattern is now established and the target is
mechanical.

### What does NOT parallelise, and why

* **Running pytest.** One tree, and the suite is load-sensitive — finding #19 this
  campaign was a budget guard that failed only under load. Two concurrent suites make
  every result untrustworthy.
* **Verifying kills.** `verify_kills.py` copies the test file into the shared
  `mutants/tests/` tree. Concurrent runs clobber each other's copy. A per-agent worktree
  does not help: the `mutants/` tree is a 460 MB generated artefact, and regenerating it
  per agent is both expensive and the source of eleven prior failures.
* **The mutation runs** (Steps 0, 3, 5, 7). Exclusive by nature.
* **Commits.** Each requires a green full suite first.

### The honest arithmetic

Today's ratio, measured across three classes: **drafting was roughly 30% of the effort;
verification and repair roughly 70%** — and the second part is serial. Parallel drafting
therefore caps the achievable speedup at about 1.4x even with unlimited agents.

It is worse than that in practice, because agent-written tests will contain exactly the
defects found today and every one costs a serial verify-fix-reverify cycle:

* an assertion satisfied by a superstring (`"free (local)"` in `"XXfree (local)XX"`)
* a fail-open assertion checking the code but not the exception type — a lesson that
  already failed to carry from one file to the next **within a single session**
* order-dependence invisible when the new file runs alone
* a docstring that silently excludes its own file from the run

### Recommendation

| work | agents? |
|---|---|
| #38 audit, #37 survey | **yes** — read-only, independent, high value |
| Group B per-function analysis | **yes** — analysis only, output is a written plan |
| Group A drafting (C2/C3/C4) | **yes, with the rules below in the prompt** |
| C7 boundary flips | **no** — subtle; boundary semantics are where real defects hide |
| Group B test writing | **no** — needs the understanding the analysis produced |
| all verification, all runs, all commits | **no** — serial by construction |

Any agent drafting a test must be given, in its prompt: assert values not substrings;
for a fail-open site assert the recorded exception TYPE as well as the code; never
recompute the implementation's expression in the assertion; restore every module global
touched, and assert the restoration.

**Net:** agents are clearly worth it for the three read-only audits and Group A. For the
rest, the constraint is not typing speed — it is that every claim has to be verified
per-mutant against a shared harness, one at a time.

---

## Not on this plan, needing an owner decision

1. **#38 — the exclusion rule matches prose.** Could mean G-F is measured over a smaller
   suite than intended. Fixing the rule requires amending doc 20.
2. **#37 — 153 sites ignore `CHUZOM_HOME` while `is_isolated()` certifies a sandbox.**
3. **Group E — the two notification shims (66 mutants).**
4. **#32 — the fail-open linter cannot see a fail-open that logs**; WP-13 used it as its
   instrument.
5. **agno budget pressure** reads `total_cost_usd` including $3.62/$39.79 (9.1%)
   unattributed spend.
6. **precision-tier** — 21 firings logged, 2 of 18 held-out prompts recorded gpt-4o-mini
   as final. Never instrumented; open.

## If the floor proves unreachable

Doc 21 records this in advance so it is not rationalised later: the honest output is an
**owner decision to amend or waive the 0.80 floor, recorded as an amendment, never as a
pass.** A staged floor (e.g. 0.65 now with a ratchet) is more defensible than a blanket
waiver. Two amendments and a patched instrument already exist; a third is a signal to
reassess the instrument rather than keep amending.
