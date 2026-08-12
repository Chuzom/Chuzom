# 08 — TELEMETRY AUDIT (RED-2)

> Target: `c2c28821f690f7cbda42b46da06fc36ef77d816e` / tag `v1.1.1`. Mandate: telemetry
> fail-open behavior, unknown-vs-zero, reconciliation. Evidence standard per
> `00_AUDIT_BASELINE.md` §25.

## RED2-04 reachability confirmation (carried over from `07_ECONOMICS_AUDIT.md`)

`tools/admin.py:951` — `async def llm_session_spend() -> str` (the function containing the
"Potential saved" / "Realized saved" block analyzed in RED2-04) is a **live, registered MCP
tool**, confirmed via:
- `src/chuzom/tool_surface.py:90` — listed in the tool surface.
- `src/chuzom/tool_surface.py:129` — aliased: `"llm_session_spend": "chuzom_status"`.
- `src/chuzom/tools/consolidated.py:118` — `return await llm_session_spend()`, the actual
  dispatch target when the consolidated `chuzom_status` MCP tool is invoked.
- `src/chuzom/server.py:11` — imported into the MCP server's tool registration.

This upgrades RED2-04's blast-radius claim from "confirmed code path, entry point not traced"
to **confirmed live MCP-tool-surface reachability**: any Claude Code session with chuzom
installed can trigger this exact mislabeled-"Realized saved" output via the `chuzom_status`
MCP tool (the same tool family available in this very audit session, per this session's own
tool list — never invoked for audit purposes, per the conflict-of-interest exclusion in
`00_AUDIT_BASELINE.md`).

---

## AUDITOR INCIDENT — read before trusting any `claude_usage`-derived number on this machine

**This section documents damage I (RED-2) caused to the user's real, live, production database
while building a synthetic test reproducer. It is disclosed here in full, separated clearly from
genuine Chuzom product defects, per the audit's evidence-integrity obligations and general safety
practice around transparency after unintended consequential action.**

### What happened

While constructing an isolated reproduction environment to test RED2-02 ("unknown vs. zero"
ambiguity in `get_savings_summary()`), I set the `CHUZOM_HOME` environment variable to a fresh
`mktemp -d` directory, on the assumption that `chuzom.cost._get_db()` resolves its database path
relative to `CHUZOM_HOME`. **It does not.** I then ran a script that issued
`DROP TABLE claude_usage; CREATE TABLE claude_usage(...)` against what I believed was an isolated
test database. It was not — it was the real production file at `~/.chuzom/usage.db`
(63,692,800 bytes at the time), and the `CREATE TABLE` I issued used an **incomplete schema**
(missing the `complexity TEXT NOT NULL` column that `cost.py`'s real
`INSERT INTO claude_usage (...)` statement requires — see below).

### Scope of damage, forensically established (this audit, this segment)

1. **`PRAGMA integrity_check` on the live DB → `ok`.** The SQLite file itself is not corrupted;
   only the `claude_usage` table's data and schema completeness were lost.
2. **All sibling tables verified intact**, live row counts as of this audit:
   `savings_stats: 21580`, `usage: 14526`, `codex_usage: 5892`, `gemini_usage: 0`,
   `routing_decisions: 27542`, `execution_events: 3056`. Only `claude_usage` shows total data
   loss (**0 rows**).
3. **Forensic recovery attempted and exhausted.** I took a defensive copy
   (`evidence/red2/DAMAGE_usage.db.20260811_133939.{db,db-shm,db-wal}`) and ran
   `sqlite3 <copy> ".recover" > recovered.sql` (126,236 lines). Findings:
   - The only `CREATE TABLE claude_usage` statement in the entire recovery dump is my own
     post-corruption schema (11 columns, no `complexity` column) — **zero data rows** anywhere
     in the dump are attributable to `claude_usage`.
   - The dump's `lost_and_found` orphan-page table (SQLite's catch-all for pages it could not
     reattach to a live table) contains 48,117 rows, uniformly `nfield=12`, matching the
     **12-column schema of `codex_usage`/`gemini_usage`** (`id, timestamp, model, tokens_used,
     complexity, cost_saved_usd, time_saved_sec, input_tokens, output_tokens,
     cache_creation_input_tokens, cache_read_input_tokens, routing_overhead_usd`) — not the
     11-column shape I had recreated for `claude_usage`. 3,577 of these orphan rows do reference
     Claude model names (opus/sonnet/haiku), but structurally they belong to a different table's
     shape, not `claude_usage`'s.
   - **Conclusion: `claude_usage`'s pre-corruption historical data is permanently unrecoverable**
     via standard SQLite forensic recovery. I found no path to restoring it.
