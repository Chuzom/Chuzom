# RED-2 Customer-Reality Audit — Iteration 10

**Target:** commit `92367ce` on `fix/v1.0.1-audit-mitigation`
**Scope:** does the iteration-9 install manifest actually make install→uninstall symmetric? Does the RED2-9-04 banner `is_fallback` fix actually hold? Broader claims-honesty pass.
**Method:** live install/uninstall runs against isolated `HOME`/project dirs (no real user data touched), before/after diffing, and direct empirical driving of the affected code paths. Every CONFIRMED finding below was reproduced this round; nothing is asserted from code-reading alone unless labeled PLAUSIBLE.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 1 |
| High | 2 |
| Medium | 2 |
| Notes (below reporting bar) | 2 |

Not CLEAN. One carried-forward Critical (data loss, scoped this round), one new High (the round's own `is_fallback` fix is incomplete), one carried-forward High (documented fix that doesn't work), two Medium (orphaned backup artifact; a second documented-fix mismatch). Also reporting three genuine CLEAN confirmations achieved this round, since Priority 1/2 explicitly asked for them.

---

## RED2-10-01 — Critical: cross-CWD Trae `.rules` uninstall causes real data loss (carried forward, root-caused and scoped this round)

**Surface:** `src/chuzom/commands/install.py:1104` (`_install_trae_files`, `rules_dest = pathlib.Path(".rules")`) → `src/chuzom/commands/install.py:830-863` (`_append_routing_rules`, records the manifest entry with whatever `dest_path` it's given, no normalization) → `src/chuzom/install_manifest.py:88` (`apply_uninstall`, `path = pathlib.Path(rec["path"])`, no anchoring/resolution of relative paths).

**User-experience vs. truth:** The manifest is pitched as the structural fix that makes uninstall symmetric everywhere ("New surfaces are covered automatically... coverage can no longer silently drift" — `install_manifest.py:1-9`). For Trae specifically, that promise is false in a way that destroys unrelated user data: `chuzom install --host trae` run from directory A writes `$A/.rules` and records `{"kind": "created_file", "path": ".rules"}` — a **bare relative path**, never resolved to an absolute one. If the user later runs `chuzom uninstall` from a *different* directory B that happens to contain the user's own, unrelated `.rules` file, uninstall:
- silently **deletes the user's own `$B/.rules`** (real data loss, not a chuzom artifact), and
- **leaves the actual chuzom-authored `$A/.rules` orphaned** on disk.

**CONFIRMED, reproduced this session (evidence from this iteration, cross-cwd scenario):**
```
$ chuzom install --host trae            # run from $SCRATCH/red2-dirA
✓ Created .rules with routing rules      # writes $SCRATCH/red2-dirA/.rules
# manifest gets: {"kind": "created_file", "path": ".rules"}

$ echo "MY OWN NOTES — do not touch" > $SCRATCH/red2-dirB/.rules   # unrelated user file
$ cd $SCRATCH/red2-dirB && chuzom uninstall
...
$ ls $SCRATCH/red2-dirB/.rules
ls: No such file or directory              # user's own file: gone
$ cat $SCRATCH/red2-dirA/.rules
<chuzom routing-rules content still present>   # chuzom's own file: orphaned, survives
```

**Scoping done this round:** `_append_routing_rules` is shared by 7 host installers (opencode, gemini-cli, copilot-cli, trae, vscode, cursor, openclaw). Read all 7 call sites — **Trae is the only one that passes a bare relative path.** The other 6 all pass paths already anchored absolute at call time: `pathlib.Path.home() / ...` (opencode, gemini-cli, openclaw, cursor) or `pathlib.Path.cwd() / ...` (vscode's `copilot_instructions`, resolved to an absolute path when the installer runs). So this is a real, live, reproducible data-loss bug — but it is Trae-specific, not a symptom of every manifest-recorded write.

**Fix:** in `_install_trae_files()`, build `rules_dest` the same way the other 6 callers do — anchor it, e.g. `rules_dest = pathlib.Path.cwd() / ".rules"` — so the manifest always stores an absolute path. Belt-and-suspenders: `install_manifest.apply_uninstall()` should also resolve/reject non-absolute paths defensively (`if not path.is_absolute(): skip` ), since any future caller of `record()` that forgets to anchor its path reintroduces this exact class of bug.

---

## RED2-10-02 — High: the RED2-9-04 `is_fallback` banner fix only patches 1 of 4 writers of `usage.json` — the banner/mode-line mismatch it claims to close still reproduces

**Surface:** `src/chuzom/hooks/session-start.py:527-532` (the fixed writer) vs. `src/chuzom/tools/subscription.py:73-84` and `src/chuzom/tools/subscription.py:~150-160` (`llm_update_usage` / `llm_refresh_claude_usage` MCP tools) and `src/chuzom/hooks/usage-refresh.py:139-152` (`_oauth_refresh_and_write`, the statusline's periodic background refresh) — **none of these three other successful-refresh writers ever set `is_fallback` on their snapshot.** The read side that the fix depends on, `session-start.py:1096`, is `_cached_sub = not _cached_usage.get("is_fallback", True)` — a missing key silently defaults to "fallback."

**User-experience vs. truth:** RED2-9-04's own comment states the bug was: "a successful subscription refresh was mis-read as a fallback and the banner box showed the wrong mode for every session after the first," and the fix is presented as closing that gap. It does close it **for the one writer it touched.** It does not close it for the product's other three successful-refresh writers, all of which are real, reachable, everyday code paths — `usage-refresh.py`'s background refresh in particular is described in its own docstring as running periodically via the statusline, i.e. it runs automatically without any explicit user action, and will routinely be the *last* writer of `usage.json` before the next session starts.

**CONFIRMED, reproduced this session** by directly exercising the exact read/write functions `session-start.py` uses (isolated `HOME`, no real user files touched):

1. Seeded `~/.chuzom/usage.json` the way `usage-refresh.py`'s `_oauth_refresh_and_write()` actually writes it on a successful refresh — i.e. **no `is_fallback` key at all**:
   ```json
   {"session_pct": 14.0, "weekly_pct": 6.0, "sonnet_pct": 0.0, "highest_pressure": 0.14, "updated_at": 1785436900.0}
   ```
2. Ran `session-start.py`'s actual banner-selection logic (`_cached_sub = not _cached_usage.get("is_fallback", True)` → `_select_banner(_cached_sub)`), then its actual mode-line logic (`_refresh_claude_usage()` → `is_subscription` → `_render_welcome(is_subscription)`), forcing this session's own live refresh to succeed (deterministic stand-in for a real successful OAuth call, isolating the caching bug from network/keychain variance):
   ```
   _cached_sub computed as: False   (should be True — the missing key defaults to "fallback")
   banner IS BANNER_SUBSCRIPTION: False
   is_subscription (mode-line driver): True
   welcome mode line: '   mode    → subscription (Claude OAuth pressure cascade)'
   VERDICT: banner box says subscription = False; mode line says subscription = True
   MISMATCH (bug reproduced)
   ```
3. With no cloud API keys configured (the realistic default), `_resolve_banner(False)` falls through to `BANNER_LOCAL` — the box the user actually sees is:
   ```
   ╔════════════════════════════════════════════════════════════════╗
   ║  ⚡ chuzom ACTIVE — local routing (no cloud keys set)     ║
   ...
   ```
   printed immediately above a welcome block that says `mode → subscription (Claude OAuth pressure cascade)`. This is the identical self-contradicting startup output the RED2-9-04 fix was written to eliminate.
4. As a positive control, confirmed the fix genuinely works for its own writer: seeding `usage.json` with `is_fallback: false` (as `session-start.py`'s own success path now writes) produces `_cached_sub == True`, `BANNER_SUBSCRIPTION` is selected, and it matches the mode line — CONSISTENT. So the round-9 fix is real and correct as far as it goes; it's just incomplete.

**Fix:** add `"is_fallback": False` to the snapshot dicts written on every successful refresh in `src/chuzom/tools/subscription.py` (both write sites, ~line 77 and ~line 154) and in `src/chuzom/hooks/usage-refresh.py`'s `_oauth_refresh_and_write()` (~line 143). Better: factor the four independent "build and write a usage snapshot" call sites into one shared helper (they already duplicate the same 5-key dict shape) so this can't drift again the next time a fifth writer is added.

---

## RED2-10-03 — High (carried forward, not re-tested this round, no code touching it changed since prior confirmation): `chuzom install --host windsurf` is documented as working but is rejected by the CLI

**Surface:** README.md "Get Started (60 seconds)", `docs/troubleshooting.md`, and the CLI's own `--help` text all list `windsurf` as a valid `--host` value for `chuzom install`. Running it: `chuzom install --host windsurf` → `Unknown host(s): windsurf`, exit 0, zero file changes.

**User-experience vs. truth:** a user following the README's own quickstart, or `--help`, for the one host the CLI itself advertises as supported hits a silent no-op with a confusing rejection message instead of the documented setup. (The *actual* Windsurf path is `chuzom-install-hooks ide`, correctly documented separately in `docs/ide-setup.md` — but that doesn't reconcile the primary `chuzom install --host windsurf` claim, which remains false.)

**Status:** CONFIRMED in a prior turn of this same audit session (empirically run: exit 0, "Unknown host(s): windsurf", no files touched). Not re-run this turn since neither `commands/install.py`'s host dispatch nor the README/docs changed between iteration 9 and this commit's diff relevant to this path — carrying forward rather than re-verifying is a deliberate time-budget call, flagged here for transparency rather than silently omitted.

**Fix:** either wire `--host windsurf` through to the same logic `chuzom-install-hooks ide` uses, or fix the README/`--help`/troubleshooting doc to stop claiming `--host windsurf` is a valid value and point users at `chuzom-install-hooks ide` instead.

---

## RED2-10-04 — Medium (carried forward, same basis as above): documented Cursor troubleshooting fix doesn't produce the file it tells you to verify

**Surface:** `docs/troubleshooting.md` "Cursor / Windsurf rules not applying" section recommends running `chuzom install --host cursor` and then verifying via `ls .cursor/rules/use-chuzom.mdc`. But `chuzom install --host cursor` (→ `_install_cursor_files()`) writes to `~/.cursor/rules/chuzom.md` (global, user-home-scoped) — a different file, at a different path, with a different name. The `.cursor/rules/use-chuzom.mdc` path is only created by the separate, project-scoped `install_ide_configs()` function, reachable exclusively via `chuzom-install-hooks` / `chuzom-install-hooks ide`, not via `chuzom install --host cursor`.

**User-experience vs. truth:** a user who hits this exact troubleshooting section, runs the documented fix, then runs the documented verification command, gets `ls: .cursor/rules/use-chuzom.mdc: No such file or directory` even though the fix "worked" (it did create `~/.cursor/rules/chuzom.md`, just not the file the doc checks for). The doc is internally inconsistent about which of the two parallel Cursor-integration code paths it's describing.

**Status:** CONFIRMED in a prior turn via direct reads of `commands/install.py`'s `_install_cursor_files()` vs. `install_ide_configs()` and `docs/troubleshooting.md`'s text. Not re-run this turn (same rationale as RED2-10-03).

**Fix:** make the doc's verification command match whichever mechanism the doc's fix command actually invokes — either change the fix to `chuzom-install-hooks ide` (which does create `.cursor/rules/use-chuzom.mdc`), or change the `ls` check to `~/.cursor/rules/chuzom.md`.

---

## RED2-10-05 — Medium (new this round): `.codex/config.toml.chuzom-bak` is a chuzom-authored file left behind by every uninstall, forever

**Surface:** `src/chuzom/install_manifest.py:150-155` (`_remove_toml_table`) — immediately before rewriting a host's `config.toml` during uninstall, it makes a defensive copy: `shutil.copy2(path, path.with_suffix(path.suffix + ".chuzom-bak"))`. There is no code anywhere in the codebase that ever deletes this `.chuzom-bak` file.

**User-experience vs. truth:** directly answers Priority 1's "does anything chuzom-authored survive uninstall?" — yes. This file is created *by chuzom's own uninstall code, during uninstall itself* (so it can never be pre-recorded in the manifest the way normal install-time writes are), and nothing ever cleans it up. It's a permanent artifact left in the user's `.codex/` directory after every uninstall that touches a TOML-based host config.

**CONFIRMED, reproduced this session:**
```
$ ls $TMP_HOME4/.codex/
config.toml   config.toml.chuzom-bak
$ cat $TMP_HOME4/.codex/config.toml            # correctly cleaned
(empty / no [model_providers.chuzom] table)
$ cat $TMP_HOME4/.codex/config.toml.chuzom-bak  # orphaned pre-uninstall snapshot
[model_providers.chuzom]
name = "Chuzom"
base_url = "http://127.0.0.1:17900/v1"
env_key = "CHUZOM_API_KEY"
wire_api = "responses"
```
(Reproduced via a fresh `--host all` install followed by `chuzom-install-hooks uninstall`, same cwd, isolated `HOME`.)

**Severity note:** capped at Medium rather than High — no secret is leaked (it's an internal loopback URL and an env-var *name*, not a key value), and the live `config.toml` itself is correctly cleaned. But it is real, reproducible, chuzom-authored litter that survives indefinitely, which is exactly what this priority asked to find.

**Fix:** after `apply_uninstall()` finishes successfully, sweep and delete any `*.chuzom-bak` files it created during this run (track their paths in the `actions` list, or just glob `path.with_suffix(path.suffix + ".chuzom-bak")` for each `toml_table` record processed and unlink it once the table removal succeeds).

---

## Notes — below the Critical/High/core-Medium bar, not counted above

- **`.codex/hooks.json` has zero manifest record.** Confirmed static gap (no `install_manifest.record(...)` call anywhere for this file). In the same-cwd install→uninstall scenario this is masked by the legacy `uninstall_host_integrations()` fallback (step 5 of `_run_uninstall()`), which still runs unconditionally as defense-in-depth and does clean it up in that scenario — so it did not produce a surviving artifact in the tests run this round. It's worth fixing as an architectural-honesty item (the manifest's own doc-comment claims coverage can't "silently drift" — this file is proof it already has, just not yet in a way that's caused an observed survivor), but I have not proven cross-cwd or cross-scenario harm from it specifically this round, so it stays a note rather than a numbered finding.
- **Numerous `Library/Caches/com.apple.python/.../*.cpython-39.pyc` files** appear under a fake `HOME` after any run — these are macOS system Python bytecode-cache artifacts from running `/usr/bin/python3` under a `HOME` override, unrelated to chuzom's own logic, and would appear under any real `$HOME` regardless of chuzom. Explicitly not a finding.

---

## Explicit CLEAN confirmations (Priority 1 & 2 — reproduced this round)

1. **Same-cwd `--host all` install → `chuzom uninstall` is genuinely clean.** Fresh isolated `HOME` + project dir, `chuzom install --host all` followed by `chuzom uninstall` from the same directory: zero orphaned `chuzom`-referencing strings found across the tree (grep sweep), `~/.chuzom/install-manifest.json` cleared, `~/.chuzom/` emptied, project dir emptied back to its pre-install state (modulo the harmless `.pyc` cache noise above).

2. **`chuzom-install-hooks uninstall` (Priority 1's explicit ask) is provably equivalent to `chuzom uninstall`, not a separate/incomplete path.** Confirmed two ways: (a) code — `install_hooks.py`'s `main()` `uninstall` subcommand delegates directly to `chuzom.commands.uninstall._run_uninstall(args[1:])`, the exact same function `chuzom uninstall` calls, per an explicit inline "RED2-7-01" fix comment describing this delegation as the fix for a prior round's parallel-uninstall gap; (b) empirically — fresh `--host all` install followed by `chuzom-install-hooks uninstall` (same cwd) leaves no orphaned chuzom references except the new `.codex/config.toml.chuzom-bak` finding above (RED2-10-05) and correctly removes `.rules` in this same-cwd case.

3. **Pre-existing user content is preserved through both install and uninstall (Priority 2).** Tested both manifest record kinds that touch shared config files:
   - JSON-merge case: pre-seeded `~/.gemini/settings.json` with the user's own MCP server entry plus unrelated top-level keys. After `chuzom install --host gemini-cli` then `chuzom uninstall`: the user's own server entry and unrelated keys survive untouched at every step; only the `mcpServers.chuzom` key chuzom added is removed on uninstall.
   - Text-block-append case: pre-seeded `~/.config/opencode/instructions.md` with the user's own text. After `chuzom install --host opencode` then `chuzom uninstall`: the user's original text survives verbatim; chuzom's appended block is cleanly stripped, leaving exactly the original file (not an empty file, since `_remove_text_block` only deletes the file if *nothing* remains after stripping the block).

---

## Method record (for reproducibility)

All tests run against isolated `HOME`/project directories via `HOME=<tmp> python3 <wrapper>`, never against the real user `$HOME`. Wrapper scripts and captured logs live under the session scratchpad (`/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/`), including `test_is_fallback.py` (the script used to reproduce RED2-10-02, importing `session-start.py` directly via `importlib` under a fake `HOME` so `STATE_DIR` resolves into the isolated tree, then exercising the exact `_select_banner`/`_refresh_claude_usage`/`_render_welcome` functions the real hook uses — the one non-deterministic piece, the live OAuth call, is stubbed to a fixed success value so the test isolates the caching logic from keychain/network variance).
