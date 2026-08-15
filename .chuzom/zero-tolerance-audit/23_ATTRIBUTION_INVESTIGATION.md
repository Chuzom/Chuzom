# 23 · Routing-attribution consistency — Phase 1 investigation

Date: 2026-08-15. Phase 1 only: lineage traced, root cause established, **no code changed**.
Written before implementation per the directive's §3 and §18.

---

## A. Root cause

**The two surfaces do not read the same table, and cannot apply the same attribution rule
even in principle.**

    sqlite> PRAGMA table_info(usage)               -> 22 columns, classifier_type ABSENT
    sqlite> PRAGMA table_info(routing_decisions)   -> 34 columns, classifier_type PRESENT

`MODELS this session` reads `usage`. The 30-day dashboard reads `routing_decisions`. The
attribution semantics fixed in `0aab32f` — exclude `classifier_type='unknown'`, split
attributed from unattributed — are expressed as a **column filter on a column the other
table does not have.**

There is a second, independent reason the numbers differ, and it is the one that explains
the specific contradiction reported:

    _FREE_PROVIDERS = {"ollama", "codex", "gemini_cli"}
    paid = [r for r in clean if r["provider"] not in _FREE_PROVIDERS | {"subscription"}]
    tools = _aggregate(paid_rows) if paid_rows else {}          # session-end.py:1904

**The MODELS panel is built from PAID rows only.** `ollama/hermes3:8b` — the router's
single largest destination at 38.6% of attributed routing decisions — is a free local
provider and is therefore **structurally invisible** in a panel titled "MODELS this
session". So is every Codex and Gemini-CLI call.

The surfaces disagree because Path A answers *"what did the router choose?"* over all
providers, and Path B answers *"what did we pay for this session?"* — while both are
labelled as models.

---

## B. Data lineage

### Path A — 30-day routing-decisions attribution

    router decision
      -> cost.py writer (guarded by _refuse_unisolated_test_write, 0aab32f)
      -> usage.db :: routing_decisions        (34 cols, has classifier_type)
      -> cost.get_quality_report()            filters classifier_type != 'unknown'
      -> attributed / unattributed split      (added by 0aab32f)
      -> dashboard 30-day panel

### Path B — MODELS this session

    model invocation
      -> cost.log_usage()
      -> usage.db :: usage                    (22 cols, NO classifier_type)
      -> session-end.py::_query_session_data(session_start)
             SELECT task_type, model, provider, input_tokens, output_tokens, cost_usd
             FROM usage WHERE timestamp >= ? AND success = 1
         then: drop rows where _is_test_model(model)
         then: SPLIT by provider -> paid / subscription(cc) / free
      -> session-end.py::_aggregate(paid_rows)     keyed by task_type
      -> session-end.py:2024  re-aggregate by model
      -> ui/session_summary.py:583  "MODELS this session"

---

## C. A real defect inside Path B, independent of the disagreement

`_aggregate` stores **per-tool totals** next to **per-model counts**:

    tools[tool]["in"]  += in_tok                                  # sum over ALL rows
    tools[tool]["models"][model] = ...get(model, 0) + 1           # count per model

The panel then multiplies one by the other (`session-end.py:2036`):

    model_agg[model]["tokens"] += (in_tok + out_tok) * count
    model_agg[model]["cost"]   += cost * count

`in_tok`/`out_tok`/`cost` are the **tool's totals**, not that model's. For a task_type with
total tokens `T` and models `{A: 3, B: 2}`, the panel reports `3T` for A and `2T` for B —
`5T` for a tool that consumed `T`.

**Inflation factor = the number of rows for that task_type.** `calls` is correct; `tokens`
and `cost` are inflated multiplicatively, and the panel's `total` line sums the inflated
figures.

This is a straightforward correctness bug and does not depend on any architectural
decision below.

---

## D. Divergence map

| dimension | Path A (routing decisions) | Path B (MODELS this session) |
|---|---|---|
| database | `usage.db` | `usage.db` |
| DB path resolution | `cost.py` (its own expression) | `os.path.join(STATE_DIR, "usage.db")`, STATE_DIR hardcoded from `Path.home()` |
| honours `CHUZOM_HOME` | no | no |
| table | `routing_decisions` | `usage` |
| writer | router decision path | `cost.log_usage()` |
| time scope | 30 days | `timestamp >= session_start` |
| session identity | none (time window) | session start time, not a session id |
| success filter | — | `success = 1` |
| provider scope | all | **paid only** — free/subscription dropped |
| `classifier_type='unknown'` | excluded (0aab32f) | **column does not exist** |
| attributed / unattributed | explicit split (0aab32f) | concept absent |
| test-data exclusion | `provenance='unattributed'` marking | `_is_test_model(model)` name heuristic |
| aggregation grain | per decision | per task_type, then multiplied per model |
| duplicate handling | not verified | not verified |

Two different test-exclusion mechanisms is itself a divergence: a test row with a
realistic model name passes Path B's heuristic, and a real row with a test-looking name is
dropped from it.

---

## E. `usage.db` resolution

