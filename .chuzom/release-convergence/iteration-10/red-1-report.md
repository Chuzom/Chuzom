# RED-1 — Architecture & Correctness Audit — Iteration 10

Commit: 92367ce
Scope: `install_manifest.py` apply_uninstall/record, the RED1-9-02 TOML-regex fix in
`commands/install.py`, manifest recording-site round-trip correctness, and a broad
regression sweep of previously-fixed router.py/server.py/types.py areas.

Method: direct code reading + adversarial repro scripts under `/tmp/red1-iter10/`,
executed with `/Users/yaliandrona/Projects/Chuzom/.venv/bin/python`.

---

## Findings

### RED1-10-01 — HIGH — a single malformed manifest record silently aborts the entire uninstall replay, orphaning files on 5+ hosts

**File:** `src/chuzom/install_manifest.py`, lines 79-98 (`apply_uninstall`)

```python
for rec in reversed(records):
    try:
        kind = rec.get("kind")
        ...
    except Exception as e:  # noqa: BLE001 — one bad record must not abort the rest
        actions.append(f"  manifest removal skipped ({rec.get('path')}): {e}")
```

**Failure scenario:** if any entry in `install-manifest.json` is not a dict (e.g. a bare
string, int, or `null` — plausible from a future buggy `record()` call, manual editing,
or a torn/partial write since `record()`'s read-modify-write in `_load()`→append→
`write_text()` is non-atomic and has no fsync/locking), the per-record `try` correctly
catches the `AttributeError` from `rec.get("kind")` — but the **except handler itself**
then calls `rec.get('path')` to build the log message. Since `rec` is not a dict, this
raises a *second* `AttributeError`, which is not caught by anything inside
`apply_uninstall()` and propagates out of the function entirely — aborting the loop
**for every remaining record**, not just the malformed one.

`commands/uninstall.py` wraps the `apply_uninstall()` call in its own try/except
(`except Exception as e: actions.append(f"manifest cleanup skipped: {e}")`), so the CLI
does not crash — it prints one easy-to-miss line among dozens of `✓ Removed …` lines and
reports overall success. But **none of the records after the malformed one are replayed**.

