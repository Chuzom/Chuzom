# The G-F holdout is contaminated, and the contaminant was my verification method

**Owner decision, 2026-08-16:** declare the holdout contaminated, do not score it, report
the G-F work as validation-style evidence, and drop the claim to a pre-registered unbiased
holdout estimate.

This document is the record. It is written so a reader who was not present can verify every
claim in it independently.

---

## 1 · What the holdout was for

Doc 20 pre-registered a deterministic three-way split of the 2436 mutants in G-F scope:

    TRAIN       1518    used to choose what to fix and to iterate
    VALIDATION   468    scored only at checkpoints, never inspected to choose targets
    HOLDOUT      450    scored EXACTLY ONCE, at the very end, and never inspected

Only `holdout.txt`'s sha256 is committed; the list itself is gitignored. Its whole purpose
is to give one unbiased estimate of how well the tests generalise to mutants that played no
part in writing them. §7 makes it voiding to inspect its contents or to score it twice.

## 2 · How it was contaminated

Per-mutant kill verification — the step that checks a newly written test actually kills the
mutants it claims to — enumerated mutant names by regex over the **generated mutant
source**:

```python
src = pathlib.Path(f"mutants/src/chuzom/{module}.py").read_text()
names = re.findall(rf"def (x_?_?{fn}__mutmut_\d+)\(", src)
```

That returns **every** mutant of the function. It does not consult `train.txt`. So each
verification run swept train, validation and holdout members alike, and printed each one's
kill/survive outcome.

This was the method used throughout Groups A, B, C and E.

## 3 · Evidence, reproducible in one command

Measured for Group E's two functions:

| function | train | validation | **holdout** | total |
|---|---|---|---|---|
| `cost.fire_budget_alert` | 38 | 12 | **12** | 62 |
| `router._native_notify` | 28 | 9 | **9** | 46 |

21 of the 108 mutants in that single verification run were holdout members. Verify with:

```
python - <<'PY'
import pathlib
def load(f): return {l.strip() for l in pathlib.Path(f).read_text().splitlines() if l.strip()}
hold = load(".chuzom/gf/holdout.txt")
for fn in ("chuzom.cost.x_fire_budget_alert__", "chuzom.router.x__native_notify__"):
    print(fn, sum(1 for n in hold if n.startswith(fn)))
PY
```

The same arithmetic applies to every function verified in Groups A–C. The split is an exact
partition, so any exhaustive per-function sweep necessarily includes holdout members in
proportion to the split (roughly 62/19/19).

## 4 · Why this actually breaks the estimator

Three distinct things happened, and only the third is fatal. The distinction matters
because collapsing them would either overstate or understate the damage.

**(a) Reading the holdout membership list — did NOT happen.** `holdout.txt` was never
opened to select a target. Every target came from the TRAIN-derived classification in
`gf_phase2_classes.md`.

**(b) Observing outcomes for mutants that are in the holdout — happened.** By itself this
leaks response information but changes no decision.

**(c) Adapting test-writing to those observed outcomes — happened.** This is the one that
matters. The clearest instance is recorded in the session history: a C1 fail-open file
reported "11 of 41" kills, I inspected the survivor list, added exception-type assertions
aimed at what survived, and reached "11/11". Similar iterate-on-survivors loops ran across
Groups A, B and C.

Once test content is conditioned on outcomes drawn from a pool containing holdout members,
the holdout is no longer measuring generalisation to unseen mutants. It has partly become a
development set. Not knowing *which* entries were holdout does not fix this — the decisions
were still influenced by them.

## 5 · Why regenerating the holdout is not available

Doc 20 §7 lists as a voiding condition:

> the sample was regenerated after seeing a failing score

0.12 (baseline), 0.5866, 0.6360 and 0.7387 have all been seen. Regenerating now collides
with that clause directly. It would also require a third amendment, and doc 21's own
honest-failure criterion 2 states that a third amendment is the signal to reassess the
instrument rather than to keep amending it.

## 6 · What is unaffected, and what must now be relabelled

**Unaffected.** Both mutation runs were invoked as

    gf_mutmut.py --names-file .../train.txt --names-file .../validation.txt

so the holdout was never scored. The checkpoint numbers stand exactly as recorded:

| split | n | killed | raw | 95% LB |
|---|---|---|---|---|
| TRAIN | 1518 | 1138 | 0.7497 | 0.7273 |
| VALIDATION | 468 | 329 | 0.7030 | 0.6601 |
| COMBINED | 1986 | 1467 | 0.7387 | 0.7189 |

**Relabelled.** These are train/validation figures. They are NOT a held-out estimate and
must never be reported as one. The ~250 individually verified kills remain real work
against real coverage gaps; what is lost is the claim that their generalisation was
measured on untouched mutants.

Note also that the stopping rule was never met — validation needs 392 kills and has 329 —
so the holdout would not have been reached this session regardless. The contamination
removed an option that was not yet in play.

## 7 · Corrective action, effective immediately

**Every per-mutant verification filters its candidate list against `train.txt` before
running, and never enumerates from mutant source.**

```python
train = {l.strip() for l in TRAIN.read_text().splitlines() if l.strip()}
names = sorted(n for n in train if n.startswith(prefix))   # not a regex over source
```

This should have been true from the first verification in this campaign. It was not, and
nothing in the tooling would have flagged it — which is the point of §8 below.

## 8 · What a later reader should take from this

The audit's most-repeated finding is that **a guard which validates its own artefact reports
clean while blind**. This is the twelfth instance, and the first where the blind guard was
my own procedure rather than something in the codebase.

Every individual step was defensible. Targets came from TRAIN. Tests were written before
verification. The control passed. mutmut behaved correctly. The split file was never opened.
The failure is that *enumerating from source* silently substituted a different population
for the intended one, and no step in the loop ever compared the population being verified
against the population the protocol authorised.

The generalisable rule: **when a protocol partitions a population, every operation on that
population must name its partition explicitly.** An operation that says "all mutants of
this function" instead of "the TRAIN mutants of this function" is not a shortcut; it is a
different experiment.

## 9 · Consequence for G-F

G-F remains **NOT QUALIFIED** (doc 19 verdict unchanged) and can no longer be qualified via
this holdout. Release (#10) is now blocked on an owner decision about the 0.80 floor —
amend it, waive it, or ship with G-F stated as not qualified — rather than on a holdout
number that no longer exists.

Rebuilding a clean qualification instrument from a fresh sealed split, after test-writing
has stopped, remains possible later. It is deferred, not abandoned, and it should not be
attempted while tests are still being added.
