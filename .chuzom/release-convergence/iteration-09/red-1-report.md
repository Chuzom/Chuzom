# RED-1 Adversarial Audit — Iteration 9

**Auditor:** RED-1 (ARCHITECTURE & CORRECTNESS)
**Commit:** `fe175a0`
**Scope:** Priority items 1-6 per orchestrator mandate (see below).
**Method:** Direct code reading + Bash-executed Python repros against
`/Users/yaliandrona/Projects/Chuzom/.venv/bin/python`. Worked independently;
did not read any RED-2 (or other auditor) output.

## Verdict

**2 findings at reportable severity: 1 Critical, 1 High.**
Everything else checked (see "What else was checked" below) is CLEAN.

---

## RED1-9-02 — Critical

**Uninstall-time TOML table removal silently destroys unrelated tables
(and reports false success) when tables aren't blank-line-separated**

- **File:** `src/chuzom/commands/install.py`
- **Function:** `_remove_toml_table_block(text: str, header: str) -> str`, lines 661-668
- **Caller:** `uninstall_host_integrations()`, Codex TOML-removal block (~lines 671-750), which writes the regex's output straight back to `~/.codex/config.toml` with **no backup**.

### The code

```python
def _remove_toml_table_block(text: str, header: str) -> str:
    """Remove a `[header]` TOML table and its body (until the next table / EOF)."""
    import re
    pattern = re.compile(
        rf'(?:^|\n)\[{re.escape(header)}\]\s*\n(?:(?!\n\[).*\n?)*',
        re.MULTILINE,
    )
    return pattern.sub("\n", text, count=1)
```

### Failure scenario

The negative lookahead `(?!\n\[)` only detects a table boundary when the
cursor sits at a position where the literal next two characters are
`\n` followed by `[` — i.e. it only works when a **blank line** separates
the target table from the next one. TOML does not require blank lines
between tables (a common, valid, unforced style). When the next table
immediately follows without a blank line, the greedy
`(?:(?!\n\[).*\n?)*` loop never finds a boundary and consumes everything
through **EOF**, deleting every table that follows the target — not just
the immediately-next one.

This is reachable in real usage: the chuzom installer always appends
`[model_providers.chuzom]` as the *last* table on install (see
`_ensure_toml_table_block`, lines 412-417), so the bug is dormant on a
pure install→uninstall round trip. But it fires the moment anything is
appended after it later without a blank-line separator — by the Codex
CLI itself, another tool, or a hand-edit — which is entirely plausible
over the life of a `~/.codex/config.toml` file that chuzom does not
exclusively own.

The caller reports `"✓ Removed [model_providers.chuzom] from {config_toml}"`
regardless of whether the regex over-matched, so the user is told the
operation succeeded while their unrelated Codex provider configuration
was silently wiped. No backup is taken before this write (contrast with
the install-side Codex writer, which takes a `.chuzom-bak` snapshot
before its own write — lines ~483-490 of the same file).

### CONFIRMED — repro

Saved repro:
`/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_toml_overmatch.py`

```
$ .venv/bin/python repro_toml_overmatch.py
Case A (blank-line separated): [model_providers.other] survived — OK
Case B (2 tables, no blank line): [model_providers.other] survived = False
  --- resulting text ---
'\n'
Case C (3 tables, no blank line): other survived = False, third survived = False
  --- resulting text ---
'\n'

*** CONFIRMED: _remove_toml_table_block over-matches through EOF, silently destroying unrelated TOML tables when not blank-line-separated. ***
EXIT=1
```

Both `[model_providers.other]` and `[model_providers.third]` (with all
their key/value content) are deleted along with `[model_providers.chuzom]`,
confirming the over-match runs to EOF, not just to the next table.

### Fix

Bound the lookahead to a real table-header boundary instead of requiring
a blank line, e.g. match up to (but not including) the next line that
starts with `[` at column 0, or the end of string:

```python
pattern = re.compile(
    rf'(?:^|\n)\[{re.escape(header)}\]\s*\n(?:(?!\[)[^\n]*\n?)*',
    re.MULTILINE,
)
```