Impact is not merely theoretical/cosmetic: `uninstall_host_integrations()` (the legacy,
hardcoded fallback that runs unconditionally afterward) only re-covers a fixed enumerated
set of paths — JSON MCP registrations, the Gemini extension dir, the Cursor rules file,
and Codex's TOML table / `config.yaml` block / `hooks.json`. It does **not** cover the
routing-rules `instructions.md` text blocks that are *solely* manifest-tracked for:
`~/.codex/instructions.md`, `~/.config/opencode/instructions.md`,
`~/.config/gh/copilot/instructions.md`, `~/.openclaw/instructions.md`, and the
project-scoped `.github/copilot-instructions.md` — confirmed by the module's own comment
at `commands/install.py:717-723` ("New installs are covered authoritatively by the
install manifest … which also handles the project-scoped writers
(.github/copilot-instructions.md, Trae .rules)"). If the malformed record sorts before
any of these in the manifest list (very plausible — records are appended in install
order, and the crash happens the first time a bad entry is hit while replaying
newest-first), the corresponding routing-rules blocks are **left behind permanently**
after a `chuzom uninstall` that reports success.

**CONFIRMED** — repro at `/tmp/red1-iter10/repro_malformed.py`:
```
CRASHED: AttributeError 'str' object has no attribute 'get'
```
A manifest with one good `created_file` record followed by one corrupted (non-dict)
record causes `apply_uninstall()` to raise instead of returning a partial-action list;
the good record's file is never removed.

**Fix:** guard the except handler itself, e.g.
```python
except Exception as e:
    _p = rec.get("path") if isinstance(rec, dict) else rec
    actions.append(f"  manifest removal skipped ({_p}): {e}")
```
and/or skip non-dict records up front (`if not isinstance(rec, dict): continue`) so one
corrupt entry can never interrupt the replay loop — restoring the function's own stated
invariant ("each removal is independently guarded, so one failure never aborts the rest").

---

### RED1-10-02 — HIGH — `created_file` uninstall kind blind-deletes the whole file, destroying any content the user added after install

**File:** `src/chuzom/install_manifest.py`, lines 89-92 (`apply_uninstall`, `created_file`/`file` branch)

```python
elif kind in ("created_file", "file"):
    if path.exists():
        path.unlink()
        actions.append(f"✓ Removed {path}")
```

**Failure scenario:** several installers use `created_file` for files chuzom creates
fresh (not appended-to), e.g. `~/.codex/instructions.md` when it didn't previously exist
(`commands/install.py` ~line 620), and analogous `instructions.md` creates for other
hosts. If the user later edits that same file — adding their own personal instructions
below chuzom's — `apply_uninstall()` does not diff or preserve any of it: it unconditionally
`unlink()`s the whole file, deleting the user's own content along with chuzom's, with no
backup and no confirmation. This is materially worse than the `text_block`/`toml_table`
removal paths in the same module, which surgically remove only the recorded substring/table
and leave everything else in the file intact (and even back up `.chuzom-bak` before mutating
TOML).

**CONFIRMED** — repro at `/tmp/red1-iter10/repro_created_file_dataloss.py`: a file created
by chuzom, then appended to by the "user" with clearly-personal content
(`# MY OWN PERSONAL CODEX INSTRUCTIONS…`), is fully deleted (`instructions.exists()` →
`False`) after `apply_uninstall()`, permanently losing the user's addition.

**Fix:** either (a) record `created_file` with a content hash/snapshot and only unlink if
the current content still matches what chuzom wrote (skip + warn otherwise), or (b) at
minimum diff current content against the originally-written text and, if they differ,
strip only the chuzom-authored portion (treat it like a `text_block` from the start,
recording the exact written text as `block` instead of using the blunt `created_file`
kind) rather than deleting the file outright.

---

## Confirmed CLEAN (checked, no Critical/High/core-Medium finding)

- **RED1-9-02 TOML-table-removal regex** (`install_manifest._remove_toml_table` and the
  textually-identical `commands/install._remove_toml_table_block`) — adversarial harness
  `/tmp/red1-iter10/repro_toml.py`, 4/5 cases pass:
  - adjacent tables with no blank-line separator (the original regression) — removes only
    the target table, leaves the neighbor intact.
  - header-is-a-prefix-of-another-header (`model_providers.chuzom` vs.
    `model_providers.chuzomX`) — does **not** falsely match the longer name.
  - table at EOF with no trailing newline on the last **content** line — removed correctly.
  - a nested/dotted subtable immediately following (`model_providers.chuzom.extra`) is
    preserved, not swallowed.
  - **One non-matching edge case found and deliberately NOT reported**: a table consisting
    of *only* the header line, with no body and no trailing newline at all
    (`'foo = 1\n[model_providers.chuzom]'`, EOF right after `]`) is not removed — the
    regex requires `\n` immediately after the header line. Excluded because (a) chuzom's
    own write path always emits a header + body + trailing newline, so this exact byte
    sequence can only arise from a user manually deleting all table content AND the final
    newline character by hand, and (b) the failure mode is safe — `updated == text`, no
    match, no removal, no corruption — leaving at most one inert, empty, keyless header
    line. No data loss, no crash, requires a contrived manual edit chuzom cannot produce.
- **`_remove_json_key`** — `data.get(root_key)` is guarded with `isinstance(servers, dict)`
  before indexing; a non-dict value under `root_key` degrades to a no-op, not a crash. (A
  non-dict *root* JSON document, e.g. a top-level list, would raise inside
  `_remove_json_key`, but that exception is caught cleanly by `apply_uninstall()`'s normal
  per-record try/except — `rec` itself is a valid dict in that case, so the except
  handler's own `rec.get('path')` succeeds and the loop continues to the next record. This
  is the *correctly-handled* counterpart to RED1-10-01, which is specifically about the
  manifest *record* being malformed, not the target file.)
- **`_remove_text_block` double-occurrence risk** — every `text_block` append site
  (`_append_routing_rules`, the codex `config.yaml` MCP block, the codex `hooks.json`
  merge) is structurally guarded by an `if "chuzom" not in existing` / `if block in y`
  check before appending, so the same block text can never be written twice into the same
  file — `text.replace(block, "", 1)`'s "first occurrence only" semantics can therefore
  never actually leave an indistinguishable duplicate behind in practice.
- **Manifest recording sites capturing a wrong path/block** — `_merge_json_mcp_block`,
  `_append_routing_rules`, and `_copy_hook_script` (the three shared helpers) all call
  `install_manifest.record(...)` using the *same local variables* just used for the write
  (`path`, `root_key`, `server_name`, `block`, `dest`), so a record cannot structurally
  diverge from what was actually written at that call site. Traced all call sites in
  `_install_opencode_files`, `_install_gemini_cli_files`, `_install_codex_gateway_config`,
  and `_install_codex_files` — all correctly recorded via these helpers.
- **`hooks.json` writes with no direct manifest record** (Codex `~/.codex/hooks.json` in
  `_install_codex_files`, and Gemini CLI's
  `~/.gemini/extensions/chuzom/hooks/hooks.json` in `_install_gemini_cli_files`) —
  investigated as a candidate finding; **not reportable**, both are redundantly covered
  today: Codex's `hooks.json` PostToolUse entry is stripped by a hardcoded
  `commands/install.py:802-821` block inside `uninstall_host_integrations()`, and Gemini's
  entire `extensions/chuzom` directory (containing `hooks.json`) is unconditionally
  `rmtree`'d by the same function (`commands/install.py:757-764`) — and
  `uninstall_host_integrations()` runs unconditionally on every `chuzom uninstall`
  regardless of manifest-replay outcome. No live user-facing residue today. (This *is* a
  latent architectural inconsistency — these two writes bypass the manifest's own stated
  guarantee against "silently drifting coverage" and depend on a parallel,
  manually-maintained legacy path staying in sync — but it causes zero current harm and is
  excluded per the "no marginal findings" instruction.)
- **Reservation/envelope leaks in `router.py route_and_call`** — traced every exit path:
  daily-cap raise, empty-chain `ValueError`s, semantic-cache-hit return, cost-escalation
  `BudgetExceededError`s, envelope-reservation-failure raise, pre-dispatch deadline
  expiry, `CancelledError`/`TimeoutError` handlers, the generic `except Exception`
  handler, and the success-return path. Every exit releases `_pending_spend` (and the
  envelope, where applicable) exactly once — either via the shared idempotent
  `_release_reservation_if_held()` helper or a manual duplicate that is safe by
  construction (`release_envelope(None, ...)` is a guarded no-op, confirmed in
  `quota_envelope_routing.py`).
- **`_pending_spend` single-release** — confirmed via the same sweep; no double-decrement
  or leaked-forever path found.
- **Rejected-attempt billing** — RED1-8-01's true-cost accounting
  (`response.cost_usd + response.chain_attempt_cost_usd`) is present and semantically
  correct at the success path.
- **Atomic settle** — `commit_envelope`'s single-transaction settle (undo reservation +
  record real spend) replaces the earlier two-step release+commit; no TOCTOU gap re-found.
