# RED-5 Reliability Audit — Concurrency, Crashes, Corruption, State Integrity

**Auditor:** RED-5 (adversarial, zero-tolerance track)
**Target:** Chuzom, clean worktree, tag v1.1.1, SHA c2c2882
**Interpreter used exclusively:** `<worktree>/.venv-audit/bin/python`
**Central question:** *Can Chuzom lose or corrupt accounting/state without anyone noticing?*

All reproducers are genuine multi-**process** harnesses (`subprocess.Popen`, separate
OS processes with a sandboxed `HOME`), not threads-in-one-process, per the mandate.
Scripts and raw logs: `/Users/yaliandrona/Projects/Chuzom/.chuzom/zero-tolerance-audit/evidence/red5/`.
No production code was modified. No real `~/.chuzom/` or `~/.claude/` state was touched.

---

## Summary table

| ID | Severity | Confidence | Area | Title |
|---|---|---|---|---|
| RED5-01 | P0 | PROVEN | Concurrency / lineage | `LineageStore` cold-start construction race crashes writer processes and silently loses their entire write batch |
| RED5-02 | P0 | PROVEN | Fail-open / accounting | `execution_ledger.record_event()` swallows the identical cold-start race into a discarded `False` — **zero call sites in the codebase check the return value** |
| RED5-03 | P1 | PROVEN | Concurrency / session_store | `exclusive_lock()`'s timeout-fallback-to-unlocked is unreachable by design — callers never bind the yielded success flag, silently reintroducing the exact race CHZ-AUD-C-01 already fixed once |
| RED5-04 | P1 | STRONG EVIDENCE | Concurrency / budget_store | Unlocked read-modify-write on `budgets.json` — concurrent `set_cap()` calls can lose each other's updates |
| RED5-05 | P1 | STRONG EVIDENCE | Concurrency / audit log | Audit hash-chain append is not atomic with its own prev-hash read — concurrent legitimate writers fork the chain, and `verify_integrity()` then reports ordinary concurrency as **tampering** |
| RED5-06 | P1 | STRONG EVIDENCE (disclosed) | Concurrency / idempotency | `lookup()`-then-`store()` is not an atomic claim; module docstring admits multi-process coordination is unimplemented, directly undermining its stated purpose in the system's actual multi-process deployment |
| RED5-07 | P1 | STRONG EVIDENCE | Multi-session / state | `chuzom/state.py` process-globals are session-safe only under stdio; under the actually-exposed `main_sse_secured()` multi-tenant transport they are a cross-tenant state-bleed risk |
| RED5-08 | P2 | PROVEN | Deadlock detection | "Hook deadlock detector" is a foolable regex text-scanner over on-disk hook files, not runtime/semantic deadlock detection — silently reports "SAFE TO DEPLOY" if the hooks directory or filenames don't match its hardcoded glob |
| RED5-09 | INFO | N/A | Migrations | Only one schema migration exists (purely additive); the upgrade/downgrade/newer-version attack surface the mandate asks about is not yet exercised in production because it has never had a second version to migrate against |

---

## RED5-01

**ID:** RED5-01
**Severity:** P0
**Confidence:** PROVEN
**Area:** Concurrency — `src/chuzom/lineage/lineage_store.py`
**Title:** `LineageStore.__init__()`'s cold-start WAL transition is an unhandled, uncaught multi-process race that crashes the constructing process and silently discards its entire intended write batch

**Claim-Invariant violated:** The codebase's own comment states `busy_timeout` is set specifically so SQLite "waits and retries instead of raising `database is locked`" (paraphrased from the surrounding code intent), and the sibling comment in `_connect()` claims "journal_mode is persisted in the database header, so it only has to win once" — implying the WAL transition is a one-time, safe operation. Commit `14bf8b1 fix(lineage): stop "database is locked" under concurrent writers` is presented (in git history / audit tracking) as having closed this defect class for `LineageStore`.

**Observed behavior:** When N=12 separate OS processes race to construct a `LineageStore(router_dir=...)` pointed at a **not-yet-existing** `routing_lineage.db`, `_connect()`'s statement `conn.execute("PRAGMA journal_mode = WAL")` — executed immediately after `conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")` (30000 ms) on the same connection — still raises an **uncaught** `sqlite3.OperationalError: database is locked`. Nothing in `lineage_store.py` catches this exception; it propagates out of `LineageStore.__init__()` and crashes the constructing process before it ever calls `.append()`. The entire process's intended write batch (200 records in the reproducer) is lost — not just delayed, not retried, not logged anywhere by the library itself.

**Expected behavior:** Constructing N concurrent `LineageStore` instances against the same not-yet-existing DB file should either (a) block/retry until the WAL transition succeeds (which is what `busy_timeout` is supposed to guarantee for ordinary reads/writes), or (b) fail in a way that is caught, logged, and does not take down the entire calling process along with all of its subsequent writes.