(`(?!\[)` anchored at line-start via `re.MULTILINE`, without requiring a
preceding `\n` in the lookahead itself — verify against nested `[[array
tables]]` and multi-line strings containing `[` at line-start, which is
a separate edge case worth a follow-up test either way.) Additionally,
take a backup (mirroring the install-side `.chuzom-bak` pattern) before
this write, and verify the removal only stripped the intended span
(e.g. by re-parsing the result and confirming no other top-level table
lost keys) before trusting/reporting success.

---

## RED1-9-01 — High

**`install()` / `install_claw_code()` clobber hand-edited hook files with
zero backup, unlike the safe auto-update path**

- **File:** `src/chuzom/install_hooks.py`
- **Functions:** `install(force: bool = False) -> list[str]`, lines 729-881 (hook-copy loop ~741-777); `install_claw_code() -> list[str]`, lines ~989-1085
- **Real callers:** `chuzom-install-hooks` CLI entry point (`main()`, lines 1296-1340, calls `install()` with no args → `force=False`, and exposes **no `--force` flag** to change this); `onboard.py` line 211 (`install_actions = _install_hooks()`, also `force=False`); `commands/install.py` line 204 (`cc_actions = install_claw_code()`).

### The code (install() hook-copy loop)

```python
for src_name, dst_name, event, matcher in _HOOK_DEFS:
    src = _HOOKS_SRC / src_name
    dst = _HOOKS_DST / dst_name

    if not src.exists():
        actions.append(f"SKIP {src_name}: source not found at {src}")
        continue

    if not force and dst.exists():
        try:
            if src.read_bytes() == dst.read_bytes():
                command = f"{_python_exe()} {dst}"
                already_registered = _hook_is_registered(settings, event, matcher, command)
                if already_registered:
                    continue
        except OSError:
            pass

    shutil.copy2(src, dst)
    ...
```

There is no call to `_backup_before_overwrite()` anywhere in this loop.
`install_claw_code()` is worse: it has no same-content check at all and
unconditionally `shutil.copy2(src, dst)`s every invocation.

Contrast with the automatic background-update path
(`check_and_update_hooks()` / `check_and_update_rules()`, lines 196-304),
which correctly calls `_backup_before_overwrite()` before any overwrite
and hard-stops (does not overwrite) if it returns `None` (backup
failure). That contract exists and is honored there — it's simply never
invoked from the explicit, user-triggered install path.

### Failure scenario

A user (or another tool) hand-edits a managed hook file, e.g.
`~/.claude/hooks/chuzom-auto-route.py`, to add a local tweak. They later
re-run `chuzom-install-hooks` (or re-run onboarding, or reinstall Claw
Code integration) for an unrelated reason — e.g. to pick up a newly
added hook. Their edit is silently overwritten with the bundled version,
with no `.bak` file created and no warning that content differed.

### CONFIRMED — repro

Saved repro:
`/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/repro_install_backup.py`

```
After run 1: target exists = True
Hand-edit applied to chuzom-auto-route.py
.bak files before run 2: []

.bak files after run 2: []
Hand-edit marker survived? False
File reverted to bundled bytes? True

*** CONFIRMED: hand-edit silently destroyed, NO backup written. ***
```

### Fix

Call `_backup_before_overwrite(dst)` in both `install()`'s hook-copy loop
and `install_claw_code()` before `shutil.copy2(src, dst)`, using the same
hard-stop-on-`None` contract already implemented in
`check_and_update_hooks()` / `check_and_update_rules()`. Optionally add a
`--force`/`--no-backup` CLI flag for users who explicitly want to
overwrite without a backup.

---

## What else was checked and ruled out (no report-worthy defect)