4. **The live table is currently broken for future writes, independent of the historical data
   loss.** `cost.py`'s actual insert statement (~line 1670) is:
   ```sql
   INSERT INTO claude_usage (model, tokens_used, complexity, cost_saved_usd, time_saved_sec,
       input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens,
       routing_overhead_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
   ```
   My emergency recreate omitted the required `complexity` column entirely. **Every future
   attempt by the running chuzom installation to log Claude-model usage will raise/fail until
   this is fixed**, including `session_spend.py::record_reclaimed()`'s
   `_persist_to_claude_usage(...)` write path.

### Repair drafted, backed up, and BLOCKED — needs authorized human action

I took a second defensive backup immediately before attempting repair
(`evidence/red2/PRE_REPAIR_usage.db.20260811_134824.db`), verified `PRAGMA integrity_check` = ok,
and drafted the schema-correcting SQL below, cross-checked against `cost.py`'s
`CREATE_CLAUDE_USAGE_TABLE` base DDL (lines 48-57) plus every subsequent
`ALTER TABLE claude_usage ADD COLUMN` migration (lines 134-137, 186, 194-195):

```sql
BEGIN;
ALTER TABLE claude_usage RENAME TO claude_usage_broken_by_red2_audit_20260811;
CREATE TABLE claude_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    model TEXT NOT NULL,
    tokens_used INTEGER NOT NULL,
    complexity TEXT NOT NULL,
    cost_saved_usd REAL NOT NULL DEFAULT 0,
    time_saved_sec REAL NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_input_tokens INTEGER NOT NULL DEFAULT 0,
    routing_overhead_usd REAL NOT NULL DEFAULT 0.0
);
COMMIT;
```

**This write was blocked by the Claude Code harness's auto-mode permission classifier** when I
attempted to execute it against `~/.chuzom/usage.db`, with an explicit instruction not to work
around the block and to let the user decide. I did not attempt any workaround — no alternate
tool, no retry, no indirection. **The live installation remains in the broken state described
above as of this writing.** The SQL above is verified-correct against the app's own schema
expectations but has **not been executed**. Someone with appropriate authorization needs to:
1. Review `evidence/red2/PRE_REPAIR_usage.db.20260811_134824.db` (the last-known-good backup,
   itself already missing the historical `claude_usage` data — the data loss predates this
   backup) if they want an audit trail.
2. Run the repair SQL above against `~/.chuzom/usage.db` directly (outside this audit's
   permission scope) to restore write-ability. This does **not** restore the lost historical
   rows — those are gone — it only stops future writes from failing.
3. Decide whether/how to communicate the historical `claude_usage` data loss to anyone who
   relied on that table's history (e.g., long-window retrospective reports spanning the loss
   period will now show a gap for Claude-model-specific usage; other tables are unaffected).

**This incident is auditor error, not a Chuzom product defect**, with one exception carved out
below (RED2-07), which is a legitimate, distinct product finding about the same root confusion
that caused my mistake.

---

## RED2-07 — `CHUZOM_HOME` does not isolate `chuzom.cost._get_db()`'s storage path (testability/safety gap)

- **Severity:** P2
- **Confidence:** PROVEN (at direct, painful cost — see incident above)
- **Area:** Storage-path resolution / testability
- **Title:** An environment variable that looks like a storage-root override does not actually
  redirect the primary usage database, creating a trap for anyone (developer, CI, or an
  auditor) who reasonably assumes it does.

**Observed:** `chuzom.cost._get_db()`'s path resolution does not honor `CHUZOM_HOME` for the
`usage.db` file location; the database path resolves to the user's real home-relative
`~/.chuzom/usage.db` regardless of that variable. I confirmed this the hard way: a script that
set `CHUZOM_HOME` to an isolated temp directory before calling into `chuzom.cost` still mutated
the real production file.

