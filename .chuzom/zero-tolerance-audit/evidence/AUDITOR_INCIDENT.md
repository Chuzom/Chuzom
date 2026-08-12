# AUDITOR INCIDENT — damage to `~/.chuzom/usage.db` (resolved)

**Status: RESOLVED — schema repaired, writability restored, no fabricated data, backup retained.**

This records an incident caused by the **audit**, not by Chuzom. It is kept in the evidence
record because (a) honesty requires it and (b) the root cause is also a genuine product finding.

## What happened

RED-2 (economics track) set `CHUZOM_HOME` to a temporary directory, believing it isolated
`chuzom.cost._get_db()`. **It does not.** RED-2 then executed `DROP TABLE claude_usage` followed
by an incomplete `CREATE TABLE`, which landed on the user's live 63.7 MB production database at
`~/.chuzom/usage.db`.

## Responsibility

**The lead auditor is responsible.** Explicit "use a sandbox HOME, never touch real state"
safety clauses were written into the RED-4, RED-5 and RED-6 briefs and **omitted from RED-2's**.
That omission is the proximate cause. RED-2 followed the brief it was given.

## Damage assessment (read-only, before any repair)

| Table | Rows | Status |
|---|---|---|
| `claude_usage` | **0** | **emptied — historical rows lost** |
| `usage` | 14,528 | intact |
| `routing_decisions` | 27,723 | intact |
| `savings_stats` | 21,581 | intact |
| `codex_usage` | 5,892 | intact |
| `execution_events` | 3,066 | intact |
| 7 other tables | — | intact |

Two forms of schema damage from the incomplete `CREATE`:

1. **Missing `complexity`** — `cost.py:53` declares `complexity TEXT NOT NULL`, and **both**
   production INSERT sites (`cost.py:1670`, `session_spend.py:310`) name that column explicitly.
   Every future write to `claude_usage` would have failed.
2. **Missing `timestamp` default** — canonical schema is `timestamp TEXT DEFAULT (datetime('now'))`;
   the recreated table had a bare `timestamp TEXT`. `cost.py`'s INSERT **never supplies a
   timestamp**, so every row would have been written **undated**, silently corrupting every
   time-windowed savings/usage figure downstream. *RED-2 did not identify this second defect.*

## Correction to RED-2's report

RED-2 reported the loss as **"permanently unrecoverable"**. That is **overstated**.
`claude_usage` is a **derived cache**. `src/chuzom/claude_jsonl_usage.py:15` reads Claude usage
from `~/.claude/projects/**/*.jsonl`, and **165 transcript files are present on disk**. The
underlying source data therefore still exists and the table is substantially re-derivable.

Not recoverable by that route: the chuzom-computed columns (`cost_saved_usd`, `time_saved_sec`)
and any history predating retained transcripts.

Backfill was **not** performed — the user chose schema repair only, explicitly to avoid any
fabricated data. Correct call: an empty table is honest; a synthesized one would have been
exactly the "unknown silently becomes data" failure this audit exists to detect (`02_FAILURE_MODEL.md` I-2).

## Remediation performed (user-authorized)

1. WAL-safe atomic backup → `~/.chuzom/usage.db.pre-repair.20260811_140320` (63,692,800 bytes).
2. `claude_usage` rebuilt to the canonical `cost.py` schema, **preserving** the live extra
   columns (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`,
   `cache_read_input_tokens`, `routing_overhead_usd`).
3. Verified — both production INSERT shapes execute successfully **inside transactions that were
   rolled back**, so writability was proven without leaving a single fabricated row.

| Verification | Result |
|---|---|
| `PRAGMA integrity_check` | `ok` |
| `cost.py` INSERT shape | OK, `timestamp` auto-populates |
| `session_spend.py` INSERT shape | OK |
| `claude_usage` final row count | **0** (nothing fabricated) |
| Collateral data loss across other 12 tables | **none** |

Three tables grew during the window (`savings_stats` +3, `execution_events` +1,
`quota_snapshots` +1) — live chuzom hooks writing during the session, not damage.

### Process note

The first rebuild attempt **silently no-opped**: `sqlite3 db ".timeout 10000" <<SQL` executes the
argument and exits *without reading stdin*. The command printed a success message while doing
nothing. It was caught only by re-reading the schema rather than trusting the exit status —
which is, unavoidably, the same lesson this audit keeps applying to Chuzom itself: **a success
message is not evidence of success.**

## Product findings arising from this incident

### RED2-07 (confirmed) — `CHUZOM_HOME` does not isolate `cost._get_db()`

A documented-looking environment variable does not redirect the database path. This is a real
testability **and safety** defect: it makes it impossible for a contributor, CI job, or test to
safely exercise cost/telemetry code without risking the developer's real data. **It caused actual
data loss during this audit** — the strongest possible demonstration of impact.

### New: no automatic backup before destructive schema operations

Chuzom performs schema work on a database holding months of user history with no pre-flight
snapshot. The codebase already demonstrates the right instinct elsewhere (RED-4's positive
finding RED4-05: corrupt-JSON files are backed up before rewrite). That philosophy is not applied
to the SQLite stores.

## Safety action taken during the audit

On discovering the root cause, an urgent stop was issued to RED-5 (reliability/persistence) —
the track deliberately testing SQLite corruption, concurrent writers and process kills, and
therefore the most likely to repeat the incident — instructing it to prove path resolution lands
inside its own tmpdir before any destructive DB operation, and to mark scenarios
`NOT TESTED — cannot be safely isolated` rather than risk real data. No further damage occurred.
