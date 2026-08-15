# Audit #37 — inventory of state-root resolutions

Date: 2026-08-15. Opened by `p0_session_store_isolation.md`, where one module resolved
`~/.chuzom` directly and therefore ignored `CHUZOM_HOME`, so `is_isolated()` returned True
while that module read and wrote outside the sandbox.

**Provenance:** the enumeration was produced by a subagent sweep and is recorded as such.
The decision-relevant figure was independently re-counted before being written down (see
"corroboration"). The per-file table is the agent's; the conclusions are not taken on
trust.

## Counts

| category | n | what it is |
|---|---|---|
| **A1** | 55 | `~/.chuzom` inside `src/chuzom/hooks/` — separate processes |
| **A2** | 120 | `~/.chuzom` everywhere else in `src/chuzom/` |
| **B** | 24 | another product's directory (`~/.claude`, `~/.cursor`, `~/.codex`, `~/.gemini`, `~/Library/…`, `~/.config/…`) |
| **C** | 46 | bare `Path.home()` used as a search root or comparison, composing no chuzom path |
| | **245** | |

Category **B** should *not* follow `CHUZOM_HOME` — redirecting another tool's config
directory because chuzom was sandboxed would be a new defect. Category **C** is inert.

Of the 120 A2 sites, **four** already honour some override: `CHUZOM_STATE_DIR`
(`surface_status.py`), `CHUZOM_EXECUTION_LEDGER_DB` (`execution_ledger.py`),
`CHUZOM_CP_AUDIT_PATH` (`control_plane/audit.py`), `CHUZOM_DB_PATH`
(`agentic/telemetry.py`). Each honours a *different* variable, none honours
`CHUZOM_HOME`, and `paths.py` is the only module that implements the canonical answer.

## The finding that matters most: one artefact, many answers

Nineteen logical artefacts are resolved by more than one expression in more than one
module. Two dominate:

| artefact | distinct resolution sites |
|---|---|
| `usage.db` | **~23** |
| `usage.json` | ~15 |
| `~/.chuzom` as a bare directory | ~32 |
| `.env` | 8 |
| `routing.yaml` | 4 |
| `profile.yaml` | 3 |
| `org-policy.yaml` | 2 |

**Corroboration:** `usage.db` was re-counted independently of the agent —
24 sites compose it from `Path.home()`/`expanduser`, against 41 total textual references
in `src/`. The agent reported 23. Same magnitude, and the discrepancy is a grep-pattern
difference, not a disagreement about the finding.

This is the defect's actual shape. `session_store.py` was not a lone module that forgot a
rule; it is one instance of a codebase where "where does state live" is answered
independently in ~150 places. Two answers that disagree is exactly what made
`is_isolated()` return True over a store it did not govern — and with `usage.db` reached
23 different ways, that disagreement has 23 chances to recur on the single file that
carries billing and routing history.

## The contentious part: hooks

The 55 A1 sites run as separate processes spawned by Claude Code. A defensible argument
says they should always use the real home: they are not under a test harness, they
coordinate state across invocations, and some legitimately read `~/.claude/`.

An equally defensible argument says a sandbox that the hooks ignore is not a sandbox —
which is precisely the failure already found.

**This is the decision, and it is the owner's.** It cannot be settled by counting.

## Options

| option | scope | effect |
|---|---|---|
| **(a)** route A2 through `paths.state_path()` | 116 sites | `is_isolated()` becomes truthful for in-process state; hooks still diverge |
| **(b)** (a) plus the 51 non-`.claude` hook sites | ~167 sites | fully truthful; changes where hook state lives for every existing user |
| **(c)** narrow what `is_isolated()` asserts | 1 site + docs | the guard stops over-claiming; the divergence remains, documented |
| **(d)** central accessor for `usage.db` and `usage.json` only | ~38 sites | ~80% of the disagreement surface on the two files that carry money and routing |

**Recommendation: (d) then (c).** (d) removes the concrete risk — one file, many
answers — on the artefacts where disagreement is most expensive, and is verifiable by the
same method that caught the original defect. (c) then stops `is_isolated()` from
certifying what it does not govern, which is the property that turned a local bug into a
silent one.

(a) and (b) are large, and neither is a bug fix: they change where every existing user's
data lives, and any of the 116 sites could have a caller depending on the current path.

## Not done here

No refactor, no diff, no path changed. Changing these resolutions relocates user data,
which is not a call to make from inside an audit. Only `session_store.py` — the one site
with a demonstrated live failure, where the suite read real prompt content — was fixed,
in `c29a673`.
