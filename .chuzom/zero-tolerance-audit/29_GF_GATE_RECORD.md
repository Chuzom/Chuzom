# G-F — gate record: NOT QUALIFIED

**Owner decision, 2026-08-17:** report G-F as NOT QUALIFIED. Do not waive it, do not amend
the floor, do not defer it. Release proceeds with this stated.

This is the gate record. It is written so a reader can tell what was measured, what could
not be, and that the outcome is a reporting decision rather than a pass wearing a different
word.

---

## Outcome

    G-F  mutation coverage  ·  NOT QUALIFIED

Not `pass`. Not `waived`. Not `deferred`. Not `accepted risk`.

**No claim is made that this release satisfies the mutation-coverage gate.** The gate is
reported as not qualified because the required independent measurement is unavailable.

## What WAS measured, and is trustworthy

Two full mutation runs over the 1,986-mutant train+validation population, at commits
`c2c2882` (baseline) and `abf25ef` (checkpoint 2). Conservative scoring per doc 20 §4 —
no-coverage, suspicious and timeout all counted as SURVIVORS.

| split | n | killed | raw | 95% lower bound |
|---|---|---|---|---|
| TRAIN | 1518 | 1138 | 0.7497 | 0.7273 |
| VALIDATION | 468 | 329 | 0.7030 | 0.6601 |
| COMBINED | 1986 | 1467 | 0.7387 | 0.7189 |

Baseline was 0.12. Roughly 280 mutants were killed by tests written during this campaign,
each verified individually against a passing no-mutant control.

**These are train/validation figures.** They describe how the suite performs against
mutants that participated in writing it. They are diagnostic evidence and remediation
input. **They are not a held-out estimate and must never be reported as one.**

One qualification on the figures themselves: doc 61 measured that 5 of 6 sampled
timeout-marked mutants are in fact killed in 4–9 seconds against their own covering tests,
making the ⏰ marking an artefact of 18 parallel workers rather than a property of the
mutant. If that rate holds across all 121 timeouts, the true combined figure is nearer
0.789. That is an estimate from n=6 and **does not replace the recorded 0.7387 anywhere.**
The direction is the safe one — mutmut marks KILLED when the suite fails, so a false
timeout inflates survivors and never kills.

## What could NOT be measured, and why

**The holdout was never scored, and now cannot be.**

Doc 20 reserved 450 mutants, sealed by committed sha256, to be scored exactly once as an
unbiased estimate of generalisation to mutants that played no part in writing the tests.

Per-mutant kill verification enumerated mutants by regex over the **generated mutant
source** rather than from `train.txt`:

```python
names = re.findall(rf"def (x_?_?{fn}__mutmut_\d+)\(", mutants_source)
```

That returns every mutant of a function. The split is an exact partition, so each
verification run swept holdout members at roughly the split ratio — 21 of 108 in the one
run measured directly. Test-writing was then **adapted to those survivor lists** (the C1
"11 of 41 → add exception-type assertions → 11/11" iteration is the clearest instance,
and similar loops ran across Groups A–C).

Observing holdout outcomes leaks information. **Conditioning test content on them makes the
holdout a development set.** Not knowing which entries were holdout does not repair that;
the decisions were still influenced by them.

`holdout.txt` was never opened, and target selection always came from the TRAIN-derived
classification. That distinction matters for describing what happened. It does not rescue
the estimator.

**Regenerating is also unavailable.** Doc 20 §7 voids qualification if "the sample was
regenerated after seeing a failing score", and 0.12, 0.5866, 0.6360 and 0.7387 have all
been seen.

This was the audit's own method, not a tooling failure. Full detail: **doc 26**.

## Evidence

| what | where |
|---|---|
| pre-registered protocol | `20_GF_QUALIFICATION_PROTOCOL.md` |
| contamination post-mortem | `26_HOLDOUT_CONTAMINATION.md` |
| checkpoint 2 measurement | `evidence/gf_checkpoint2.md`, commit `e3688d2` |
| pre-registered prediction | `evidence/gf_checkpoint_prediction.md` |
| timeout artefact | task #61 record, sampled 2026-08-16 |
| mutation run artefacts | `.chuzom/gf/checkpoint/` |

## Requalification

Requires a **fresh sealed split from mutants whose outcomes have not been observed**, taken
after test-writing has stopped, with the standing rule that every per-mutant verification
filters its candidate list against `train.txt` **before** running and never enumerates from
mutant source.

`gf_phase2_classes.md`'s survivor classification remains accurate and is the ready-made work
list for that effort.

Requalification is deferred, not abandoned. It should not be attempted while tests are
still being added, because that is the condition under which the first attempt failed.

## What this does not affect

The other gates are unchanged: **G-A, G-B, G-C, G-D PASS; G-E satisfiable.**

The held-out **quality** benchmark (`f541482`) is a separate instrument and is unaffected:
chuzom q=4.17 vs static-chain 4.50 vs premium 4.50, delta −0.33. Chuzom is not the champion
on that benchmark, and that result stands as previously recorded.
