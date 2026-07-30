# RED-1 Architecture & Correctness Audit — Iteration 11

**Auditor:** RED-1 (independent, adversarial)
**Commit:** `1986990` (`198699085b43c7897c944ab2f156ea2cdb610789`)
**Scope:** install/uninstall manifest hardening review, budget/spend correctness,
concurrency (`_BG_TASKS`/lifespan, `_budget_lock`), frozen `LLMResponse` mutation
safety, render-mode allow-list, content-aware hook/rules update backup safety,
open-ended sweep.

**Verdict: 2 findings, both HIGH.** Both are CONFIRMED via repro. No Critical,
no additional core-Medium findings after exhaustive review of the 5 mandated
coverage areas.

---

## RED1-11-01 — `install()` overwrites a hand-edited `~/.claude/rules/chuzom.md` with ZERO backup attempt

**Severity:** HIGH
**File:** `src/chuzom/install_hooks.py:830-837` (inside `install()`)

```python
rules_src = _RULES_SRC / "chuzom.md"
rules_dst = _RULES_DST / "chuzom.md"

if rules_src.exists():
    shutil.copy2(rules_src, rules_dst)
    actions.append(f"Installed routing rules → {rules_dst}")
```

### Failure scenario

`chuzom install` is the documented, user-facing, freely-re-runnable headline
command (has its own `--force` flag anticipating repeated runs; `cmd_install`
routes here for the default `claude-code` host). Any time a user:

1. Hand-edits their global routing rules (`~/.claude/rules/chuzom.md` — the
   very file whose *content* dictates this repo's own inherited routing
   rules), or
2. Simply re-runs `chuzom install` after `pip install --upgrade chuzom-router`
   ships a new bundled `chuzom.md` (any content change, not just a version
   bump; not gated by any diff/version check at all),

