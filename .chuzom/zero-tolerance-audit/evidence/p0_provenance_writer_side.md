# P0 — provenance is now written, and NULL is no longer read as "real"

Date: 2026-08-15. Closes W2.1 and W2.2; corrects the attribution rule this same session
introduced.

## Root cause (W2.2)

**Nothing in `src/chuzom/` ever wrote `routing_decisions.provenance`.** The column is
`TEXT DEFAULT NULL`, and `cost.log_routing_decision`'s INSERT listed 25 columns without
it. Every row — genuine or synthetic — was born NULL.

`0aab32f` then marked one known-bad population `unattributed` **retroactively**. That is
what made `provenance IS NULL` *look* like "real traffic": it actually meant *"not yet
cleaned up"*.

The guard itself is correctly placed (`cost.py`, before `_get_db()` and the INSERT) and
carries an honest comment naming this path as the one that put 28,536 rows into a user's
database. It fails for a different reason: `_refuse_unisolated_test_write` only fires when
`PYTEST_CURRENT_TEST` is set, so a subprocess, script or benchmark harness writing
real-looking rows passes straight through.

Two further self-validating fields found alongside it:

* `is_real` is `INTEGER DEFAULT 1` — a column named "is real" reads `1` on rows that are
  demonstrably synthetic.
* the secondary fixture guard checks `cost_usd in (0.001, 0.003)`; the second synthetic
  population carries `0.01` and misses by one value in a hardcoded tuple. The code's own
  comment already warned that guard "is not load-bearing and must not be treated as
  such" — a second population then proved it.

## The correction to my own rule, stated plainly

Earlier this session I built `attribution.py` keyed on `provenance IS NULL` = attributed,
and argued it was *more* robust than filtering on `classifier_type`. **That was wrong.**

I verified the two columns were correlated in the data and never verified *what writes
provenance*. It is a marking artefact, not a property of the row. The rule reproduced the
historical dashboard numbers exactly — which is why it looked right. It was reproducing
the bug.

## The fix

### Writer side — `cost._write_provenance()`

    PYTEST_CURRENT_TEST set, or CHUZOM_ALLOW_STUBS=1  ->  "test"
    otherwise                                          ->  "runtime"

`provenance` is now in the INSERT column list. Origin is recorded at the point of writing,
which is the only version that cannot drift: a cleanup pass can always be out of date, and
a reader cannot recover a fact the writer never stored.

`CHUZOM_ALLOW_STUBS=1` counts as test provenance — it is the documented escape hatch for
writing stub data deliberately, and data written through an escape hatch is not user
traffic. The flag says so.

### Reader side — three states, not two

    ATTRIBUTED    provenance in {"runtime"}
    UNATTRIBUTED  provenance in {"unattributed", "test"}
    UNKNOWN       NULL, empty, or a value this version does not recognise

An unrecognised marker lands in UNKNOWN rather than defaulting into a bucket, so a future
`replay`/`imported` marker written by another component becomes visible instead of quietly
inflating a share.

`AttributionResult.is_reportable` is False whenever `unknown_decisions > 0`: a share over
a partial denominator is a wrong answer stated confidently.

## What the corrected rule says about the live database

    attributed      0
    unattributed    28683
    UNKNOWN         3667
    is_reportable   False

**Zero attributed decisions.** Not because there is no real traffic, but because no row
was ever written with its origin recorded. The dashboard's 75.1% gpt-4o share was computed
over 3,667 rows whose provenance nobody ever stored.

This is the honest state. It will populate as new routing happens.

## Tests

`tests/test_p0_attribution_provenance.py`, 16 tests: writer stamps runtime/test/stub
correctly; NULL, empty and unrecognised values all report UNKNOWN and never promote;
`is_reportable` gates a mixed set; shares sum to 1.0 over the attributed denominator only,
with 50 unknown rows present that must not enter it.

## Still open — OWNER DECISION (#51)

Historical rows stay UNKNOWN. Options: backfill by fingerprint (the 3.200:1 split, single
`prompt_hash`, 100/50/0.01/500.0 constants), leave them unknown permanently, or delete
them. Each changes historical dashboard numbers, so it is not a call to make from inside
an audit.

Not attempted here: identifying **which** harness wrote them. The writer function is
known (`cost.log_routing_decision`); the caller is not.