1. **RED1-8-01 rejected-attempt billing** — re-confirmed correct (prior sessions).
2. **Atomic `settle(key, est, actual)` across all 3 `BudgetBackend`s + `commit_envelope`** — re-confirmed correct across in-memory, SQLite, and Postgres backends (prior sessions).
3. **`server.py` `_lifespan` / `drain_bg_tasks` (RED1-8-05 area)** — confirmed CLEAN. `_lifespan` correctly awaits `drain_bg_tasks(timeout_s=5.0)` on shutdown, on the same event loop as the tracked tasks, itself wrapped in `try/except: pass` so it can never block shutdown. `_BG_TASKS`/`_spawn_bg` hold strong references (no GC-mid-flight risk) and the drain is bounded (`asyncio.wait(..., timeout=timeout_s)` then cancel + gather stragglers).
4. **`_remove_json_mcp_block()`** (the JSON-host counterpart to the TOML removal above) — confirmed safe. A malformed non-dict top-level JSON value would raise `AttributeError` on `existing.get(root_key)`, but this happens *before* any write, and the caller (`uninstall_host_integrations()`'s per-host loop) wraps each call in `try/except Exception`, degrading to a "host cleanup skipped" message with no corruption or crash propagation.
5. **`_save_settings()`** (`install_hooks.py` lines 364-389) — evaluated a narrow sub-finding (proceeds without hard-stopping if `settings.json` is *already* corrupt AND the corrupt-backup write itself also fails) and excluded it: the "lost" data in that double-failure scenario was already-corrupt garbage, not meaningful user data. Below the Critical/High/core-Medium bar.
6. **Broad sweep — reservation/envelope leaks on every `route_and_call` exit path**:
   - Confirmed `route_and_call` has no `finally:` block anywhere (verified via `awk` scan across the full function body) — a structural fact that makes every manual release site load-bearing on its own correctness rather than backstopped by a catch-all.
   - Confirmed the escalation-check `except BudgetExceededError:` manual-release pattern (~lines 3658-3697) is **not** exploitable: `_env_key` is provably `None` at that point (envelope reservation happens later, ~line 3757), and the handler ends in an unconditional `raise`. Latent stylistic trap for future refactors, not a current bug — excluded.
   - **This session:** examined both `release_tokens(provider, _res_tokens)` call sites in `_dispatch_model_loop` (lines 2703 and 2808) in full. Both are inside `finally:` blocks that wrap the entire try body (success-return **and** the broad `except Exception:` → `continue` branch for rate-limit/content-filter/auth-error/generic-failure), so release fires on every exit from that attempt, exactly once. Confirmed every pre-reservation skip (`tracker.is_healthy` check, quality-feedback skip, budget-pressure-exhausted skip, premium-cap skip, per-task cost-cap skip in the emergency loop) occurs **before** `reserve_tokens()` is called (line 2084 in the primary loop, line 2747 in the emergency loop), so no reservation is ever made for a skipped candidate — nothing to leak. **CLEAN.**
   - **This session:** examined the idempotency-store replay short-circuit (`idempotency_key` dedupe, lines 3164-3198). Confirmed the lookup and early `return _cached_resp` happen **before any reservation** (both the in-process `_pending_spend` reservation and the envelope `reserve_envelope()`, which happens later at ~line 3757) and before any provider is dispatched. The cached-response return path uses `cost_usd=0.0` in its audit row and calls `_emit_ledger_terminal(correlation_id, "bypassed", route_succeeded=True)`. A replayed/duplicate request with the same `idempotency_key` cannot double-bill. **CLEAN.**

Both threads of priority item 6 (the token-release sweep and the
idempotency replay check) that were open at the start of this session
are now resolved as CLEAN.

---

## Summary for orchestrator

- **Critical (1):** RED1-9-02 — `_remove_toml_table_block` regex over-matches through EOF, silently destroying unrelated TOML tables (e.g. Codex provider configs) on uninstall when not blank-line-separated, with a false "✓ Removed" success message and no backup.
- **High (1):** RED1-9-01 — `install()` / `install_claw_code()` silently overwrite hand-edited managed hook files with zero backup, unlike the correctly-guarded automatic-update path (`check_and_update_hooks()`/`check_and_update_rules()`), reachable via the plain `chuzom-install-hooks` CLI (no opt-out flag) and onboarding.
- No other Critical/High/core-Medium findings. Everything else audited this iteration (drain lifecycle, atomic settle, rejected-attempt billing, JSON host-integration removal, token-reservation symmetry across both dispatch loops, idempotency-replay non-double-billing) is CLEAN.