- **Frozen `LLMResponse`** — confirmed `@dataclass(frozen=True)` in `types.py`; the
  cap-downgrade annotation path correctly uses `dataclasses.replace()`.
- **`server.py` lifespan drain** — `_lifespan`'s `try/yield/finally: await
  drain_bg_tasks(...)` guarantees background-task drain on every shutdown path.

## Excluded as not independently reportable

- **`record()` non-atomic read-modify-write** (`_load()` → append → `write_text()`, no
  locking/fsync) — a theoretical lost-update race under genuine concurrent-process
  installs. Not repro'd: the CLI's actual `--host all` install loop is sequential within a
  single process, so there is no realistic concurrent-writer scenario in the current
  codebase to demonstrate real user-facing harm. Flagged for awareness only, not as a
  finding.

---

## Summary for orchestrator

**2 findings — both HIGH.**

- RED1-10-01 (HIGH): a single malformed/corrupt manifest record crashes inside
  `apply_uninstall`'s own exception handler, silently aborting the entire uninstall
  replay and orphaning routing-rules files on up to 5 hosts that have no legacy-fallback
  coverage. CONFIRMED.
- RED1-10-02 (HIGH): the `created_file` uninstall kind unconditionally deletes the whole
  file rather than just the chuzom-authored portion, permanently destroying any content a
  user added after install with no backup. CONFIRMED.

Everything else audited (RED1-9-02 TOML regex fix — 4/5 adversarial cases pass, 1 excluded
as unreachable/harmless; `_remove_json_key`; `_remove_text_block` duplicate-occurrence
risk; manifest recording-site path/block fidelity across all bespoke installers; the
hooks.json manifest-coverage gap; and the full router.py/server.py/types.py regression
sweep — reservation/envelope leaks, `_pending_spend` single-release, rejected-attempt
billing, atomic settle, frozen dataclass, lifespan drain) is CLEAN.