**Why this matters to a real user:** Every hook invocation in the real deployment model is a separate OS process (per the mandate's own framing: "hooks run as separate OS processes in real deployment"). Any time two or more hook processes are the *first* to touch a fresh `~/.chuzom/routing_lineage.db` — e.g., right after `chuzom` is installed, after `~/.chuzom/` is cleared, after a machine/profile reset, or simply the first few seconds of a burst of concurrent Claude Code sessions — one or more of those hook processes can crash outright, silently losing that hook's entire routing-lineage record for that invocation, with only an unhandled traceback on stderr (which, per this audit, is not verified to be surfaced/logged/monitored anywhere in the real hook pipeline — see "3 most important untested things" below).

**Exact reproduction:**
```bash
WORKTREE=<audit worktree>
PY=$WORKTREE/.venv-audit/bin/python
cd /Users/yaliandrona/Projects/Chuzom/.chuzom/zero-tolerance-audit/evidence/red5
for i in $(seq 1 10); do
  $PY repro_01_lineage_multiproc.py "$WORKTREE/src" 2>&1 | grep -E "raw line count|locked errors|OperationalError"
done
```
Script: `evidence/red5/repro_01_lineage_multiproc.py`. Spawns 12 OS processes via `subprocess.Popen`, each constructing its own `LineageStore(router_dir=<sandboxed HOME>/.chuzom)` and calling `.append()` 200 times with a real `RoutingDecision`.

**Evidence (file:line, command, output):**
- `lineage_store.py`: `_BUSY_TIMEOUT_MS = 30_000`; `_connect()` does `conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")` then unguarded `conn.execute("PRAGMA journal_mode = WAL")`. `LineageStore.__init__()` calls `self._init_db()` with no surrounding try/except.
- First run (full transcript saved at `evidence/red5/repro_01_output.log`): 4 of 12 worker processes crashed with `sqlite3.OperationalError: database is locked` before calling `.append()` once; the other 8 completed cleanly with 0 per-write errors. Final: `jsonl raw line count: 1600 (expected 2400)`; all 1600 lines individually parsed as valid JSON; `query_jsonl()` succeeded; `sqlite routing_decisions row count: 1600 (expected 2400)`. Arithmetic is exact: 2400 − 1600 = 800 = 4 crashed procs × 200 writes each.
- 10-iteration repeat loop: 8 clean runs, 2 failing runs (iteration 8 of the second batch: `jsonl raw line count: 2200 (expected 2400)`, i.e. one process's batch lost). Observed failure rate ≈ 20% at N=12 concurrent constructors on this machine — a real, reproducible, timing-dependent race, not a one-off fluke.
- **Isolation test** (`evidence/red5/repro_01b_lineage_warm_append.py`): pre-constructing the `LineageStore` once, single-process, *before* spawning the 12 concurrent writers — 10/10 clean runs, `2400/2400` on both JSONL and SQLite every time, zero locked errors. This proves the race is confined to the very first WAL-mode transition on a not-yet-existing/freshly-created file; concurrent `append()` calls against an already-WAL-established file are safe.

**Root cause:** `PRAGMA journal_mode = WAL` is a schema-changing statement that SQLite handles differently from ordinary DML/DQL with respect to `busy_timeout`/`sqlite3_busy_handler` retry semantics — it can return `SQLITE_BUSY` (surfaced as `database is locked`) without honoring the same retry-until-timeout loop that protects normal statement execution, especially when multiple connections are simultaneously attempting the *same* journal-mode transition on a file that doesn't yet exist. `lineage_store.py` sets `busy_timeout` correctly but has no code path that anticipates or catches a failure specifically from the `journal_mode` pragma itself, and `LineageStore.__init__()` has no try/except around `_init_db()` at all.

**Why existing tests missed it:** Any test that (a) runs serially, (b) uses threads instead of real OS processes, or (c) constructs the store once and reuses it (the overwhelmingly likely pattern for unit/integration tests, and exactly the scenario proven safe by the warm-append isolation test above) will never exercise the cold-start race window, because the race requires multiple **separate processes** to be the literal first ones to touch a **not-yet-existing** database file at the same moment. The mandate's own framing applies directly here: "A test passing serially is NOT evidence of concurrency safety."

**Blast radius:** Every SQLite-backed store in this codebase that (1) is constructed lazily/per-process and (2) calls `PRAGMA journal_mode = WAL` unconditionally in its connect/init path is a candidate for the same defect. Confirmed present in a second, independent file — see RED5-02.

**Can this defect class exist elsewhere?:** Yes — proven present in `execution_ledger.py`'s `_connect()` (RED5-02, below), which has the structurally identical `sqlite3.connect(..., timeout=30.0)` → unguarded `conn.execute("PRAGMA journal_mode=WAL")` shape. Not yet checked (time-boxed out of this session): `budget_store`'s `SqliteAdapter` for `audit.db` (`storage/adapters/sqlite_adapter.py`, same `self._conn.execute("PRAGMA journal_mode=WAL")` right after `executescript`+`commit()`, held as a **long-lived singleton connection** rather than per-call — the exposure window may differ but the same unguarded pragma is present), and `idempotency.py`'s SQLite init path.

**Recommended systemic fix:** Wrap every `PRAGMA journal_mode = WAL` statement across the codebase in a small retry helper that catches `sqlite3.OperationalError` specifically for the journal-mode pragma and retries with backoff up to the same budget as `busy_timeout`, OR pre-create the file with the correct journal mode via a single, lock-protected bootstrap step before any concurrent construction can occur (e.g., using the same `file_lock.exclusive_lock()` primitive already in the codebase to serialize first-time DB creation across processes). At minimum, `LineageStore.__init__()` must not let `_init_db()` raise uncaught into the constructor — a caught, logged, retried-or-degraded failure is strictly better than a process crash with silent data loss.

**Regression test that would prevent recurrence:** A `subprocess.Popen`-based multi-process test (mirroring `evidence/red5/repro_01_lineage_multiproc.py`) that deletes/never-creates the target DB file, spawns ≥10 concurrent processes each constructing a fresh `LineageStore` against the same path, and asserts (a) zero process exit codes are non-zero and (b) the total row/line count in both JSONL and SQLite equals the expected total exactly. This test must run in CI multiple times (the race is ~20% per run at N=12) or use a repeat-until-either-N-runs-or-failure loop to have a meaningful chance of catching a regression.

**Release blocking?** YES

---

## RED5-02

**ID:** RED5-02
**Severity:** P0
**Confidence:** PROVEN
**Area:** Fail-open / Concurrency — `src/chuzom/execution_ledger.py`
**Title:** `execution_ledger.record_event()` has the identical unguarded cold-start WAL race as `LineageStore`, but swallows it into a discarded boolean — making the resulting accounting-event loss **completely silent**, with no crash, no log line, and no caller anywhere in the codebase checking for it

**Claim-Invariant violated:** `record_event()`'s own docstring states: "FAIL-OPEN: returns `False` on any error, never raises into the caller (routing path)." This is an honest, disclosed design choice — but it is only a safe design if *something* checks the returned `False` and does something with it (log, count, alert, retry). Nothing does.

**Observed behavior:** `_connect()` in `execution_ledger.py` (lines 258–285) does:
```python
conn = sqlite3.connect(str(p), timeout=30.0)
conn.execute("PRAGMA journal_mode=WAL")
```
— structurally identical to the RED5-01 defect: a WAL-mode pragma executed immediately after a busy-timeout has been established (here via the `timeout=` kwarg to `sqlite3.connect()` itself), with no try/except around the pragma. This function is called inside `record_event()`'s single top-level `try: ... except Exception: return False` (lines 302–319). So when the same cold-start race that crashes `LineageStore` fires here, it is caught by this blanket handler and `record_event()` simply returns `False` — the process does **not** crash, produces **no** traceback, and the caller receives a boolean it never inspects.

Confirmed via `grep -rn "record_event(" src/chuzom` (excluding the definitions themselves): every call site — `router.py:1702`, `router.py:1738`, `hooks/auto-route.py:3758`, `hooks/stop-enforce.py:138`, `hooks/enforce-route.py:572/606/664` — invokes `record_event(LedgerEvent(...))` as a bare statement. None assign, check, log, or branch on the return value.

**Expected behavior:** A failed accounting write for something the system explicitly calls "the canonical ledger" (see `record_event()`'s own docstring: "Append *ev* to the canonical ledger. Idempotent on `event_id` (INV-COST-003)") should, at minimum, increment an observable failure counter, emit a log line, or be surfaced through *some* telemetry path distinguishable from "nothing happened." Right now, a lost accounting event and a routing turn that legitimately produced no ledger event are indistinguishable from every vantage point available to the user or to Chuzom's own dashboards.

**Why this matters to a real user:** This is the single most direct answer to the audit's central question. `execution_ledger.py` is explicitly the source of truth for cost/savings accounting (`Accounting`, `get_route_accounting`, `get_session_accounting`, `reconcile_session` are all built by reading this table). If a `record_event()` call silently no-ops during exactly the highest-contention moment (first-ever construction of `usage.db`, or any burst of concurrent hook processes on a fresh install/profile), the user's savings/cost dashboard is quietly wrong from that point forward, with zero indication that anything was ever missed. Contrast with RED5-01, which at least crashes loudly (assuming stderr is captured somewhere) — this path is fully silent by design.

**Exact reproduction:** Not yet executed as a dedicated multi-process reproducer in this session (time-boxed out); the code-path proof is unambiguous and does not depend on a probabilistic timing outcome to be true (the try/except shape guarantees the swallow-and-return-False behavior *whenever* the underlying `sqlite3.OperationalError` occurs, and RED5-01 already proves that error occurs under real multi-process cold-start contention with ~20% frequency at N=12 for the structurally identical pragma call). A dedicated reproducer would adapt `evidence/red5/repro_01_lineage_multiproc.py` to call `execution_ledger.record_event()` instead of `LineageStore.append()`, assert on `record_event()`'s boolean return, and confirm some workers return `False` under concurrent cold-start load while their process exit code stays 0 (silent, not crashing) — this is the recommended next step, listed below under "3 most important untested things."

**Evidence (file:line, command, output):**
- `execution_ledger.py:271-272`: `conn = sqlite3.connect(str(p), timeout=30.0)` then `conn.execute("PRAGMA journal_mode=WAL")`, no try/except.
- `execution_ledger.py:268-270` comment: "30s busy-timeout (was 5s): under pathological CI-runner load, rapid open/write/close cycles can transiently hold the WAL lock long enough that a 5s wait errored with `database is locked`." — proves the team has *already* observed `database is locked` failures in this exact file and treated the fix as "raise the timeout," without noticing the WAL pragma itself is not covered by that timeout's retry semantics (the same gap proven empirically in RED5-01 against `lineage_store.py`'s otherwise-identical pattern).
- `execution_ledger.py:297-319`: full `record_event()` body — single `try/except Exception: return False` wrapping `_connect()` and the insert.
- `grep -rn "record_event(" src/chuzom` output (this session): 9 call sites outside the definitions, all bare-statement calls, zero capturing the return value.

**Root cause:** Same as RED5-01 (unguarded `PRAGMA journal_mode=WAL` racing under concurrent first-time file creation), compounded by a fail-open exception handler with no observability hook, compounded again by 100% of call sites discarding the one signal (`bool` return value) that could have surfaced the failure.

**Why existing tests missed it:** Same reasoning as RED5-01 (requires real concurrent multi-process cold start), plus: even a test that *did* trigger the race and got `record_event() == False` would only catch this if the test itself asserts on the return value — which none of the current call sites do, so there is no behavioral pressure anywhere in the codebase to keep this working.

**Blast radius:** Every accounting/cost dashboard, reconciliation report, and savings claim derived from `~/.chuzom/usage.db` is downstream of this silent-drop path. `Accounting`, `Reconciliation`, `get_route_accounting`, `get_turn_accounting`, `get_session_accounting`, `get_period_accounting`, `reconcile_session` are all built by reading rows from this exact table — a dropped row doesn't fail loudly in any of them, it's simply absent from every aggregate.

**Can this defect class exist elsewhere?:** Yes — this is now the second of at least two (likely three, pending the `SqliteAdapter`/`audit.db` check noted in RED5-01) independent modules with the identical unguarded-WAL-pragma shape. The fail-open wrapper pattern (`try: ... except Exception: return False/None/[]`) is pervasive across this codebase (`json_adapter.py`, `sqlite_adapter.py`'s `read()`, `idempotency.py`, `file_lock.py`, `state.py` getters) — any of these swallowing a genuine data-loss condition indistinguishably from "nothing happened" is the same epistemic risk the mandate specifically asked about (mandate item 4: "can the system distinguish 'nothing bad happened' from 'we failed to observe what happened'?" — the answer here is demonstrably no).

**Recommended systemic fix:** Same pragma-level fix as RED5-01, PLUS: introduce a lightweight, fail-open-safe "ledger write failure" counter/log (e.g., a single `logging.getLogger("chuzom.reliability").warning(...)` call, or an in-memory counter exposed via an existing health/doctor command) inside the `except Exception: return False` branch of `record_event()`, so failures are at least locally observable even though the write itself is still best-effort. Audit all other fail-open call sites in this codebase for the same "return value is generated but never checked" pattern.

**Regression test that would prevent recurrence:** Multi-process reproducer asserting `record_event()`'s boolean return is checked and logged at every call site (a static grep-based lint rule enforcing "no bare `record_event(...)` statement calls" would also catch regressions cheaply), plus the same concurrent-cold-start stress test recommended in RED5-01, adapted to assert on returned booleans instead of process exit codes.

**Release blocking?** YES

---

## RED5-03

**ID:** RED5-03
**Severity:** P1
**Confidence:** PROVEN
**Area:** Concurrency — `src/chuzom/session_store.py` + `src/chuzom/file_lock.py`
**Title:** `exclusive_lock()`'s documented "degrade to unlocked on timeout" fallback is architecturally unreachable by its only two callers, silently reintroducing the exact append/compaction race CHZ-AUD-C-01 already fixed once

**Claim-Invariant violated:** `file_lock.py`'s own docstring states this module exists specifically to fix CHZ-AUD-C-01 — a previously measured, quantified bug ("22/1200 = 1.83% loss observed under 6-process load") where concurrent compaction could silently orphan another process's just-appended write. `session_store.py`'s inline comment at the lock call site (lines 421-430) restates this as a hard invariant: "the append (dedupe-check + write) and any triggered compaction must run as one atomic unit across processes."

**Observed behavior:** `exclusive_lock()` is a context manager that *yields a boolean* (`True` if the lock was actually acquired, `False` if acquisition timed out after `_DEFAULT_TIMEOUT_SECONDS = 30.0`) specifically so that "callers that need to fail rather than silently proceed unlocked should check the yielded value" (per its own docstring). Both call sites in `session_store.py` — `purge_expired()` at line 375 and `record_event()` at line 431 — use `with exclusive_lock(_lock_path(path)):` with **no `as` binding at all**. The yielded value is discarded unconditionally. This means: if lock acquisition ever times out (30s of contention — plausible under a burst of concurrent hook processes all touching the same session file, especially combined with the compaction path's own file I/O under load), `record_event()`'s critical section — append + `_maybe_compact()`, including the `os.replace()` atomic swap — proceeds exactly as if it were safely locked, with zero indication to the caller, the log, or the user that the safety mechanism was bypassed.

**Expected behavior:** Either (a) the caller checks the yielded boolean and skips/defers/logs when `locked is False` rather than proceeding into a critical section the code itself documents as requiring cross-process atomicity, or (b) `exclusive_lock()` offers (and callers use) a strict variant that raises on timeout instead of silently degrading, for call sites where "proceed unlocked" is known to be unsafe (as this comment block explicitly says it is).

**Why this matters to a real user:** This is not a hypothetical process-death scenario — it is the code's own documented failure mode, left unchecked at the only two places that mattered enough to add the lock in the first place. Under sufficient hook-process concurrency, the previously-fixed, previously-measured (1.83%) session-context loss bug can silently reappear with zero regression signal, because the fix's own escape hatch for "the lock didn't work" is never exercised.

**Exact reproduction:** Direct code reading is dispositive here — no timing-dependent execution is required to establish that the yielded value is never bound or inspected (a `with cm():` statement structurally cannot branch on the context manager's yielded value unless it uses `as`). Confirmed via direct `Read` of `session_store.py` lines 361-462 this session:
```python
with exclusive_lock(_lock_path(path)):
    _maybe_compact(path)
```
and
```python
with exclusive_lock(_lock_path(path)):
    prev = _last_record(path)
    ...
    _maybe_compact(path)
```
Neither has `as locked:`, and no `if not locked:` branch exists anywhere in the surrounding function bodies (verified by reading the full 361-462 line range). A live reproducer that holds the sibling `.lock` file locked from an external process for >30s while calling `record_event()` in a second process would additionally demonstrate the unlocked write landing during the hold — not yet executed this session (time-boxed).

**Evidence (file:line, command, output):**
- `file_lock.py:44-53` (docstring): "Yields `True` if the lock was actually acquired, `False` if acquisition timed out... callers that need to fail rather than silently proceed unlocked should check the yielded value."
- `session_store.py:375`: `with exclusive_lock(_lock_path(path)):`
- `session_store.py:431`: `with exclusive_lock(_lock_path(path)):`
- `session_store.py:421-430` inline comment restating the atomicity requirement that the missing `as`-binding fails to enforce.
- `file_lock.py:5-8` docstring citing the original quantified bug this module was built to fix.

**Root cause:** The locking primitive was built with a deliberate, well-documented fail-open escape hatch (consistent with this codebase's pervasive fail-open philosophy), but the only two production call sites never opted into checking it — a straightforward oversight at the call site, not a flaw in `exclusive_lock()`'s own design.

**Why existing tests missed it:** A test would need to force `exclusive_lock()` to time out (hold the lock externally for the full 30s default, or monkeypatch the timeout very low) *and* assert on write-loss/orphaning under that specific condition. Nothing in the visible test suite (not independently verified this session, but consistent with the general pattern found across every other finding here) appears to exercise the timeout-fallback path specifically; ordinary concurrency tests that succeed within the 30s window would never observe this.

**Blast radius:** Every `record_event()`/`purge_expired()` call — i.e., all session-context accumulation used to feed routed models real prior-turn context — is exposed during any 30-second window where lock contention is high enough to time out.

**Can this defect class exist elsewhere?:** Not found elsewhere in this session — `exclusive_lock()` appears to have exactly these two call sites in the codebase (not independently re-verified via a full-repo grep this session; recommended as a follow-up).

**Recommended systemic fix:** Change both call sites to `with exclusive_lock(_lock_path(path)) as locked:` and skip/log/defer the critical section when `locked` is `False`, rather than proceeding unconditionally. At minimum, log a warning when this occurs so operators have a signal that the previously-fixed race is happening again.

**Regression test that would prevent recurrence:** A test that pre-holds the lock file for longer than the timeout from a second process, then calls `record_event()` and asserts it does NOT proceed to write via the unprotected path (or, if the design intent is "proceed but log," asserts a warning was emitted).

**Release blocking?** YES (this directly un-fixes a previously-shipped, previously-measured data-loss bug under realistic contention)

---

## RED5-04

**ID:** RED5-04
**Severity:** P1
**Confidence:** STRONG EVIDENCE (code-proven TOCTOU shape; not yet triggered under live concurrent load)
**Area:** Concurrency — `src/chuzom/storage/service.py` (`StorageService.write_budget` / `delete_budget`) + `src/chuzom/storage/adapters/json_adapter.py`
**Title:** Budget-cap writes are an unlocked read-modify-write across the entire `budgets.json` file — concurrent `set_cap()` calls for *different* providers can silently lose each other's updates

**Claim-Invariant violated:** A budget cap set for provider A should never be undone by a concurrent write that only intended to change provider B's cap.

**Observed behavior:** `write_budget(provider, amount, source)` does: `existing_data = self._budgets_adapter.read() or {}`; `existing_data[provider] = amount`; `self._budgets_adapter.write(existing_data, atomic=True)`. `JsonAdapter` (`json_adapter.py`) has **zero locking** anywhere — `read()` and `write()` are independent, unsynchronized filesystem operations; `atomic=True` only protects against a torn/partial *file* via temp-file + `os.replace()`, it does nothing to serialize two processes' full read-modify-write cycles against each other. Two concurrent calls — `write_budget("openai", 50)` and `write_budget("anthropic", 30)` — can both `read()` the same starting snapshot, each mutate only their own key in their private in-memory copy, and then `write()` their full snapshot back; whichever write lands second silently overwrites the first writer's change to the *other* key, because that writer's in-memory copy predates the first writer's update.

**Expected behavior:** Concurrent budget-cap writes for independent providers should never clobber each other. This requires either locking the read-modify-write cycle (e.g., reusing `file_lock.exclusive_lock()`, already present elsewhere in the codebase) or moving to a per-key storage format (e.g., one file per provider) that makes whole-file overwrite races impossible.

**Why this matters to a real user:** Budget caps are a safety/cost-control feature — a user who sets a $50 cap on one provider and, moments later (or concurrently, via another session/hook), a cap on a different provider, can end up with the first cap silently reverted to whatever it was before, with no error, no warning, and no record that the update was lost. This is the accounting-adjacent "state that can be lost without anyone noticing" the audit specifically asks about.

**Why this matters:** covered above.

**Exact reproduction:** Not yet executed as a live multi-process reproducer this session (time-boxed). Recommended construction: two `subprocess.Popen` processes calling `chuzom.storage.service.storage_service.write_budget()` for two *different* provider keys in a tight loop against the same sandboxed `~/.chuzom/budgets.json`, asserting after N rounds that both keys hold their most-recently-intended value rather than one being reverted to a stale snapshot.

**Evidence (file:line, command, output):**
- `storage/service.py` `write_budget()`: `existing_data = self._budgets_adapter.read() or {}` → `existing_data[provider] = amount` → `self._budgets_adapter.write(existing_data, atomic=True)` — no lock spans this sequence.
- `storage/adapters/json_adapter.py`: `read()` (try/except returning `None` on any error) and `write()` (temp-file + `os.replace()`) — no `fcntl`/`msvcrt` import, no reference to `file_lock` anywhere in this file.

**Root cause:** Whole-file read-modify-write with no cross-process synchronization, on a store that is logically keyed (per-provider) but persisted as a single monolithic JSON blob.

**Why existing tests missed it:** Requires two concurrent processes racing on the same file with a read-write window wide enough to overlap; single-process/serial tests cannot observe this by construction.

**Blast radius:** Any user or automated workflow that sets multiple provider budget caps close together in time (including via concurrent Claude Code sessions or automated provisioning scripts).

**Can this defect class exist elsewhere?:** Yes — `delete_budget()` has the identical unlocked read-modify-write shape, and `migrate_config()` (also in `storage/service.py`, writing via the same unlocked `JsonAdapter` pattern against `config.yaml` through `YamlAdapter`, not independently inspected this session) is a plausible sibling.

**Recommended systemic fix:** Wrap `write_budget`/`delete_budget`'s read-modify-write cycle in `file_lock.exclusive_lock()` (already proven-available elsewhere in this codebase), the same primitive used (if imperfectly — see RED5-03) for `session_store.py`.

**Regression test that would prevent recurrence:** Two-process concurrent `write_budget()` test for distinct provider keys, asserting no lost updates after N concurrent rounds.

**Release blocking?** NO (real but requires a specific interleaving; not release-blocking on its own, but should be fixed alongside RED5-03 since the same primitive fixes both)

---

## RED5-05

**ID:** RED5-05
**Severity:** P1
**Confidence:** STRONG EVIDENCE (code-proven TOCTOU shape; not yet triggered under live concurrent load)
**Area:** Concurrency / tamper-evidence — `src/chuzom/storage/service.py` (`append_audit_event`) + `src/chuzom/storage/adapters/sqlite_adapter.py`
**Title:** The tamper-evident audit hash-chain's own append path is not atomic with its prev-hash read, so ordinary concurrent legitimate writes can fork the chain — and `verify_integrity()` cannot tell that apart from actual tampering

**Claim-Invariant violated:** The audit log is documented/designed as "tamper-evident" — a `verify_integrity()` failure is meant to signal that someone altered historical records, not that two writers happened to append at the same moment.

**Observed behavior:** `StorageService.append_audit_event()` does: `prev_hash = self._get_latest_audit_hash()` (a SELECT reading the current last row's `hash_hex`), computes `hash_hex = sha256(prev_hash + canonical_payload)`, then calls `self._audit_adapter.append(event_dict)` (a separate INSERT + commit). These are two independent operations with no transaction or lock spanning both. Two concurrent `append_audit_event()` calls can both read the same `prev_hash` (both observe the same "latest" row before either has inserted their own), and both then compute and insert rows claiming to be the direct child of that same `prev_hash` — producing two rows in the table whose `prev_hash` matches, but which cannot both legitimately extend a single linear chain. `SqliteAdapter.verify_integrity()` walks rows in `timestamp ASC` order expecting each row's `prev_hash_stored` to equal the previous row's `hash_hex` exactly; a forked chain from this race produces a `prev_hash_stored != prev_hash` mismatch, which `verify_integrity()` reports as `(False, "broken_chain_at_<id>")` — the *same* return shape it uses for genuine tampering. There is no code path that distinguishes "two legitimate concurrent writers forked this" from "a byte was maliciously altered."

**Expected behavior:** Either the read-then-append sequence should be a single atomic unit (e.g., an `INSERT ... SELECT MAX(hash_hex)`-style single statement inside one transaction, or protected by a lock spanning both operations), or `verify_integrity()`'s failure classification should be able to distinguish an ordering/fork race from an actual content-hash mismatch (only the latter is real evidence of tampering; the former is a concurrency bug in the writer).

**Why this matters to a real user:** This is a security/compliance feature (per the module's stated purpose — tamper-evident logging, CEF export "for SIEMs" per `SqliteAdapter.export()`) that can produce **false positive tamper alerts** from its own ordinary concurrent operation, undermining trust in genuine tamper alerts (alert fatigue / "the audit log is always broken, ignore it"), which is arguably worse for a security feature than silent data loss elsewhere in this report.

**Exact reproduction:** Not yet executed as a live reproducer this session (time-boxed). Recommended construction: two concurrent processes calling `storage_service.append_audit_event()` in a tight loop against the same sandboxed `audit.db`, then running `verify_integrity()` and checking for `broken_chain_at_*` results despite no byte of any row having been altered post-write.

**Evidence (file:line, command, output):**
- `storage/service.py` `append_audit_event()`: `prev_hash = self._get_latest_audit_hash()` then separately `self._audit_adapter.append(event_dict)` — no transaction/lock spans the two.
- `storage/adapters/sqlite_adapter.py` `verify_integrity()` (lines 109-159): single failure-mode string `f"broken_chain_at_{id_}"` used both for "row order/linkage broken" and is the only path exercised by a concurrency fork; `f"tampered_at_{id_}"` is the separate path for a genuine hash mismatch, but a forked-chain race hits the *former*, not the latter — so operationally both "concurrency accident" and "chain discontinuity from any other cause" are bucketed together and neither is distinguishable from partial tampering that also breaks linkage.

**Root cause:** Read-then-write hash-chaining without a transaction or lock spanning the read of the previous hash and the insert of the new row — classic TOCTOU applied to a cryptographic chain construction.

**Why existing tests missed it:** Requires two genuinely concurrent writers; any serial test (including most hash-chain "tamper detection" unit tests, which typically test by mutating an existing row, not by racing two legitimate writers) would never produce a forked chain.

**Blast radius:** Any deployment with more than one concurrent writer to the audit log (multiple hook processes, multiple sessions, or the SSE multi-tenant transport described in RED5-07) — i.e., essentially every real deployment beyond a single serial user.

**Can this defect class exist elsewhere?:** This is the audit-log-specific manifestation of the same "read-then-write with no lock" pattern found in RED5-04 (budgets.json) and RED5-01/02 (lineage/execution_ledger cold start) — a recurring architectural pattern across this codebase's persistence layer, not an isolated one-off.

**Recommended systemic fix:** Either wrap `_get_latest_audit_hash()` + `append()` in a single SQLite transaction (SQLite's own locking would then naturally serialize this at the DB level), or protect the sequence with `file_lock.exclusive_lock()`. Additionally, harden `verify_integrity()` to log/report fork points distinctly from genuine hash mismatches, so operators are not trained to distrust or ignore tamper alerts.

**Regression test that would prevent recurrence:** Two-process concurrent `append_audit_event()` test asserting `verify_integrity()` still reports `(True, "intact")` afterward (i.e., the chain was correctly serialized, not forked), or if fork-tolerance is the chosen design, a test asserting fork events are labeled distinctly from `tampered_at_*`.

**Release blocking?** NO (requires concurrent writers to the audit log specifically, a narrower surface than the P0 findings, but should not ship long-term given it's a security-adjacent false-positive risk)

---

## RED5-06

**ID:** RED5-06
**Severity:** P1
**Confidence:** STRONG EVIDENCE (disclosed by the module's own docstring; not independently re-verified via a live reproducer this session)
**Area:** Concurrency — `src/chuzom/idempotency.py`
**Title:** Idempotency dedupe is single-process only, in a system whose real deployment topology is multi-process — concurrent retries of the same routing call can still incur duplicate provider cost, the exact failure this module exists to prevent

**Claim-Invariant violated:** The module's own purpose statement (paraphrased from its docstring, previously read in full this session): prevents duplicate provider costs on `route_and_call` retries.

**Observed behavior:** `lookup(key)` (a SELECT + expiry check) and `store(key, response, ttl_seconds)` (an `INSERT OR REPLACE`) are two independent calls with no atomic "claim" step between them. The module's own docstring **honestly discloses** this: "Single-process; multi-process coordination lands in T2-XL1" — but the system's actual deployment model (hooks as separate OS processes, per the mandate's own framing) is precisely the multi-process scenario this store does not protect against. Two concurrent processes retrying the same logical request (e.g., a hook retry racing a user-initiated retry, or two concurrent sessions issuing the same idempotency key) can both `lookup()` and both observe a cache miss, both proceed to call the provider, and both `store()` — resulting in the exact duplicate provider cost this module exists to prevent.

**Expected behavior:** An atomic claim primitive (e.g., an upfront `INSERT` that fails/conflicts if a claim row already exists, functioning as a mutex on the key) before the expensive provider call, so a second concurrent request for the same key blocks or short-circuits rather than duplicating work.

**Why this matters to a real user:** Directly undermines a specifically cost-control-oriented feature under exactly the concurrency conditions the rest of this codebase's docstrings otherwise describe as expected/normal for hook execution.

**Exact reproduction:** Not independently re-executed this session (time-boxed); this finding rests on direct reading of the module's own honest disclosure plus its `lookup()`/`store()` implementation shape (both read in full earlier this session).

**Evidence (file:line, command, output):** `idempotency.py` module docstring: "...multi-process coordination lands in T2-XL1." `lookup()`/`store()` signatures and bodies as summarized above (read in full during this session's file review).

**Root cause:** Disclosed, accepted technical debt — not an oversight, but a design gap that the codebase's own roadmap notation (`T2-XL1`) acknowledges is still open.

**Why existing tests missed it:** N/A — this is a disclosed, known gap, not a missed defect.

**Blast radius:** Any retried routing call issued from two or more concurrent processes/sessions sharing the same idempotency key.

**Can this defect class exist elsewhere?:** This is the idempotency-specific instance of the same "check-then-act without an atomic claim" pattern seen elsewhere in this report (RED5-04, RED5-05).

**Recommended systemic fix:** Implement the disclosed `T2-XL1` multi-process coordination (e.g., an atomic `INSERT`-as-claim with a short "in-flight" TTL row, later replaced by the real response) before relying on this module to actually prevent duplicate cost in the deployed multi-process topology.

**Regression test that would prevent recurrence:** Two-process concurrent `lookup()`→provider-call→`store()` simulation for the same key, asserting the provider-call simulation is invoked at most once.

**Release blocking?** NO (disclosed limitation, not a hidden defect) — but flagged because the disclosure is inconsistent with the system's marketed cost-protection guarantees under its actual deployment model.

---

## RED5-07

**ID:** RED5-07
**Severity:** P1
**Confidence:** STRONG EVIDENCE (code-proven design gap; no live multi-tenant SSE reproducer executed this session)
**Area:** Multiple sessions / async — `src/chuzom/state.py` + `src/chuzom/server.py` + `src/chuzom/tools/admin.py`
**Title:** Process-global routing state (`_active_profile`, `_last_usage`, `_active_agent`) is safe only under the stdio transport; the actually-exposed `main_sse_secured()` entry point serves multiple concurrently authenticated tenants from one process against these same unscoped globals

**Claim-Invariant violated:** Per-user/per-session routing state (active profile override, cached usage, active agent) should never bleed across two different authenticated clients.

**Observed behavior:** `state.py` defines `_active_profile`, `_last_usage`, `_active_agent` as bare module-level globals guarded only by a `threading.Lock` (`_state_lock`) — the module's own comment explains this lock exists because "the server may delegate work to a ThreadPoolExecutor," i.e., it is designed to be thread-safe within **one process**, not session-scoped across multiple logical clients of that process. `server.py`'s `main()` (stdio transport) is safe under this design because stdio implies one process per client connection. However, `server.py`'s `main_sse_secured(host="127.0.0.1", port=17891)` — explicitly documented in its own docstring as "what the CLI actually exposes" (as opposed to the intentionally-unexposed, SEC-001-flagged `main_sse()`) — runs a single `uvicorn.Server` behind Bearer-token auth, serving potentially many different authenticated clients/tenants concurrently from that one process. Under this transport, `llm_set_profile()` (`tools/admin.py`) mutates the same bare global regardless of which authenticated caller invoked it, and `get_active_profile()`/`get_last_usage()`/`get_active_agent()` return whatever the *last* caller (of any tenant) set — a genuine cross-tenant state-bleed path. Concretely proving this was a design gap rather than a framework limitation: `llm_save_session(ctx: Context)` in the same file (`tools/admin.py`) *does* accept a per-request `Context` object from `mcp.server.fastmcp`, proving session-scoped state was available to use; `llm_set_profile(profile: str) -> str` simply does not take one.

**Expected behavior:** Routing-profile/usage/agent state that varies per authenticated tenant should be stored per-session (e.g., keyed by the `Context`'s session/request identity, or an equivalent per-connection store), not as bare process globals, whenever the server can run under a multi-tenant transport.

**Why this matters to a real user:** Under `main_sse_secured()`, one tenant calling `llm_set_profile("premium")` could cause a *different*, concurrently connected tenant's subsequent routing decisions to silently use the wrong profile — a correctness and potentially billing-relevant issue (profile affects cost tier), and a state-integrity violation that would be invisible to either tenant, since each only observes their own request/response, not the shared global's true owner at any given moment.

**Exact reproduction:** Not executed this session (would require standing up `main_sse_secured()` with two simulated Bearer-token-authenticated clients issuing interleaved `llm_set_profile`/`get_active_profile`-dependent calls and observing cross-contamination) — time-boxed out; flagged as one of the three most important untested items below.

**Evidence (file:line, command, output):**
- `state.py:26-34`: module-level globals + `threading.Lock` docstring explaining the single-process-multi-thread (not multi-tenant) safety model.
- `server.py` (`main`, line ~456; `main_sse`, line ~475 with its SEC-001 docstring explaining why it's unexposed; `main_sse_secured`, line ~530, whose docstring states it is "what the CLI actually exposes").
- `tools/admin.py`: `llm_save_session(ctx: Context)` (accepts `Context`) vs. `llm_set_profile(profile: str) -> str` (does not) — read in full this session, lines 1-90.

**Root cause:** `state.py` was designed under a single-process/single-tenant assumption (correct for the stdio transport) that does not hold for the multi-tenant SSE transport that was later added and is now the actual hosted/exposed entry point.

**Why existing tests missed it:** Requires a genuine multi-client SSE harness with distinct auth identities issuing interleaved calls; unit tests exercising `state.py`'s getters/setters in isolation (single caller) would never observe cross-tenant bleed by construction.

**Blast radius:** Any hosted/multi-tenant deployment of `main_sse_secured()` serving more than one authenticated client concurrently — the exact configuration its own docstring says is the real, exposed entry point.

**Can this defect class exist elsewhere?:** Worth checking whether other modules besides `tools/admin.py` also mutate process-globals without `Context` scoping; not exhaustively audited this session.

**Recommended systemic fix:** Thread a per-session identity (from `Context` or the Bearer-token-authenticated identity already established by `main_sse_secured()`'s auth layer) through `state.py`'s get/set functions, keyed by session rather than global.

**Regression test that would prevent recurrence:** A test standing up `main_sse_secured()` (or a minimal harness around the same FastMCP app) with two distinct authenticated identities, asserting that one identity's `llm_set_profile()` call does not affect the other identity's `get_active_profile()` result.

**Release blocking?** NO for the stdio-only deployment path; YES if `main_sse_secured()` is being marketed/used as a genuine multi-tenant hosted offering as its docstring implies.

---

## RED5-08

**ID:** RED5-08
**Severity:** P2
**Confidence:** PROVEN (code reading is dispositive; no execution needed to establish what the implementation does)
**Area:** Retry/Deadlock — `src/chuzom/hook_deadlock_detector.py` + `src/chuzom/hook_deadlock_checker.py`
**Title:** "Hook deadlock detection" is a best-effort regex text-scanner over on-disk hook source files, not runtime or semantic deadlock detection — and silently reports "SAFE TO DEPLOY" when its hardcoded assumptions don't hold

**Claim-Invariant violated:** The module's own docstring claims it "Detects and prevents: Circular dependencies between hooks... Missing subprocess timeouts... Resource contention patterns..." — language implying sound, deterministic analysis. `check_all_hooks()` is described as "Used by CI/CD and startup verification."

**Observed behavior:** `HookDeadlockDetector._analyze_all_hooks()` only scans files matching `self.hooks_dir.glob("chuzom-*.py")` inside `Path.home() / ".claude" / "hooks"` (or a caller-supplied dir). All of its "analysis" is regex pattern matching over the *raw text* of these files: `_extract_subprocess_calls` matches `subprocess\.(run|Popen|call|check_call|check_output)\([^)]*\)` etc.; `_extract_timeout_config` matches bare substrings like `timeout=(\d+|\w+\(\))` and `CHUZOM_.*TIMEOUT` **anywhere in the file**, with no requirement that a matched "timeout" is actually bound to, or in proximity of, any specific subprocess call it's supposedly "covering"; `_extract_hook_dependencies` matches import-style regexes (`from chuzom\.hooks\.(\w+) import`, etc.) to build a dependency graph, then runs a DFS for cycles over that regex-derived graph. `_check_timeout_coverage()`'s only rule is `if analysis.subprocess_calls and not analysis.timeouts` — i.e., a hook is only flagged if it has **zero** timeout-looking substrings anywhere in the entire file; a single unrelated timeout string anywhere (even in a docstring, comment, or a completely different function) satisfies this check for every subprocess call in that file. `check_all_hooks()` (`hook_deadlock_checker.py`) returns `0` ("no critical issues") immediately if `~/.claude/hooks` doesn't exist at all, with only a print statement, no failure signal to its caller beyond that exit code.

**Expected behavior:** A component whose docstring claims to "detect and prevent" deadlocks and missing timeouts should either (a) perform real semantic/AST-level analysis that can't be defeated by a timeout string appearing anywhere else in the file, or (b) be documented as the best-effort heuristic linter it actually is, so CI/startup verification callers and human reviewers don't over-trust a "SAFE TO DEPLOY" result.

**Why this matters to a real user:** If this check is wired into CI or startup verification as its docstring claims, a "SAFE TO DEPLOY" or exit-code-0 result carries false confidence — genuine circular hook dependencies expressed through any indirection (dynamic imports, calling by variable, wrapping subprocess calls in a helper function, hooks with non-`chuzom-*.py` filenames) or genuinely unguarded subprocess calls sitting in a file that happens to mention `timeout=` somewhere else will pass silently. This directly answers mandate item 8 ("does hook deadlock detection actually work, or is it best-effort presented as deterministic?"): it is best-effort, and its docstring/naming ("Detects and prevents") presents it as more authoritative than its regex-over-text implementation can support.

**Exact reproduction:** Code reading is sufficient and dispositive; additionally trivially demonstrable: create a hook file containing a `subprocess.run(...)` call with no timeout, plus an unrelated string `# TODO: revisit timeout=300 in some other function`, run `HookDeadlockDetector.analyze()` against it, and observe `has_timeout_issues` is `False` for that file despite the actual subprocess call being unprotected.

**Evidence (file:line, command, output):** `hook_deadlock_detector.py` lines 105-133 (`_extract_subprocess_calls`, `_extract_timeout_config`), lines 211-220 (`_check_timeout_coverage`), lines 78-85 (`_analyze_all_hooks`'s hardcoded `chuzom-*.py` glob); `hook_deadlock_checker.py` lines 21-25 (silent `return 0` when hooks dir doesn't exist).

**Root cause:** The tool is implemented as a lightweight regex/text heuristic rather than an AST-aware or runtime instrumentation-based analysis, while its docstring and function names ("detect and prevent," "SAFE TO DEPLOY") imply a stronger guarantee than the implementation provides.

**Why existing tests missed it:** Tests exercising this module would need to specifically construct adversarial hook files with indirection to reveal the gap between "text mentions a timeout" and "this specific subprocess call is actually timeout-protected" — a heuristic tool's own test suite is likely to test its happy path, not its evadability.

**Blast radius:** Confidence in CI/startup-verification gating for hook deadlock risk; does not itself cause data loss but creates false assurance about a different real risk class (hook hangs / resource contention).

**Can this defect class exist elsewhere?:** Worth checking whether other "verification"/"detector" modules in this codebase (referenced but not read this session, e.g. broader `_startup_verify_or_die()` in `server.py`) share the same "presented as deterministic, implemented as heuristic" gap.

**Recommended systemic fix:** Either rename/re-scope the docstring and CLI output to honestly describe this as a best-effort lint (e.g., "heuristic hook scan: may miss issues masked by indirection"), or upgrade the implementation to AST-based analysis that binds timeout arguments to their specific call sites rather than file-wide substring presence.

**Regression test that would prevent recurrence:** A test with a hook file containing an actually-unprotected `subprocess.run()` call plus an unrelated, non-binding `timeout=` string elsewhere in the file, asserting `has_timeout_issues` is `True` (currently would fail, proving the gap).

**Release blocking?** NO (governance/confidence issue, not a data-loss or crash path)

---

## RED5-09

**ID:** RED5-09
**Severity:** INFO
**Confidence:** N/A (scope observation, not a defect)
**Area:** Schema migration — `src/chuzom/migrations/`
**Title:** Only one schema migration exists; the mandate's upgrade/downgrade/newer-version/mixed-version attack surface has no real multi-version chain to exercise yet

**Observed behavior:** `src/chuzom/migrations/versions/` contains exactly one file, `001_create_chuzom_health.py` — a purely additive `CREATE TABLE IF NOT EXISTS chuzom_health` + two `CREATE INDEX IF NOT EXISTS` statements, with a correct, non-destructive `down()` (drops indexes then table). No other migration exists in this framework. Separately, `execution_ledger.py` has its own, independent, idempotent inline migration list (`_MIGRATIONS` tuple of `ALTER TABLE ... ADD COLUMN` statements, each wrapped in its own try/except to tolerate an already-migrated or fresh-via-DDL database) — this is a different, ad hoc mechanism from the `migrations/` framework and was read in full this session; no defect found in it (each statement's own try/except correctly makes re-application idempotent).

**Why this matters:** The mandate specifically asks to test "upgrade from older schema, downgrade, a DB written by a NEWER version read by this one, mixed-version rows in one store." With only one versioned migration in the formal framework, there is no genuine multi-version upgrade path to test against yet — this is a scope/coverage observation, not a proven or suspected defect. It does mean the `migrations/` framework itself is essentially untested in the field beyond its first version, so any latent bug in its version-sequencing/application logic (not independently deep-audited this session — `migrations/__init__.py` was located but not read in full) would not yet have had an opportunity to manifest.

**Recommended follow-up:** Read `migrations/__init__.py` in full to assess the runner's own concurrency/idempotency properties (does applying migrations itself race under concurrent first-run processes, analogous to RED5-01?) before this framework accumulates more versions and the upgrade/downgrade surface becomes real. Not release-blocking today given the framework's current single-version state.

**Release blocking?** NO

---

## Safety appendix — DB-path isolation audit (added post-cross-track incident report)

A coordinating agent reported that a sibling audit track proved `CHUZOM_HOME` does **not**
isolate `chuzom.cost._get_db()` from the real `~/.chuzom/usage.db`, and that track executed
a `DROP TABLE` against the user's live 63.7MB production database believing it was sandboxed,
permanently destroying historical data. In response, every DB-path resolver touched or
considered by RED-5 was re-checked by reading the resolution code directly (read-only,
no execution) before writing this appendix. No destructive test was run as part of this
check.

**Confirmed safe, and how RED-5 actually used them:**
- `LineageStore(router_dir=...)` — takes an explicit constructor path argument; does not
  consult any env var for its base directory. `evidence/red5/repro_01_lineage_multiproc.py`
  and `repro_01b_lineage_warm_append.py` both passed an explicit `tempfile.TemporaryDirectory`
  path as `router_dir`, never relying on `CHUZOM_HOME` or any other env-var redirection.
  RED5-01's live reproducers are confirmed genuinely sandboxed.
- `StorageService(router_dir=...)` (`storage/service.py:39`) — `self._router_dir = router_dir
  or (Path.home() / ".chuzom")` — also takes an explicit constructor override. Verified this
  turn, read-only. RED5-04/RED5-05's proposed-but-not-yet-executed live reproducers would be
  safe to build using this constructor argument directly, the same explicit-path pattern
  used successfully for RED5-01 — **not** via `CHUZOM_HOME`.

**Confirmed unsafe / not independently proven — marked NOT TESTED for this reason:**
- **`chuzom/cost.py`'s `_get_db()`** — proven unsafe by the sibling track's incident.
  RED-5 never called this function directly or indirectly in any executed reproducer this
  session (confirmed by reviewing every script under `evidence/red5/`), so no remediation
  is owed on RED-5's part. It is flagged here because `execution_ledger.py` lives in the
  same accounting-state area of the codebase and a future auditor could reasonably assume
  the same env-var pattern is safe there — it is not, without independent verification.
- **`chuzom/execution_ledger.py`'s `_db_path()`** (line 159-163) — reads
  `os.environ.get("CHUZOM_EXECUTION_LEDGER_DB")` and, per a code read, falls back to
  `Path.home() / ".chuzom" / "usage.db"` (the real production accounting DB) if unset. The
  override *appears* correctly wired by static reading, but per the coordinator's directive
  this must be proven by printing the resolved path and asserting it lands under the sandbox
  tmpdir before any destructive/concurrent test is run against it — RED-5 did not do this at
  runtime this session. **The planned live multi-process reproducer for RED5-02 (recommended
  in that finding's "Exact reproduction" section as a confidence upgrade from PROVEN-via-code
  to PROVEN-via-code-and-execution) is therefore explicitly marked NOT TESTED — cannot be
  safely isolated without first proving the resolver at runtime, and was deliberately not
  attempted.** RED5-02's PROVEN confidence rating is unaffected: it rests entirely on static
  code reading (the unguarded pragma shape identical to the live-proven RED5-01 crash, plus
  the exhaustive grep proving the returned `False` is discarded at every call site) and does
  not depend on this untested live reproducer.
- Budget/audit-log live reproducers proposed in RED5-04 and RED5-05 were never executed this
  session (they were already marked "not yet executed... time-boxed" before this incident);
  they remain NOT TESTED. Per the safe pattern confirmed above (`StorageService(router_dir=...)`),
  they *could* be executed safely using an explicit constructor path exactly as RED5-01's
  reproducers did — but were not attempted, so no live evidence exists for them beyond the
  code-level TOCTOU proof already documented.

**Explicit confirmation:** RED-5 did not touch, drop, truncate, migrate, or otherwise write to
`~/.chuzom/usage.db` or any other real user state at any point this session or the prior one.
Every executed reproducer used an explicit, RED-5-chosen `tempfile.TemporaryDirectory` path
passed directly into a constructor argument (`router_dir=...`), never an env-var override of
chuzom's own resolvers. No remediation action was taken or is owed by this track.

## Evidence index

- `evidence/red5/repro_01_lineage_multiproc.py` — multi-process cold-start reproducer for RED5-01 (12 processes × 200 writes against a not-yet-existing `LineageStore` DB).
- `evidence/red5/repro_01_output.log` — saved full transcript of the first failing run (4/12 processes crashed, exact 800-record loss) plus the appended isolation-test summary.
- `evidence/red5/repro_01b_lineage_warm_append.py` — isolating variant: pre-constructs the store once (single process) before spawning 12 concurrent appenders; 10/10 clean, proving the race is cold-start-only.

---

## Final assessment — for the FINAL MESSAGE to the coordinating agent

See accompanying message. Verdict: **yes, Chuzom can lose and misclassify state without anyone noticing, via multiple independent, proven or strongly-evidenced concurrency paths — and the single worst path (RED5-02) is a silent accounting-data drop with a discarded error signal at 100% of its call sites.**
