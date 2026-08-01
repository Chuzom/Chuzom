# RED-1 — Architecture & Correctness Audit — Iteration 7

Auditor: RED-1 (independent, no access to RED-2's report)
Commit audited: `611c506`
Scope: budget-envelope parent-chain fix (iter-6), content-aware hook-update fix (iter-6),
broad `route_and_call`/`_dispatch_model_loop` correctness.

## Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 2 |
| Core-Medium | 0 |

- **RED1-7-01** (High) — `commit_envelope()` release-then-commit is non-atomic: a real window exists where a concurrent reservation can push total exposure past a shared budget cap.
- **RED1-7-02** (High) — `check_and_update_hooks()` / `check_and_update_rules()` silently destroy user-customized hook/rules files on every MCP server startup, whenever the user edited the file without also bumping an internal, undocumented version-stamp comment.

---

## RED1-7-01 — `commit_envelope()` release-then-commit race allows shared-cap breach

- **Severity:** High
- **File:** `src/chuzom/quota_envelope_routing.py:96-113` (caller), `src/chuzom/budget_backend.py:492-567` (`release`/`commit`, each independently locked/transacted)
- **Status:** CONFIRMED (executed repro)

### Scenario

`commit_envelope()` settles a turn's budget-envelope reservation in two separate awaited backend calls:

```python
# quota_envelope_routing.py:96-113
async def commit_envelope(key, est_cost_usd, actual_cost_usd, *, backend=None):
    if key is None:
        return
    b = backend or _default_backend()
    try:
        await b.release(key, est_cost_usd)
        await b.commit(key, actual_cost_usd, settle_pending=False)
    except Exception as exc:
        log.warning("envelope_commit_failed", ...)
```

Each of `release()` and `commit()` on `SqliteBudgetBackend` (and identically on the in-process `BudgetEnvelopeManager`) independently acquires and releases the backend's `asyncio.Lock` and runs its own separate `BEGIN IMMEDIATE ... COMMIT` transaction. Between the two awaits there is a real window where:
- `pending_usd` has already been decremented (the reservation is "undone"), but
- `consumed_usd` has **not yet** been incremented with the actual spend.

During that window the envelope looks like the money was never spent at all. A concurrent `try_reserve()` against the same key — or an ancestor key shared via the parent chain — sees an under-counted total and can be admitted even though it pushes the true combined exposure over the cap. This is not an edge case: two ordinary turns settling close together against a shared (team/org/tenant) envelope is routine concurrency, not an adversarial scenario.

The module docstring for `quota_envelope_routing.py` (lines 1-34) explicitly documents this two-step sequence as the *intended* design ("release(est) then commit(actual)"), so this is a genuine atomicity gap in the `BudgetBackend` protocol's API surface, not an accidental ordering bug — no backend implementation (SQLite, in-process, or the experimental Postgres backend) can close it without a protocol-level change, since the `BudgetBackend` Protocol has no single atomic "settle" operation combining release+commit in one transaction/lock-hold.

### Repro (executed)

`/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_commit_race.py`

Deterministically interleaves a `try_reserve()` call exactly in the gap between `release()` and `commit()`, i.e. exactly what a concurrently-scheduled coroutine would experience in production during that async gap.

Output:
```
After A reserves: consumed=0.0, pending=0.99
MID-WINDOW (after release, BEFORE commit): consumed=0.0, pending=0.0
Turn B try_reserve(0.99) during the window -> True
FINAL: consumed=0.99, pending=0.99, total_exposure=1.98, cap=1.0
CONFIRMED: cap breached. total_exposure=1.98 > cap=1.0 even though every individual try_reserve() call was 'within cap' at the instant it ran.
```

A $1.00 cap was breached to $1.98 total exposure with two turns that were each individually valid at the instant their `try_reserve()` ran.

### Suggested fix

Add a single atomic `settle(key, est_cost_usd, actual_cost_usd)` method to the `BudgetBackend` protocol/all three implementations that performs the pending-decrement and consumed-increment in **one** lock-hold / one transaction (mirroring how `_try_reserve_sync` already does its CHECK-then-MUTATE atomically within a single `BEGIN IMMEDIATE`). Change `commit_envelope()` to call `b.settle(key, est, actual)` instead of two separate awaited calls. Until that lands, a stop-gap is to have `commit()` accept the estimate directly and perform both adjustments itself (`commit(key, actual, release_est=est)`), eliminating the caller-visible two-step gap.

---

## RED1-7-02 — Content-aware hook/rules update silently destroys user customizations

- **Severity:** High
- **File:** `src/chuzom/install_hooks.py:165-217` (`check_and_update_hooks`), `:220-250` (`check_and_update_rules`), `:140-150` (`_files_differ`)
- **Status:** CONFIRMED (executed repro)

### Scenario

The iteration-6 "content-aware" fix (RED2-6-01/03) changed the update trigger from purely version-gated (`src_v > dst_v`) to also re-copy whenever `src_v == dst_v and _files_differ(src, dst)` — i.e., whenever the bundled and installed files have matching version stamps but different byte content ("drift"). This was added to stop genuine behavior fixes from being stranded on machines where a maintainer forgot to bump the stamp.

The unintended consequence: version stamps (`# chuzom-hook-version: N` / `<!-- chuzom-rules-version: N -->`) are an internal implementation detail. Nothing in the shipped hook files or rules file tells a user "do not edit" or "bump this comment if you customize this file" — the header of `auto-route.py` is a plain docstring with no such warning, confirmed by inspection. Any user who hand-edits an installed hook (e.g. to add a personal skip-rule, a custom classifier tweak, or an org-specific routing exception) — the file's actual designed extensibility point, since it's plain Python dropped in `~/.claude/hooks/` — will have that edit silently and permanently destroyed the next time `check_and_update_hooks()` runs, because the edited file still carries the original (unchanged) version stamp and thus is now classified as "drifted," not "user-owned."

This is not a rare event: `check_and_update_hooks()`/`check_and_update_rules()` are called unconditionally at MCP-server-module-import time on **every** startup (`src/chuzom/server.py:47-56`, wrapped only in a broad `try/except: pass`, with no gating such as "only after a version bump" or "only once per pip upgrade"). Since Claude Code typically spawns a fresh MCP server process per session, this means a user's hook customization can be wiped on the very next session after they make it — not just on the next `pip install --upgrade`.

The exact same mechanism applies to `~/.claude/rules/chuzom.md` via `check_and_update_rules()` — confirmed live: the file currently installed at that path on this machine (visible in this session's own system context) is precisely the bundled `chuzom.md` managed by this function.

### Repro (executed)

`/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_hook_clobber.py`

Simulates a user installing the bundled `auto-route.py`/`chuzom.md`, then hand-appending a personal customization without touching the version-stamp comment, then calling the real `check_and_update_hooks()`/`check_and_update_rules()` (redirected to an isolated tmp `~/.claude`, no production files touched).

Output:
```
Before check_and_update_hooks(): installed hook has user customization (173287 bytes, 173206 bytes originally)
src version=27, dst version=27
check_and_update_hooks() returned: [..., 'Refreshed chuzom-auto-route.py (content drift at v27)', ...]
After: installed hook is now 173206 bytes (user customization DESTROYED)

Before check_and_update_rules(): installed rules file has user customization (3883 bytes, 3784 bytes originally)
check_and_update_rules() returned: 'Refreshed routing rules (content drift at v7)'
After: installed rules file is now 3784 bytes (user customization DESTROYED)

=== SUMMARY ===
hook customization clobbered:  True
rules customization clobbered: True
```

Both the hook customization and the rules customization were silently and permanently overwritten, with no backup, no diff surfaced to the user, and no warning beyond a low-visibility `log.info("hook_updated", ...)` line (`server.py:53-54`) that most users will never see.

Note the stale docstring at `install_hooks.py:172`: *"Existing files are only overwritten when the bundled version is newer, to avoid clobbering user-managed scripts."* — this is no longer true post-RED2-6-01 and should be corrected regardless of the fix chosen below, since it actively misleads future maintainers about the safety guarantee this function provides.

### Thrashing sub-check (ruled out — CLEAN)

Tested whether `_files_differ`'s content comparison could cause every-startup re-copying (thrash) due to line-ending/permission/mtime false positives: `_files_differ` does a raw `read_bytes()` comparison on both sides (immune to mtime/permission metadata), and `shutil.copy2` produces byte-identical copies, so a second immediate call to `check_and_update_hooks()`/`check_and_update_rules()` with no further edits returns no updates (confirmed empty `[]` / `None`). **No thrashing bug found** — this sub-concern is CLEAN.

### Suggested fix

Do not treat "same version, different bytes" as an unconditional signal to overwrite. Options, in order of preference:
1. Track and persist a hash of the *bundled* file at the time it was last installed (e.g. a `.chuzom-installed-hashes.json` sidecar). Only auto-overwrite when the installed file's hash still matches the previously-installed bundled hash (i.e., it's untouched by the user) AND differs from the new bundled hash. If the installed file's hash doesn't match what was last installed, the user has edited it — skip and surface a visible warning ("hook X has local changes and a newer bundled version is available; run `chuzom-install-hooks --force` to overwrite, or diff manually") instead of silently overwriting.
2. At minimum, back up the about-to-be-overwritten file (e.g. `dst.with_suffix(dst.suffix + ".bak")`) before any content-drift overwrite, and log at a visible level (not just `log.info` swallowed by a broad `except Exception: pass` wrapper in `server.py`).
3. Fix the stale docstring at `install_hooks.py:172` regardless of which fix lands.

---

## Priority 1 — iteration-6 transitive parent-chain fix — CLEAN (no findings)

Tested against **both** production-relied-upon backends (`SqliteBudgetBackend._chain_rows` and the in-process `BudgetEnvelopeManager._chain`), by executing (not just reading) three targeted repros for each of the mandated sub-checks:

1. **Cycle guard (a)** — a direct 2-node cyclic parent registration (`k1` parents `k2`, `k2` parents `k1`) does not hang `try_reserve`; returns normally within a 5s watchdog on both backends.
2. **Diamond no-double-count (b)** — a diamond hierarchy (`bottom` → `left`/`right` → `top`, both paths converging on `top`) does not double-charge the shared ancestor: after reserving 3.0 against `bottom`, `top.pending == 3.0` (not 6.0) on both backends; after commit+release, `top.consumed == 3.0`, `top.pending == 0.0` on both backends.
3. **Mid-chain atomic rollback (c)** — a 3-level chain (`leaf` → `mid` → `top`) where `top`'s cap rejects a reservation leaves **zero** residual `pending_usd` at `leaf` or `mid` on both backends — the CHECK-then-MUTATE atomic transaction pattern in `_try_reserve_sync` (budget_backend.py:425-490) correctly prevents any partial reservation from leaking when a deeper/higher level in the chain rejects.

Repros: `/private/tmp/.../scratchpad/repro_chain_checks.py` (SQLite) and `/private/tmp/.../scratchpad/repro_chain_inprocess.py` (in-process manager). Both produced all-pass output, reproduced verbatim below.

SQLite backend:
```
(a) try_reserve on cyclic chain returned: True (no hang)
(b) after reserving 3.0 against `bottom`: top.pending = 3.0
    after commit+release: top.consumed = 3.0, top.pending = 0.0
(c) try_reserve(leaf, 5.0) with top near-exhausted -> False
    post-reject state: leaf.pending=0.0, mid.pending=0.0, top.pending=0.99
```

In-process manager:
```
(a) cycle: try_reserve -> True (no hang)
(b) diamond: reserve ok=True, top.pending=3.0 (expect 3.0)
    diamond: top.consumed=3.0 (expect 3.0), top.pending=0.0 (expect 0.0)
(c) midchain: reserve(leaf,5.0) with top near-exhausted -> False
    midchain: leaf.pending=0.0, mid.pending=0.0, top.pending=0.99
```

**Not independently repro-tested:** `PostgresBudgetBackend._chain_keys` (budget_backend_postgres.py:372-399) — the file carries an explicit EXPERIMENTAL disclaimer and is not the production-relied-upon path; code reading in a prior session showed the same BFS-with-`seen`-cycle-guard pattern as the other two backends, and its `_try_reserve_sync` (263-298) notably lacks the `_CAP_EPSILON` float-drift tolerance present in the SQLite backend. Given the explicit experimental status, this is downgraded to PLAUSIBLE/not release-blocking rather than a scored finding.

## Priority 3/4 — broad correctness pass on `route_and_call` / `_dispatch_model_loop` — CLEAN except for RED1-7-01 above

Read and traced (not just grepped) the full post-dispatch structure of `route_and_call` (router.py ~3360-4134) plus the reservation-cleanup helper and two additional early-exit fast paths, specifically trying to break the iteration-4/5/6 fixes noted in code comments (RED1-4-01, RED1-4-02, RED1-5-01, RED1-5-02, RED1-3-01, RED1-3-02):

- **`_release_reservation_if_held()` (router.py:3365-3377)** — a single idempotency-guarded helper (`_reservation_released` flag) that releases both `_pending_spend` (under `_budget_lock()`) and the distributed envelope (`release_envelope`, swallowing its own errors) exactly once no matter how many call sites invoke it. Used consistently at every early-exit point traced: the empty-model-chain `ValueError` path (3543, "RED1-3-01"), the semantic-cache-hit fast-return path (3592, "RED1-3-02"), and the daily-cap-exceeded path (3530). No leak found at any of these sites.
- **`except asyncio.CancelledError` / `except asyncio.TimeoutError` (router.py:3888-3994)** — both correctly decrement `_pending_spend` and call `release_envelope` before re-raising/raising, each with its own defensive audit-write try/except.
- **`except Exception:` general handler (router.py:3995-4008, "RED1-4-02")** — verified by reading (not trusting the comment) that it releases **only** the distributed envelope, correctly relying on `_dispatch_model_loop` having already released `_pending_spend` internally on this path (confirmed via the three `_pending_spend` release sites inside `_dispatch_model_loop`: 2629-2630 primary-loop success, 2781-2782 emergency-loop success, 2813-2814 chain-exhaustion tail) — no double-release, no leak.
- **Success-path settlement sequence (router.py:4009-4091)** — not wrapped in any try/except at this level by design; traced `audit_routing_turn()` (audit_routing.py:93-155, full body wrapped in `try/except Exception: log.warning`, cannot propagate) and `record_consumption()` (quota_routing.py:130-153, per-scope try/except, cannot propagate) and confirmed neither can abort the sequence before `commit_envelope()` runs — ruled out as a source of a *different* leak; this is where **RED1-7-01** (above) was found instead, in `commit_envelope()` itself. The subsequent `dataclasses.replace(response, ...)` patch for frozen `LLMResponse` (4080-4089, "RED2-02") is correctly guarded by try/except and does not mutate the frozen instance in place.
- **`_BG_TASKS` (router.py:101,107-108,114)** — module-level `set[asyncio.Task]`; `_spawn_bg()` adds each task and registers `_BG_TASKS.discard` as its `add_done_callback`, so tasks self-remove on completion regardless of success/failure — no unbounded growth or leak pattern found on inspection.

No additional Critical/High/core-Medium findings from this pass.

---

## Checklist (auditable)

| Area | Result |
|---|---|
| Chain cycle guard (SQLite) | CLEAN — confirmed via repro |
| Chain cycle guard (in-process) | CLEAN — confirmed via repro |
| Chain diamond no-double-count (SQLite) | CLEAN — confirmed via repro |
| Chain diamond no-double-count (in-process) | CLEAN — confirmed via repro |
| Chain mid-level atomic rollback (SQLite) | CLEAN — confirmed via repro |
| Chain mid-level atomic rollback (in-process) | CLEAN — confirmed via repro |
| Chain checks (Postgres, experimental) | Not repro'd — code-read only, PLAUSIBLE-not-scored given EXPERIMENTAL status |
| `commit_envelope()` release/commit atomicity | **FINDING RED1-7-01 (High)** — confirmed via repro |
| Hook update clobbering user customization | **FINDING RED1-7-02 (High)** — confirmed via repro |
| Hook/rules update thrashing (line-ending/perm/mtime) | CLEAN — confirmed via repro (idempotent on repeat calls) |
| `_pending_spend` single-release across all `route_and_call` exit paths | CLEAN — traced every exit site |
| General `except Exception:` handler no-double-release | CLEAN — confirmed by reading, not trusting comment |
| `audit_routing_turn`/`record_consumption` cannot abort success-path settlement | CLEAN — confirmed by reading |
| Frozen `LLMResponse` mutation safety | CLEAN — uses `dataclasses.replace` |
| `_BG_TASKS` leak/growth | CLEAN — self-removing via `add_done_callback` |
