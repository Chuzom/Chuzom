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

---

## W2.1 CLOSED — the writer identified

`tests/test_quality_guard.py::_create_routing_decision`. Every constant in the suspect
rows matches it field for field:

    task_type="code"            profile="balanced"       classifier_type="heuristic"
    classifier_confidence=0.9   classifier_latency_ms=10.0
    complexity="moderate"       budget_pct_used=0.5
    input_tokens=100            output_tokens=50
    cost_usd=0.01               latency_ms=500.0

That also explains the **3.200:1 gpt-4o:opus ratio** that first looked impossible for real
traffic: it is a helper invoked a fixed number of times per test, not a workload.

The file has **no database isolation whatsoever** — no `CHUZOM_DB_PATH`, no
`CHUZOM_HOME`, no `tmp_path`. It called `log_routing_decision` against whatever
`get_config().chuzom_db_path` resolved to, which is the user's real `~/.chuzom/usage.db`.

## The hole is already closed — verified, not assumed

`_refuse_unisolated_test_write` (added by `0aab32f`, after these rows were written) blocks
this path. Measured directly:

    rows BEFORE        41144
    run test_quality_guard.py   18 passed
    rows AFTER         41144
    provenance='test'  0

Zero rows written, and zero `provenance='test'` rows — because the guard returns *before*
the INSERT, so the new writer-side stamp is never reached. Both mechanisms are working,
in the right order.

The 2,373 rows are therefore **historical damage from a window that is now shut**, not an
ongoing leak.

## What this leaves for #51

The population is now fully characterised: known writer, known constants, known reason it
was never marked, and confirmed not to be growing.

Backfilling by fingerprint is therefore low-risk in the technical sense — the fingerprint
is exact and cannot collide with real traffic (no real call has *all* of
100/50/0.01/500.0/0.9/10.0/0.5). It remains an **owner decision** because it rewrites
historical dashboard figures, and this audit does not silently restate a user's history.

**Also worth noting:** `test_quality_guard.py` writing to the production DB was possible
because nothing in the test declared isolation. Finding #30's fix guards the *writer*;
nothing yet requires a *test* to declare where its state goes. That is a separate gap
from #51 and is not addressed here.
