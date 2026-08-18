# `routing_decisions` records one tool's traffic, and the dashboard presents it as all routing

**Status:** root cause established by reading every call site and corroborated against the
live database. Not a regression — structural, and probably always true.

This supersedes the working hypothesis in `26_HOLDOUT_CONTAMINATION.md`'s sibling
investigation, which suspected a recent breakage. There was no breakage.

---

## 1 · What was observed

    usage              newest row   2026-08-16 16:29:55   (minutes before this was written)
    routing_decisions  newest row   2026-08-13 19:53:16   (three days earlier)

643 rows landed in `usage` in the preceding 24 hours. **Zero** landed in
`routing_decisions`. Several `llm()` calls were made during the investigation itself; none
produced a routing row.

Provenance distribution in `routing_decisions`:

| provenance | rows |
|---|---|
| `unattributed` | 28,683 |
| `NULL` | 12,461 |
| `runtime` | **0** |
| `test` | 0 |

## 2 · What it is NOT

**Not a broken writer.** `cost.log_routing_decision` was exercised directly against an
isolated `CHUZOM_DB_PATH` and inserted correctly, stamping `provenance='runtime'`. The
writer-side provenance work is sound; nothing calls it.

**Not the schema.** The live table has 34 columns including `provenance`; the INSERT names
26 columns with 26 placeholders. They match.

**Not a recent change.** See below — the guard predates this audit.

## 3 · The cause

`router.route_and_call` declares

```python
classification_data: dict | None = None,
```

and `router.py:1971` guards the analytics write with

```python
if classification_data:
    await cost.log_routing_decision(...)
```

A caller that simply does not mention the parameter gets `None`, the guard is falsy, no row
is written, **and nothing anywhere records that a row was skipped.**

Counted across every call site:

| module | `route_and_call` calls | passes `classification_data` |
|---|---|---|
| `tools/routing.py` | 2 | **yes** — `llm_route` (line 410), `llm_auto` (line 592) |
| `tools/text.py` | 7 | **no** — the whole `llm(task=…)` family |
| `tools/agentic.py` | 1 | no |
| `route_server.py` | 1 | no — the gateway path |
| `context.py`, `orchestrator.py`, `quickstart.py`, `edit.py`, `tui/cli.py`, … | several | no |

Reproduce with:

```
grep -c "route_and_call(" src/chuzom/tools/text.py       # 7
grep -c "classification_data" src/chuzom/tools/text.py   # 0
```

## 4 · Therefore

`routing_decisions` is fed by **`llm_route` and `llm_auto` only**. Its last row is dated 13
August because that is when one of those two was last invoked — not because anything
stopped working.

Every consequence follows:

- the 30-day panel's model mix — **38.6% `ollama/hermes3:8b`, 35.6% `gpt-4o`, 13.9%
  `gemini-flash`** — is computed over one tool's traffic and labelled as routing overall;
- `usage` and `routing_decisions` disagree because one records all routed calls and the
  other records a subset, not because they define attribution differently;
- zero rows carry `provenance='runtime'` because the only writers that would stamp it have
  not run since the stamping was added.

The earlier finding that the "30-day" figure was really a **90-day window** still stands
and is independent of this. Both distortions were present at once.

## 5 · Why the obvious fixes are wrong

**Pass `classification_data` from every caller**, or **write the row with NULL enrichment**
— either would add a large population of rows to a table whose only purpose is *percentage
breakdowns of which model was chosen*. Every denominator moves. Every historical comparison
breaks. Nobody looking at the dashboard would know why the numbers changed.

That is the same failure as the 69.4% `gpt-4o-mini` figure, which turned out to be test
pollution silently inflating a denominator. Fixing a reporting gap by quietly changing what
is counted reproduces the defect in the other direction.

## 6 · Recommended shape — a product decision, not a bug fix

Write a row for **every** routed call, and record the absence of in-server classification as
an **explicit state**, never as a NULL.

The attribution layer can then report

> *"62% of routed calls had no in-server classification"*

instead of silently excluding those calls or silently averaging them in. `chuzom/
attribution.py` already has the right three-state shape — `ATTRIBUTED` / `UNATTRIBUTED` /
`UNKNOWN`, with `is_reportable` False while any unknown remains — and its design principle
(unknown is a first-class state) is exactly what this needs.

This requires deciding what the dashboard is *for*: "how does the router behave when it
classifies" and "what does all traffic actually use" are different questions, and the panel
currently answers the first while appearing to answer the second. Naming both, rather than
merging them, is the honest resolution — and matches the directive that opened this
investigation: *preserve legitimate semantic differences by naming them rather than forcing
one number.*

## 7 · What must not happen next

Do not build the canonical attribution layer over `routing_decisions` and call the result
"routing". Aggregating one tool's traffic correctly, and presenting it as all routing, is a
**more convincing wrong answer** than the one that exists today — because it would carry
the authority of a rigorous implementation.