**Why it matters:** this is exactly the kind of ambiguity the mandate's telemetry-integrity
directives ask me to hunt for, just aimed at a developer/operator instead of an end user — a
plausible-looking isolation mechanism that silently doesn't isolate. Any test, script, hook, or
future contributor who assumes `CHUZOM_HOME` sandboxes storage (a reasonable assumption given the
variable's name and the existence of `CHUZOM_WEEKLY_QUOTA_USD_OPUS_EQUIV`-style env overrides
elsewhere in the same codebase) is one command away from mutating a real user's production
telemetry, exactly as happened here.

**Recommended fix:** either make `CHUZOM_HOME` actually govern `_get_db()`'s path (consistently
with however it's used elsewhere in the codebase — NOT independently verified which, if any,
other subsystems DO honor it, given time constraints), or, if it's intentionally scoped to
something narrower, rename it or add a loud runtime warning/assertion when core telemetry
storage falls outside an explicitly-configured test path. At minimum, `cost.py`'s DB-path
resolution function should accept an explicit path override parameter that test/audit code can
use without relying on environment-variable conventions that don't hold.

**Release blocking:** N (P2 — does not affect end-user-facing behavior directly, but is a real
gap worth fixing before the next contributor or CI script hits it)

---

## Telemetry fail-open survey (mandate item 8) — source-level findings

Given the incident above, all further fail-open testing in this pass was done by **direct source
reading only** — no further live-DB execution was attempted against any real chuzom storage.

- **`get_savings_summary()`** (`cost.py:2116-2196`) — see RED2-02. Fail-open: query failure and
  genuine zero both silently return the same all-zero dict, no error surfaced.
- **`get_realized_savings()`**'s per-table `_query_table()` helper (`cost.py:1893-1985`) —
  explicit comment: *"Table may not exist on older DBs — treat as zero."* Same class of
  fail-open-to-zero-without-signal.
- **`retrospective._derive_savings()`** — `except Exception: return 0.0`, no logging observed at
  the call site itself (logging deeper in `get_period_accounting()` not fully traced).
- **`hooks/stop-enforce.py::_record_override()`** — explicitly, deliberately fail-open by design,
  with an in-code comment: *"Fully fail-open — a hook must never raise."* This is a defensible
  design choice for a hook that must not crash a user's session, but it means a broken override
  recording path fails silently exactly like the accounting bugs it exists to prevent (see
  RED2-04's three historical-bug citations, all inside this same fail-open blast radius).

**Pattern across all four:** none of the fail-open paths I found distinguish "confirmed zero" from
"telemetry broke" via a return-value signal. All degrade to a silent zero. This is a systemic
choice, not a one-off bug, and the mandate specifically asks whether a broken telemetry path can
be told apart from a quiet one — **it cannot, anywhere I looked in this codebase.**

**Not tested (explicitly, per mandate item 8's fuller scope):** concurrent-writer race conditions,
partial-write/torn-page scenarios under real concurrent load, and `hooks/session-end.py`'s
2,138-line fail-open behavior end-to-end — none of these were exercised this pass. Given the
incident, I made a deliberate decision to stop live-DB experimentation rather than risk a second
incident while chasing lower-severity, harder-to-reach scenarios in the time remaining.

---

## Summary table

| ID | Severity | Confidence | Title |
|---|---|---|---|
| RED2-07 | P2 | PROVEN | `CHUZOM_HOME` doesn't isolate `cost._get_db()`; false sense of test/audit isolation |
| — | — | — | Auditor incident (not a Chuzom defect): live `claude_usage` table data-loss + currently broken for writes; repair drafted, backed up, blocked pending authorization — see above |
| — | STRONG EVIDENCE | Fail-open-to-silent-zero is systemic across `get_savings_summary`, `get_realized_savings`, `_derive_savings`, and hook override-recording — no telemetry-broken vs. genuinely-quiet signal exists anywhere surveyed |

See `07_ECONOMICS_AUDIT.md` for the full economics-track findings (RED2-01 through RED2-06).