Already inventoried in `evidence/audit_37_state_root_inventory.md`: **~23–24 distinct
expressions** construct this path across `src/`, none via a canonical accessor, and
`session-end.py`'s is one more (`STATE_DIR` composed at module import). Independently
re-counted for that audit; the figure is not an estimate.

Consequence for this investigation: the two paths *happen* to agree on the file today
because both compose `~/.chuzom/usage.db`, but nothing enforces it, and neither honours
`CHUZOM_HOME`. Test isolation via `CHUZOM_HOME` therefore does not protect either path —
which is the same defect class already fixed in `session_store.py` (`c29a673`) and left
open for the owner elsewhere.

---

## F. The semantic question, stated before proposing an architecture

Per the directive's §11, these must not be forced into one number. The system currently
conflates at least four distinct quantities under the word "models":

1. **Attributed routing decisions** — the router chose X, with a known classifier.
   (`routing_decisions`, `classifier_type != 'unknown'`)
2. **All routing decisions** — including unknown-classifier ones.
3. **Paid model invocations** — what was billed. (`usage`, paid providers)
4. **All model invocations** — including free/local and subscription.

The 30-day panel reports (1). `MODELS this session` reports (3) — while its title claims
(4). **The panel's title is the clearest single defect in the whole picture**: a user
reading "MODELS this session" on a session where 38.6% of routing went to a local model
sees a list that excludes it entirely.

---

## G. Proposed architecture — for owner approval, not yet built

1. **Name the four quantities** in one module, with the canonical filters attached to each
   — so `classifier_type='unknown'` is decided once and consumed, never re-decided.
2. **One accessor for the database path**, used by both writers and all readers.
3. **Path B consumes the canonical layer** for whichever quantity the panel is meant to
   show — and the panel is retitled to match, or widened to all providers.
4. **The multiplication bug (§C) is fixed regardless** of any of the above; it is wrong
   under every interpretation.
5. **Consistency tests** per the directive's §13, including the invariant that
   `attributed + unattributed == eligible` and that the same fixture produces the same
   answer through every surface claiming the same quantity.

## H. What is NOT yet established

Recorded so the report is not read as more complete than it is:

* Path A's writer and DB-path expression were read during the `0aab32f` work but not
  re-traced today; the schema facts above are measured, the writer detail is from memory
  and must be re-verified before implementation.
* Duplicate-event handling on both paths is unverified.
* Whether any CLI/API surface reports a third answer has not been swept.
* The `subscription` (cc) and `free` row groups are computed by `_query_session_data` and
  then used elsewhere in the dashboard; which panels consume them is untraced.

**No code has been changed.** The next step is the repository-wide inventory (§5) and the
Path A re-trace, then the canonical layer.

---

## I. The 38.6% discrepancy — RESOLVED, and it exposed a bigger problem

The working note recorded "hermes3:8b 38.6%" as a 30-day figure. The canonical rule over
30 days gives 0.6%. The note's WINDOW LABEL was wrong:

| window | top attributed models |
|---|---|
| 7 days | gpt-4o 76.2%, opus 23.7%, hermes3 **0.1%** |
| 30 days | gpt-4o 75.1%, opus 23.4% |
| **90 days** | **hermes3 38.6%**, gpt-4o 35.6%, gemini-flash 13.9% |

`chuzom.attribution.routing_attribution(..., since_sql="-90 days")` reproduces
**38.6% / 35.6% / 13.9%** exactly. The canonical implementation agrees with the earlier
finding; only the label was wrong. **No contradiction remains between the two figures.**

## J. NEW P0 — a second synthetic population is counted as ATTRIBUTED

Charting the transition surfaced something worse than a stale note.

    date         gpt-4o : opus       ratio
    2026-07-26      208 : 65         3.200
    2026-07-30      400 : 125        3.200
    2026-07-31      336 : 105        3.200
    2026-08-08      224 : 70         3.200
    2026-08-11      240 : 75         3.200
    2026-08-12      608 : 190        3.200

Exactly 3.200 on eight of nine days. Real traffic does not hold a fixed ratio to three
decimal places. Those 2,373 rows carry:

* **0** distinct `session_id`
* **1** distinct `prompt_hash`
* **1** distinct `task_type`

and they are all `provenance IS NULL` — i.e. **counted as attributed routing**.

Separately, `classifier_type='gateway'` (6,310 decisions, the largest population before
August) disappears entirely after Aug 1, replaced by `heuristic` alone.

### What this means

**`provenance IS NULL` does not mean "real traffic".** Finding #30 caught ONE synthetic
population — the `gpt-4o-mini` rows, correctly marked `unattributed`. This is a **second,
larger, unmarked one**, and it is inside the attributed set.

Consequences, stated plainly:

1. The dashboard's 75.1% gpt-4o figure is computed over synthetic rows.
2. **The canonical layer added in this work inherits the same contamination.** A correct
   rule over contaminated data still yields a wrong answer; the rule is not the defect.
3. The apparent collapse of local routing (38.6% → 0.1%) may be an artefact of synthetic
   volume swamping real traffic rather than a routing regression — **or both**. Not yet
   distinguishable.

**Finding #30 is incomplete, not wrong.** Tracked as task #51. No further attribution work
should be built on this data until the writer is identified and the marking decided.
