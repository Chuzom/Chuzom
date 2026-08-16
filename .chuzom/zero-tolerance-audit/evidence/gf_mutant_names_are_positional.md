# A source fix silently re-points 26 sealed holdout names

**Status:** established by measurement, not argument. Consequence for sequencing only —
no protocol amendment required, because the conflict is avoidable by ordering.

## What prompted this

The owner approved fixing three production defects found by the Group B mutation work,
and chose to run the checkpoint AFTER those fixes to save a run. Both choices are sound
on their own. Together they interact with the sealed split in a way the question did not
surface, which is a defect in the question rather than in the answer.

## The measurement

mutmut names a mutant by its POSITION in the function's source:

    chuzom.coverage.x_snapshot__mutmut_7   = the 7th mutation, in source order

Confirmed directly in the generated tree rather than inferred from documentation:

    $ grep -n "def x_snapshot__mutmut_" mutants/src/chuzom/coverage.py | head
    1003: def x_snapshot__mutmut_orig()
    1063: def x_snapshot__mutmut_1()
    1123: def x_snapshot__mutmut_2()
    ...
    182 variants generated for this one function

Inserting a statement into a function inserts new variants at that point and shifts the
index of every variant after it. The name is stable only while the source is.

## The blast radius

Counted against the three committed partition files:

| split | `coverage.x_snapshot` | `cost._validate_routing_insert` | affected |
|---|---|---|---|
| train (1518) | 55 | 27 | 82 |
| validation (468) | 18 | 8 | 26 |
| **holdout (450)** | **18** | **8** | **26 (5.8%)** |
| total (2436) | 91 | 43 | 134 (5.5%) |

Defect (a) and (c) both edit `coverage.snapshot`; defect (b) edits
`_validate_routing_insert`. All three land inside the two functions above.

## Why this matters more than the percentage suggests

The holdout is scored EXACTLY ONCE (doc 20 section 7) and its contents must never be
inspected. Its integrity rests entirely on a committed sha256 of the name list.

That hash covers the FILE. It does not cover what the names REFER TO. After the fix the
file is byte-identical, the hash verifies clean, and 26 of the 450 names denote different
mutations than the ones that were sealed. The seal reports success while blind.

This is the eleventh instance of the campaign's most-repeated failure shape — a
self-validating guard that checks its own artefact instead of an independent declaration
(methodology (a)). It is worth recording precisely because the guard would NOT have
flagged it.

## Why "just regenerate the split" is not available

Doc 20 section 7 lists as a voiding condition:

> the sample was regenerated after seeing a failing score

Failing scores have been seen: 0.12 (baseline), 0.5866, 0.6360. Regenerating the split
now voids the qualification outright. This is the decisive constraint — not a preference.

## Resolution: order, not amendment

No amendment is needed. A third amendment would itself be a signal to reassess the
instrument (doc 21's own honest-failure criterion 2), so avoiding one matters.

    1. checkpoint  -> on the sealed tree, source unchanged     [running]
    2. stopping rule (doc 20 section 5)
    3. holdout     -> scored once, sealed tree, source unchanged
    4. the three defect fixes land                             [#59]

The owner gets all three fixes and a valid qualification. The only thing given up is
fixes-before-checkpoint ordering, which was chosen for economy rather than principle.

A further point in favour of this order: the operating rules already forbid changing the
tree under a running harness, so the fixes could not have preceded a checkpoint that was
going to run anyway. The ordering was over-determined.

## Correction to the framing of defect (a)

Recorded here because the original diagnosis, written in the test's xfail reason, named
the wrong root cause.

Stated there as a missing type check. It is better described as a HOISTED PARSE. The
sibling module `failopen._snapshot` has the identical loop and is correct:

    code = str(json.loads(line).get("c", ""))   # .get INSIDE the try
    except Exception: malformed += 1; continue  # AttributeError caught here

`coverage.snapshot` reads `event` twice (`"k"` then `"d"`), so the parse could not stay
inline and was hoisted to its own statement — leaving `.get` outside the guard. Verified:

    json.loads('[1,2,3]').get('c','')            -> AttributeError CAUGHT   (failopen)
    event = json.loads('[1,2,3]'); event.get('k') -> AttributeError ESCAPES (coverage)

So this is not a class of defect spanning both modules; `failopen` is already correct and
needs no change. Checking that was worth doing — "a correction applied to one file is not
a correction to the class" has been wrong three times this session, and this is the first
time the check came back negative. Recording the negative result matters as much as the
positives, or the habit only ever appears to pay off.