...their `chuzom.md` is overwritten unconditionally via a bare
`shutil.copy2(rules_src, rules_dst)`. Unlike every other managed-file
overwrite path in this file — `check_and_update_hooks()` (line 237, guarded
by RED1-8-02), `check_and_update_rules()` (line 294, guarded by the same
RED1-8-02 pattern for this exact file), and even `install()`'s own hook-file
loop (line 765, see RED1-11-02 below) — **this path never calls
`_backup_before_overwrite()` at all.** There is no attempt to preserve the
previous content, no `.bak` file, no warning in the returned `actions` list,
and no way to recover. This directly regresses the RED1-7-02 invariant ("a
hand-edited managed hook/rules file is never SILENTLY and PERMANENTLY
destroyed") for the one call path users are most likely to trigger on
purpose.

### CONFIRMED — repro

Script: `/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_install_backup_gap.py`
(monkeypatches `install_hooks._RULES_DST`/`_HOOKS_DST`/`_CLAUDE_DIR`/
`_SETTINGS_PATH` to an isolated temp "fake home"; real bundled `_RULES_SRC`
used unmodified as the source). Run with
`/Users/yaliandrona/Projects/Chuzom/.venv/bin/python`:

```
=== Scenario B: rules hand-edit survived install()? ===
DATA LOSS CONFIRMED: rules hand-edit was overwritten with ZERO backup!
  (current content starts with: <!-- chuzom-rules-version: 7 -->\n# Chuzom — Global Routing Rules... )
  backup files present in rules dir: []
```

The `install()` `actions` output for this run contains only
`"Installed routing rules → …/rules/chuzom.md"` — no `"Backed up"`, no
`"SKIPPED"`, nothing indicating the prior content was destroyed.

### Fix

Mirror `check_and_update_rules()`'s existing, already-correct logic in
`install()`: only overwrite when content actually differs, back up first via
`_backup_before_overwrite()`, and skip the overwrite (append a `SKIPPED`
message) if the backup fails — exactly the RED1-7-02/RED1-8-02 pattern
already implemented at lines 288-301 for the *auto-update* path. E.g.:

```python
if rules_src.exists():
    if rules_dst.exists() and _files_differ(rules_src, rules_dst):
        backup = _backup_before_overwrite(rules_dst)
        if backup is None:
            actions.append(
                "SKIPPED routing rules update: could not back up existing "
                "file — update NOT applied (previous content preserved)"
            )
        else:
            shutil.copy2(rules_src, rules_dst)
            actions.append(f"Installed routing rules → {rules_dst} (previous saved to {backup.name})")
    elif not rules_dst.exists():
        shutil.copy2(rules_src, rules_dst)
        actions.append(f"Installed routing rules → {rules_dst}")
    else:
        actions.append("Routing rules already up to date")
else:
    actions.append(f"SKIP rules: source not found at {rules_src}")
```

(Simplest alternative: just call `check_and_update_rules()` from within
`install()` instead of duplicating the copy logic.)

---

## RED1-11-02 — `install()` overwrites a hand-edited hook file even when the backup write fails

**Severity:** HIGH
**File:** `src/chuzom/install_hooks.py:761-768` (inside `install()`, hook-copy loop)

```python
# RED1-9-01: back up a hand-edited managed hook before install overwrites
# it, so a user's local change is recoverable (parity with the auto-update
# path). Only when the installed file differs from what we're about to write.
if dst.exists() and _files_differ(src, dst):
    _b = _backup_before_overwrite(dst)
    if _b is not None:
        actions.append(f"Backed up existing {dst_name} → {_b.name}")
shutil.copy2(src, dst)          # <-- unconditional, runs even if _b is None
```

### Failure scenario

The comment explicitly claims "parity with the auto-update path"
(`check_and_update_hooks()`), but the two paths diverge exactly at the
failure branch. In `check_and_update_hooks()` (lines 234-254), a `None`
return from `_backup_before_overwrite()` causes the overwrite to be
**skipped entirely** (RED1-8-02: "if the backup cannot be written, do NOT
overwrite"). In `install()`, the `if _b is not None:` check only gates
whether a *log line* is appended — `shutil.copy2(src, dst)` on the next line
runs unconditionally regardless of whether the backup succeeded. If
`_backup_before_overwrite()` fails (disk full, permission denied on the
`~/.claude/hooks/` directory, backup path on a read-only mount, etc. — all
realistic conditions given `_backup_before_overwrite` explicitly catches
`OSError` and returns `None` for exactly this reason), a hand-edited managed
hook file is destroyed with **no backup and no warning message** — silently
regressing the very RED1-9-01/RED1-8-02 guarantee the surrounding comment
claims to provide.

### CONFIRMED — repro

Same script as above, Scenario A: monkeypatches `shutil.copy2` (as bound in
the `install_hooks` module) to raise `OSError` only when writing a `*.bak`
destination (simulating a backup-write failure), leaving the real
src→dst hook copy untouched. Hand-edits `chuzom-session-start.py` before
running `install(force=False)`:

```
=== Scenario A: hook hand-edit survived backup-write failure? ===
DATA LOSS CONFIRMED: hook hand-edit was overwritten despite backup failure!
  (current content starts with: #!/usr/bin/env python3\n# chuzom-hook-version: 18\n"""SessionStart hook... )
  backup files present: []
```

No `"Backed up existing …"` or `"SKIPPED …"` line appears in `install()`'s
returned `actions` for this hook — the user has no indication their
customization was lost.

### Fix

Gate the copy on backup success, matching `check_and_update_hooks()`:

```python
if dst.exists() and _files_differ(src, dst):
    _b = _backup_before_overwrite(dst)
    if _b is None:
        actions.append(
            f"SKIPPED {dst_name}: could not back up existing file — "
            f"update NOT applied (previous content preserved)"
        )
        continue  # or otherwise skip the shutil.copy2 below for this hook
    actions.append(f"Backed up existing {dst_name} → {_b.name}")
shutil.copy2(src, dst)
```

(Care needed: the loop body also does registration/chmod/legacy-alias work
after the copy — a bare `continue` would skip those too. If registration
should still happen even when the file copy is skipped, restructure with an
explicit `did_copy` flag instead of `continue`.)

---

## Coverage checklist (what was verified this round)

1. **`install_manifest.py` post-hardening** (absolute-path recording,
   non-dict-record guard, `created_file` strip-not-delete,
   `_remove_*` helpers) — re-read in full this session via system-reminder
   re-surfacing; matches prior-session CONFIRMED-CLEAN read exactly, no new
   issues. **CLEAN.**
2. **Budget/spend correctness** (`_pending_spend` reservation/release on
   every exit path, atomic `settle`, `chain_attempt_cost_usd` no
   double-count, TQ-007 cap downgrade, parent-chain rollup) — re-confirmed
   from prior-session deep reads (`_enrich_response`, `_release_reservation_if_held`,
   the reservation block at router.py:3255-3394); no new candidate defect
   surfaced. **CLEAN** (no new findings this round; this area was fully
   closed in prior iterations).
3. **Concurrency:**
   - `_BG_TASKS`/`_spawn_bg`/`drain_bg_tasks` (router.py:95-122) +
     FastMCP `_lifespan` (server.py:47-66): fully read this session, task
     references held strongly in a module-level set until `add_done_callback`
     discard, lifespan `try/yield/finally: await drain_bg_tasks(...)`
     runs on the same event loop and is itself exception-wrapped so it can
     never block shutdown. **CLEAN.**
   - `_budget_lock()`/`_AsyncProcLock` (router.py:1096-1119): a
     process-wide `threading.Lock`, confirmed never nested across all 9
     call sites in router.py (grepped `cost.py`/`policy.py`/
     `repo_config.py`/`session_spend.py` for `_budget_lock` — zero hits, so
     nothing called from within a lock block re-enters it). The largest
     lock block (router.py:3272-3361) does hold the lock across 3
     sequential `await`s into `cost.py` (`get_daily_spend`,
     `get_daily_spend_by_task_type`, `get_monthly_spend`), each opening its
     own aiosqlite connection — this is an intentional, documented
     check-then-reserve atomicity trade-off (serializes concurrent
     `route_and_call` calls during the window, not a deadlock or lost
     update). Not reported as a defect: no proven correctness harm, only a
     throughput characteristic under heavy concurrent load. **CLEAN** (no
     deadlock/race found).
4. **Frozen `LLMResponse` mutation safety** (`types.py:457-508`): grepped
   entire `src/chuzom/*.py` for `object.__setattr__` — the only hit is on an
   unrelated frozen dataclass in `config.py:627`, never on `LLMResponse`.
   The one call site that "modifies" a response (`_enrich_response`,
   router.py:1488-1511) correctly uses `dataclasses.replace(...)`.
   **CLEAN.**
   Render-mode allow-list (`hooks/auto-route.py:2243-2267`
   `_resolve_auto_render_mode` + call site at lines 3229-3244): unrecognized
   values fail safe to non-blocking `"echo"`; `_turn_blocked` is derived
   purely from the already-resolved mode (no re-testing of `zero_claude` at
   the call site). **CLEAN.**
   Content-aware hook/rules update backup safety (`install_hooks.py`):
   **NOT CLEAN — see RED1-11-01 and RED1-11-02 above.** The auto-update
   path (`check_and_update_hooks`/`check_and_update_rules`, used at MCP
   server startup) correctly implements the backup-or-skip guarantee; the
   manual `install()` CLI path (the one users actually invoke by hand, with
   a `--force` flag anticipating re-runs) does not, for both hooks (partial:
   backup attempted but not gated on failure) and rules (total: no backup
   attempted at all). The `settings.json` corruption-recovery backup
   (`_save_settings`, lines 364-389) was also read and is correct: it backs
   up only when the *existing* file fails to parse as JSON, then writes
   atomically via tmp+`os.replace`; no defect found there.
5. **Open-ended sweep**: reviewed `_migrate_remove_legacy_llm_router()`
   (install_hooks.py:67-77) — deletes only chuzom's own narrowly-scoped
   legacy pre-rebrand artifact paths (`llm-router.md`/`llm-router-*.py`),
   each guarded by `try/except OSError: pass`; not a general user-data
   deletion risk, working as documented. The statusline install
   (install_hooks.py:846-852) unconditionally overwrites
   `chuzom-statusline.sh`, but that file is not a documented user
   customization surface (unlike hooks/rules, which have an established
   hand-edit-and-recover contract via the RED1-7-02 lineage) — not reported.
   No other spend-miscounting, mis-routing, or crash-on-common-input
   candidates surfaced during this pass; time was concentrated on
   confirming RED1-11-01/02 with reproductions rather than a further
   unguided sweep.

## What was NOT re-litigated this round (carried as still-open questions from prior sessions, not re-confirmed or re-denied here)

- Whether the `except asyncio.CancelledError` handler in `route_and_call`'s
  "acceptable... bounded" framing for a potentially-skipped
  `_pending_spend`/envelope release under external cancellation is fully
  correct — not revisited this session; no new evidence gathered either way.
- `budget.py`'s `_pending_spend_by_key`/`_pending_tokens` module-level dicts
  (lines 42, 105-111, 125-167) were grepped but not re-read in full or
  cross-checked against `_budget_lock` this session — believed to be a
  logically separate, GIL-serialized synchronous counter based on prior-session
  understanding, but this was not independently re-verified this round.

---

## Summary for orchestrator

**2 HIGH findings, 0 Critical, 0 additional core-Medium.**

- RED1-11-01 (HIGH): `install()` overwrites a hand-edited
  `~/.claude/rules/chuzom.md` with zero backup attempt — confirmed 100%
  reproducible data loss on any `chuzom install` re-run where bundled
  content differs from installed content.
- RED1-11-02 (HIGH): `install()`'s hook-file copy loop overwrites a
  hand-edited hook even when `_backup_before_overwrite()` fails — confirmed
  via simulated backup-write failure; silently regresses the documented
  RED1-9-01/RED1-8-02 guarantee that's correctly enforced in the parallel
  auto-update path.

Both are CONFIRMED (not PLAUSIBLE) via runnable repros against the real
`install()` function in an isolated fake-home sandbox, using the actual
bundled hook/rules sources as input.
