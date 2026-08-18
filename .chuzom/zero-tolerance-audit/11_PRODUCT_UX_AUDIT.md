# 11 — RED-4: Install / Upgrade / Uninstall / Doctor / Cross-Platform Audit

> Track: RED-4. Mandate: install, upgrade, uninstall, doctor, and cross-platform behavior.
> Target: `c2c28821f690f7cbda42b46da06fc36ef77d816e` (tag `v1.1.1`), per `00_AUDIT_BASELINE.md`.
> All source inspection used `<WORKTREE>/.venv-audit/bin/python` against the clean detached
> worktree at `AUDIT-c2c2882`. All command execution used a real, built wheel
> (`pip install` into `/tmp/red4-venv`) invoked with `HOME` redirected to disposable sandbox
> directories (`/tmp/red4-sandbox{1..5}`) — **never** the real `~/.claude`, `~/.claude.json`,
> `~/.chuzom`, or `~/Library/Application Support/Claude`.

## Methodology note / disclosed near-miss

Early in this track, `chuzom verify-enterprise` was run once against `/tmp/red4-venv/bin/chuzom`
**without** a sandboxed `HOME` set, in violation of this track's own safety rule. It completed
(exit 0), made a live network attempt (Ollama classification), and read real environment
variables, but a `find ~ -newermt '-10 minutes'` sweep immediately after (excluding known-safe
paths) showed **no writes to any real config path** — `~/.claude/settings.json`'s mtime was
independently confirmed unchanged (Aug 8, vs. the incident occurring Aug 11). No damage occurred.
Every subsequent invocation in this track was prefixed with an explicit sandboxed `HOME=`. This
near-miss is disclosed here for transparency, per instructions.

Coverage note: sub-items 1–6 below are covered with direct evidence. Sub-item 7 (cross-platform)
is covered for the patterns reachable from `install_hooks.py`/`doctor.py` (subprocess creation,
quoting, path handling) plus the CI matrix analysis; a full line-by-line pass of
`commands/install.py` (1246 LOC), `install_manifest.py`, `onboard.py`, `quickstart.py`,
`hosts/*.py`, and `publish-pypi.yml` was not completed — this is disclosed as a gap, not silently
dropped (see "Not completed" section at the end). Windows and Linux execution (sub-item 7) were
**NOT TESTED** — this machine is macOS only.

---

## Finding RED4-01 — `chuzom install` silently overwrites a user's pre-existing `statusLine`, and `chuzom uninstall` deletes rather than restores it (permanent config data loss)

```
ID: RED4-01
Severity: P0
Confidence: PROVEN
Area: Install / Uninstall — Claude Code settings.json (`statusLine`)
Title: Install clobbers a pre-existing statusLine with no consent/backup; uninstall deletes it outright instead of restoring the original
Claim-Invariant violated: "A router that corrupts a user's Claude Code config is P0" (per this
  audit's own P0 definition) — statusLine is part of `~/.claude/settings.json`, a real,
  user-authored host config value, and it is unconditionally destroyed by both install and
  uninstall.
Observed behavior:
  1. A sandboxed HOME was seeded with a realistic pre-existing settings.json containing a
     custom statusLine the (simulated) user had configured themselves:
     `"statusLine": {"type": "command", "command": "/tmp/red4-sandbox2/.claude/hooks/my-statusline.sh"}`
  2. `chuzom install` ran and printed "Registered statusLine command in settings.json" with no
     warning that a different value already existed. Post-install, `statusLine.command` became
     `"bash <...>/chuzom-statusline.sh"` — the user's original script reference is gone from the
     live config with zero trace in settings.json itself.
  3. `chuzom uninstall` (later, same sandbox) printed "Removed statusLine command from
     ~/.claude/settings.json" and the key was deleted entirely — post-uninstall settings.json
     has **no** `statusLine` key at all. The user's *original* custom statusLine
     (`my-statusline.sh`) is never restored. It is unrecoverable through any chuzom code path.
Expected behavior: A tool that modifies a single-value (non-array, last-writer-wins) field in a
  shared host config file must, at minimum: (a) detect a pre-existing, non-chuzom value and
  either refuse/warn/prompt before overwriting it, or (b) back it up (the codebase already has
  a working pattern for this — see Root cause), and (c) on uninstall, restore the backed-up
  original value rather than deleting the key outright.
Why this matters to a real user: `statusLine` is exactly the kind of small, easy-to-forget,
  hand-rolled customization a real developer sets up once and never thinks about again — a git
  branch/battery/cost display script. Installing a router should never be able to silently
  delete unrelated personal tooling, and it is exactly this kind of "small, silent, permanent"
  loss that erodes trust in an installer that runs with the user's real HOME.
Exact reproduction:
  export HOME=/tmp/red4-sandbox2   # or any disposable sandbox
  mkdir -p "$HOME/.claude"
  cat > "$HOME/.claude/settings.json" <<'EOF'
  {"statusLine": {"type": "command", "command": "/tmp/red4-sandbox2/.claude/hooks/my-statusline.sh"}}
  EOF
  chuzom install     # statusLine.command is now chuzom's own value — original lost
  chuzom uninstall   # statusLine key is deleted entirely — original never comes back
Evidence (file:line, command, output):
  - Root cause: `src/chuzom/install_hooks.py` (install statusLine block, ~lines 925–976):
    ```python
    current_sl = settings3.get("statusLine")
    if not current_sl or current_sl.get("command") != statusline_cmd:
        settings3["statusLine"] = {"type": "command", "command": statusline_cmd}
        _save_settings(settings3)
    ```
    — this branch fires whenever `current_sl` exists but has a *different* command; it
    overwrites unconditionally, with no distinction between "chuzom's own prior value" and
    "a completely unrelated user value."
  - Root cause (uninstall), `src/chuzom/install_hooks.py` (~lines 1046–1064):
    ```python
    current_sl = settings_sl.get("statusLine")
    if isinstance(current_sl, dict) and "chuzom-statusline.sh" in str(current_sl.get("command", "")):
        del settings_sl["statusLine"]
    ```
    — this correctly avoids deleting a value it doesn't own, but has no memory of what the
    *original* value was, so it can only delete, never restore.
  - Raw before/after evidence (copied into this evidence dir):
    - `evidence/red4/sandbox2-settings-BEFORE-preexisting-config.json` — original statusLine =
      `/tmp/red4-sandbox2/.claude/hooks/my-statusline.sh`
    - `evidence/red4/sandbox2-settings-AFTER-install-run1.json` — statusLine now
      `bash <...>/chuzom-statusline.sh`
    - `evidence/red4/sandbox2-uninstall-run1.log`, `sandbox2-uninstall-run2.log` — uninstall
      output; final settings.json (checked live in sandbox) has no `statusLine` key at all.
    - `evidence/red4/install-preexisting-config.log`, `evidence/red4/uninstall-preexisting-config.log`
Root cause: The install path treats `statusLine` as chuzom-owned the moment it decides to write
  it, with no "is this a foreign value I should preserve?" check and no backup step. This is a
  direct architectural asymmetry with how the same file handles JSON corruption (see positive
  finding RED4-05): the codebase clearly has a philosophy of "never destroy user data without a
  recovery path" for *syntactic* corruption, but does not apply that same philosophy to
  *semantic* overwrite of a single known field it doesn't fully own.
Why existing tests missed it: The only CI coverage of `install()` (`smoke-test.yml`, see
  RED4-03) always runs against a **pristine empty tempdir HOME** — there is no test fixture
  anywhere in the repo that seeds a pre-existing, realistic `settings.json` (with a foreign
  `statusLine`, foreign hooks, etc.) before calling `install()`/`uninstall()`. A test that only
  ever installs into an empty directory can never observe an overwrite-of-existing-value bug by
  construction.
Blast radius: Every user who (a) already has a custom `statusLine` configured in Claude Code and
  (b) installs chuzom. Given `statusLine` is a common, documented Claude Code customization point
  (git status, cost tracking, battery, etc.), this is a plausible-to-common intersection, not an
  edge case.
Can this defect class exist elsewhere?: Yes — any other **single-value, non-mergeable** field
  chuzom writes into shared host config is structurally exposed to the same bug. `hooks` arrays
  are additive/mergeable (chuzom appends/removes its own named entries) and are therefore *not*
  in this class. `statusLine` is the one clearly-identified single-value field chuzom writes in
  `~/.claude/settings.json`; a systemic fix should specifically audit all `_save_settings()`
  call sites for any other last-writer-wins key.
Recommended systemic fix: Before overwriting `statusLine`, if a value already exists and its
  command does not reference chuzom's own script, write it to a durable, uninstall-visible
  backup (e.g. `settings3["_chuzom_backup"]["statusLine"] = current_sl`, or reuse the existing
  `.claude/backups/` directory pattern already used elsewhere in this codebase for
  `.claude.json`). On uninstall, if such a backup exists, restore it instead of deleting the key.
  If no backup exists (chuzom owns the current value, or none existed), delete as today.
Regression test that would prevent recurrence: A test that (1) seeds a temp HOME with a
  `settings.json` containing a non-chuzom `statusLine`, (2) calls `install()`, (3) asserts the
  original value is preserved somewhere recoverable, (4) calls `uninstall()`, (5) asserts the
  *original* statusLine value is restored verbatim in the final `settings.json` — not merely
  that the key is absent.
Release blocking? YES
```

---

## Finding RED4-02 — `chuzom doctor` never exercises the live hook→hint→MCP-tool-resolution path; the one script designed to catch this class of bug is unwired

```
ID: RED4-02
Severity: P1
Confidence: PROVEN
Area: Doctor / routing-health verification
Title: `doctor` performs only static/file-existence/JSON-key checks; it cannot detect the exact
  bug class (CHZ-SURF-01) this repo already shipped and fixed once, and the dedicated regression
  guard for it is never invoked by anything
Claim-Invariant violated: A "doctor" command's core promise is "tell me honestly whether routing
  actually works." A doctor that reports "✓ All checks passed. Chuzom is healthy." while the
  live routing path silently 404s on every prompt is a false positive on the single most
  important claim the tool makes.
Observed behavior: Full read of `_run_doctor()` in `src/chuzom/commands/doctor.py` (lines
  598–1043, all 14 checks: Hooks, Hook interpreter paths, Duplicate hook detection, Routing
  rules, Claude Code MCP, Claude Desktop, Ollama, Gateway daemon interpreter drift, Usage data
  freshness, Provider API keys, Provider circuit breakers, claw-code, Version, Quota savings
  posture) shows every check is one of: a file/hook exists on disk, a JSON key is present in
  settings/config, or a simple HTTP ping succeeds. `route_call`/`route_tool` from
  `chuzom.tool_surface` (the exact module that fixed CHZ-SURF-01, imported at the top of
  doctor.py with a `# CHZ-SURF-01` comment) are used **only** to format tool names inside printed
  strings — never called to verify that a hook-emitted tool hint actually resolves against the
  live MCP server's currently-registered tool list under the active tier/slim-mode. Grepping
  `doctor.py` for `tool_surface|slim_mode|unroutable|tool_tiers` outside the import line and the
  print-formatting call sites returns nothing.
Expected behavior: `doctor` should simulate (or actually execute, end-to-end, against a local
  fixture) at least one full routing cycle — prompt → `auto-route.py` hook classification → the
  MCP tool name the hook would emit → confirm that name is registered under the currently active
  tool tier on the running MCP server — and fail loudly if the emitted name is unroutable. This
  is precisely what `scripts/trace_northstar.py` (235 LOC, `--live` mode) was built to do.
Why this matters to a real user: The CHZ-SURF-01 bug class is specifically insidious because it
  is *silent* — the caller pays full model price with no error surfaced to the user, and no
  metric distinguishes "chose not to route" from "tried to route and failed." A doctor command
  that cannot catch a regression of the exact bug this repo already had is not doing the one job
  a doctor command exists to do.
Exact reproduction (source-level, static):
  cd <worktree>
  grep -n "route_call\|route_tool" src/chuzom/commands/doctor.py   # only in print()/f-string formatting
  grep -rn "trace_northstar" src/ .github/ pyproject.toml           # zero references outside the script itself
Evidence (file:line, command, output):
  - `src/chuzom/commands/doctor.py:1-19` — imports `route_call, route_tool  # CHZ-SURF-01` but
    never invokes them for verification, only formatting.
  - `src/chuzom/commands/doctor.py:598-1043` — full body of the 14 checks, all static/HTTP-ping.
  - `scripts/trace_northstar.py:1-26` (docstring) — explicitly designed as the
    prompt→hook→hint→MCP-server→model guard for this bug class.
  - Exhaustive grep across `src/`, `.github/`, `pyproject.toml` confirms `trace_northstar.py` is
    referenced nowhere else — not in CI, not in `doctor`, not in `install`, not in any Makefile.
  - `evidence/red4/sb5-doctor-showing-leaked-daemon.log` — a live `doctor` run that prints
    "✓ All checks passed. Chuzom is healthy." for a HOME that has zero API keys, zero
    subscription mode, and (per RED4-04) is silently reusing an unrelated real daemon process —
    yet the top-line verdict is unqualified "healthy."
Root cause: `doctor` was built as a config/environment linter, not a functional/integration
  tester. The module that could close this gap (`trace_northstar.py`) exists but was never wired
  into the one command whose entire purpose is "tell me if this actually works."
Why existing tests missed it: This isn't a test gap so much as a "doctor" scope gap — no test
  suite exercises `doctor`'s verdict against a deliberately-broken tool-tier/hint mismatch,
  because nothing in `doctor.py` has a code path that *could* detect that mismatch.
Blast radius: Every user who runs `chuzom doctor` to sanity-check their install after an
  upgrade, a tier/slim-mode change, or a provider config change, and trusts a "healthy" verdict.
Can this defect class exist elsewhere?: Yes — any future refactor that renames or re-scopes an
  MCP tool (as CHZ-SURF-01 already did once) will reproduce this exact silent-failure mode, and
  `doctor` will not catch it, by design of what it currently checks.
Recommended systemic fix: Wire `trace_northstar.py`'s core check (or an equivalent lightweight
  in-process call to `route_tool()` against the actual registered tool list of the running/
  importable MCP server) into `doctor` as a mandatory check, not just a standalone script. At
  minimum, add it to CI as `ci.yml` already does for `lint_tool_surface.py` (static AST scan) —
  today only the static lint runs; the dynamic/live guard does not run anywhere.
Regression test that would prevent recurrence: A test that deliberately renames/removes a tool
  registration the router would emit a hint for, then asserts `chuzom doctor`'s exit code and
  printed verdict reflect failure, not "All checks passed."
Release blocking? NO (routing itself was already fixed for the specific v1.1.1 case; this is
  about doctor's inability to catch a *future* recurrence — high value, not release-blocking for
  this tag)
```

---

## Finding RED4-03 — CI's only `install()` smoke test swallows all exceptions and never seeds a pre-existing host config, so it cannot catch RED4-01-class regressions

```
ID: RED4-03
Severity: P2
Confidence: PROVEN
Area: CI / install regression coverage
Title: `smoke-test.yml`'s install-flow step wraps `install()` in a broad `except Exception` that
  always exits 0, and only ever tests a pristine empty tempdir HOME
Claim-Invariant violated: A cross-platform "smoke test" that exercises `install()` should fail
  the build if `install()` crashes or corrupts config — not silently continue either way.
Observed behavior: `.github/workflows/smoke-test.yml`'s install step:
  ```python
  import os, tempfile, sys
  with tempfile.TemporaryDirectory() as tmp:
      os.environ['HOME'] = tmp
      try:
          from chuzom.install_hooks import install
          actions = install()
          print(f'install() returned {len(actions)} actions')
      except Exception as e:
          print(f'install() raised (expected on some platforms): {e}')
  ```
  Any exception raised by `install()` — including ones that are genuine bugs on that OS/Python
  combination — is caught, printed, and the step proceeds/passes regardless. Separately, `tmp`
  is always a brand-new empty directory, so this step can never seed a realistic pre-existing
  `settings.json` (with foreign `statusLine`, foreign hooks, etc.) before calling `install()`.
Expected behavior: The smoke test should assert `install()` does not raise on any tested
  platform (or explicitly allowlist specific known/expected exceptions with a comment, not a
  bare catch-all), and at least one CI job should seed a realistic pre-existing config fixture
  before calling `install()`/`uninstall()` to catch overwrite/data-loss regressions like RED4-01.
Why this matters to a real user: This is the direct, compounding reason RED4-01 (statusLine
  clobbering) could ship — the only automated place that exercises `install()` end-to-end can
  neither detect a crash nor a config-overwrite regression, by construction.
Exact reproduction:
  cat .github/workflows/smoke-test.yml | grep -A10 "from chuzom.install_hooks import install"
Evidence (file:line, command, output): `.github/workflows/smoke-test.yml`, install-flow step
  (see quoted snippet above, read in full during this session).
Root cause: The `except Exception: print(...)` pattern was almost certainly added to tolerate
  genuinely-platform-specific failures (e.g., a missing `bash` on a bare Windows runner) without
  understanding that it also masks real bugs, and no separate "does install() actually behave
  correctly" assertion was ever added alongside the "does it merely not crash" try/except.
Why existing tests missed it: This *is* the existing test; it was written to be lenient rather
  than to assert correctness, so it cannot itself be "missed by a test" — it is the gap.
Blast radius: All future install-path regressions of this shape (crash-on-some-platform,
  overwrite-of-existing-value) ship silently through this specific CI gate.
Can this defect class exist elsewhere?: Check other `except Exception: print(...)`-in-CI patterns
  repo-wide before relying on any other "green CI" signal for install/uninstall correctness.
Recommended systemic fix: Split into two assertions — (1) `install()` must not raise on any
  supported platform (fail the job if it does, do not catch-and-continue); (2) add a second job
  that seeds a pre-existing config fixture and asserts specific fields (e.g. a foreign
  `statusLine`) are either preserved or intentionally, visibly, recoverably backed up.
Regression test that would prevent recurrence: Same as RED4-01's regression test, wired into
  this specific workflow file so it runs on every PR across the full OS/Python/installer matrix,
  not just locally.
Release blocking? NO (contributing/systemic factor behind RED4-01, not independently blocking)
```

---

## Finding RED4-04 — `chuzom doctor`'s "Gateway daemon" health check is a fixed-port, machine-wide singleton that is not scoped to the `HOME` being diagnosed

```
ID: RED4-04
Severity: P2
Confidence: PROVEN
Area: Doctor / cross-environment isolation / architecture
Title: Doctor's interpreter-drift check silently queries and reports on an unrelated, pre-existing
  daemon process from a different install/HOME, breaking the isolation assumption a per-profile
  "doctor" report implies
Claim-Invariant violated: A per-`HOME` diagnostic command ("is *this* install healthy") should
  not silently validate itself against ambient machine state that has nothing to do with the
  install being diagnosed, and should not leak another install's real filesystem paths into a
  report about a different (sandboxed, in this case) install.
Observed behavior: `chuzom doctor`, run with `HOME=/tmp/red4-sandbox5` (a from-scratch sandbox
  whose own `chuzom install` never registered or started any daemon — confirmed by grep, see
  Evidence), printed:
  ```
  Gateway daemon (interpreter drift)
    ✓ daemon Python 3.11.15 matches on-disk venv (/Users/yaliandrona/Projects/Chuzom/.venv/bin/python)
  ```
  `/Users/yaliandrona/Projects/Chuzom` is the **real, unrelated development checkout on this
  machine** (this audit's own subject repo's dev copy) — not anything inside
  `/tmp/red4-sandbox5`. The check queried a hardcoded default `http://127.0.0.1:17900/healthz`
  (only overridable via `CHUZOM_URL`) and got a real answer from a real, already-running
  `python3.11` process (confirmed via `lsof -nP -iTCP:17900 -sTCP:LISTEN`, PID owned by the real
  user), because that daemon is a **machine-wide singleton launchd service**
  (`com.chuzom.gateway`, `src/chuzom/gateway_service.py:19,21`), not something the sandboxed
  `install()` ever created.
Expected behavior: Either (a) the doctor report should make explicit that this specific check is
  machine-scoped, not HOME-scoped (so a user with multiple profiles/HOMEs on one machine isn't
  misled into thinking "healthy" describes the install they just ran), or (b) the daemon's
  identity/lifecycle should itself be HOME-scoped (separate port/socket per HOME) so isolation
  is real, not just assumed.
Why this matters to a real user: On any machine where more than one chuzom-managed HOME exists
  (a shared dev box, a second Claude Code profile, a CI runner reused across projects/audits),
  `doctor` output for one profile is silently influenced by, and reports the file paths of, a
  completely different install. This also means routing/provider circuit-breaker state (also
  fetched from this same daemon by other doctor sections) could be shared across what a user
  believes are isolated installs — a meaningful, undocumented cross-tenant behavior.
Exact reproduction:
  export HOME=/tmp/some-fresh-empty-dir
  <install chuzom from a built wheel, do NOT touch real HOME>
  chuzom doctor | grep -A2 "Gateway daemon"
  # Compare the reported interpreter path against anything inside $HOME — it will not match,
  # and will instead reflect whatever machine-wide daemon is already running on port 17900.
Evidence (file:line, command, output):
  - `src/chuzom/commands/doctor.py:800-878` — full "Gateway daemon" check; note line ~809:
    `os.environ.get("CHUZOM_URL", "http://127.0.0.1:17900")` — fixed default, not derived from
    `Path.home()`.
  - `src/chuzom/gateway_service.py:19,21,81` — `LABEL = "com.chuzom.gateway"`,
    `DEFAULT_PORT = 17900`, LaunchAgent plist path is HOME-scoped for *installation*, but the
    running daemon itself listens on a fixed, unauthenticated localhost port with no HOME
    binding once started.
  - Confirmed no sandboxed `install()` run in this track ever registers/starts this daemon:
    `grep -rn "gateway_service\|install_gateway" src/chuzom/install_hooks.py
    src/chuzom/commands/install.py` → no matches; `grep -i "gateway\|launchd\|daemon\|17900"`
    against every install log captured in this track → no matches.
  - `lsof -nP -iTCP:17900 -sTCP:LISTEN` → one real `python3.11` process, real user, confirming
    this is a pre-existing, ambient, machine-wide service, not something spawned by any sandbox
    test in this track.
  - `evidence/red4/sb5-doctor-showing-leaked-daemon.log` — full doctor output showing the leak.
Root cause: The gateway daemon is architected as a single machine-wide background service
  (reasonable for its stated purpose — a shared local API-compatible endpoint other tools can
  point `OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL` at). `doctor`'s health check for it, however, was
  written as if it were validating "this install's daemon," using a hardcoded default port with
  no HOME-derived disambiguation, and no callout in its own output that this specific check is
  intentionally machine-global rather than HOME-local.
Why existing tests missed it: No test in the repo runs `doctor` against two distinct HOME
  sandboxes on the same machine and diffs the output; the daemon check was presumably only ever
  validated against "my one real machine, my one real daemon," where the leak is invisible
  because there's nothing else for it to conflict with.
Blast radius: Shared/multi-profile machines, CI runners reused across projects, and — as
  demonstrated directly in this audit track — any adversarial/audit sandbox testing performed on
  a machine that already has a real chuzom install running. It also means this audit's own
  "clean-room first run" testing (mandate item 3) is not fully hermetic on this machine for this
  one specific check, which is disclosed here rather than left implicit.
Can this defect class exist elsewhere?: Check whether "Provider circuit breakers" and other
  doctor sections that talk to the same gateway daemon inherit the same non-HOME-scoped leak
  (they read from the same `/healthz`-adjacent daemon state) — not independently re-verified line
  by line in this track; flagged as a likely-same-class follow-up.
Recommended systemic fix: Either document explicitly in `doctor`'s own output that the "Gateway
  daemon" section is machine-global (e.g. prefix with "(machine-wide service, shared across all
  profiles on this host)"), or make the daemon's port/socket path derive from `Path.home()` so
  distinct HOMEs get genuinely distinct daemons.
Regression test that would prevent recurrence: A test harness that runs `doctor` under two
  different `HOME` values on the same machine (one with a running daemon, one without) and
  asserts the second HOME's report does not reference the first HOME's filesystem paths.
Release blocking? NO
```

---

## Finding RED4-05 (positive / contrast finding — no action required, included for completeness)

```
ID: RED4-05
Severity: P3
Confidence: PROVEN
Area: Install / settings.json write safety
Title: Settings writes are atomic and self-healing for syntactic corruption, but this same
  protection was not extended to semantic overwrite (see RED4-01) — documented here as positive
  evidence that the pattern exists and could be reused, not as a new bug
Claim-Invariant violated: None — this is a positive control.
Observed behavior: `_save_settings()` in `src/chuzom/install_hooks.py` (~line 429) writes via a
  temp file + `os.replace()` (atomic on POSIX and Windows), and if the pre-existing
  `settings.json` fails to parse as JSON, it is first copied to a timestamped
  `settings.json.corrupt.<ts>.bak` before being overwritten (tagged `CHZ-PKG-008` in a code
  comment, evidence of a prior audit-driven fix). Separately, the real `claude mcp add`/`claude
  mcp remove` CLI (shelled out to for `.claude.json`, see RED4-06) independently produces its own
  timestamped backups under `~/.claude/backups/.claude.json.backup.<ts>` on every mutation —
  confirmed present in every sandbox in this track that ran a real install (`.claude/backups/`
  contained 1–2 backup files per sandbox after a single install run).
Expected behavior: N/A — this is working as intended and is good practice.
Why this matters to a real user: It demonstrates the team already has, and uses, both an atomic-
  write pattern and a backup-before-overwrite pattern elsewhere in the same file — which is why
  RED4-01's *lack* of an equivalent backup for `statusLine` reads as an oversight/asymmetry
  rather than a fundamentally missing capability; the fix in RED4-01 can reuse this exact
  established pattern.
Exact reproduction: N/A (positive finding).
Evidence (file:line, command, output): `src/chuzom/install_hooks.py:429-~460` (`_save_settings`);
  `evidence/red4/*` sandbox runs show `.claude/backups/.claude.json.backup.*` files created by
  the real `claude` CLI subprocess on every install.
Root cause: N/A.
Why existing tests missed it: N/A.
Blast radius: N/A.
Can this defect class exist elsewhere?: N/A.
Recommended systemic fix: Reuse this exact backup mechanism for `statusLine` (see RED4-01).
Regression test that would prevent recurrence: N/A.
Release blocking? NO
```

---

## Finding RED4-06 — Subprocess calls to the real `claude` CLI use safe list-argv invocation (positive finding)

```
ID: RED4-06
Severity: P3
Confidence: PROVEN
Area: Cross-platform / subprocess safety
Title: `claude mcp add`/`claude mcp remove` shell-outs use list-form argv with no `shell=True`,
  bounded timeouts, and a safe JSON-merge fallback — no shell-injection surface found
Claim-Invariant violated: None — positive/no-finding control, included per the mandate's
  cross-platform subprocess-safety check.
Observed behavior: `_install_claude_code_cli()` / `_uninstall_claude_code_cli()`
  (`src/chuzom/install_hooks.py:642-711`) resolve the `claude` binary via `shutil.which("claude")`
  (correctly PATHEXT-aware on Windows) and invoke it as
  `subprocess.run([claude_bin, "mcp", "add"/"remove", "--scope", "user", "chuzom", ...],
  capture_output=True, text=True, timeout=15/10)` — list-form args, no `shell=True`, bounded
  timeout, broad `except Exception: pass` that falls through to a direct JSON-merge fallback
  (`~/.claude.json` read/patch/write) if the CLI is missing or fails, which keeps headless/Docker/
  CI environments working without the real `claude` binary present.
Expected behavior: N/A — this is the correct pattern.
Exact reproduction: `grep -n "subprocess\.\(run\|call\|Popen\)\|shell=True"
  src/chuzom/install_hooks.py src/chuzom/commands/install.py` — no `shell=True` anywhere; all
  `subprocess.run` calls use list argv.
Evidence (file:line, command, output): `src/chuzom/install_hooks.py:642-711` (read in full this
  session).
Root cause / Why existing tests missed it / Blast radius / Can this defect class exist elsewhere:
  N/A (positive finding).
Recommended systemic fix: None needed here. Note as a caveat: this was only verified for
  `install_hooks.py`; `commands/install.py` (1246 LOC) and `hosts/*.py` were not exhaustively
  re-checked for the same pattern in this track (see "Not completed" below) — recommend the same
  grep be re-run against those files before treating subprocess safety as fully cleared
  repo-wide.
Regression test that would prevent recurrence: A static lint (similar in spirit to
  `lint_tool_surface.py`) that fails CI on any `shell=True` or string-concatenated subprocess
  command anywhere under `src/chuzom/`.
Release blocking? NO
```

---

## Finding RED4-07 — Idempotence confirmed across install / uninstall / `--force` / `--purge` (positive finding)

```
ID: RED4-07
Severity: P3
Confidence: PROVEN
Area: Lifecycle idempotence
Title: Repeated invocation of install, uninstall, `install --force`, and `uninstall --purge`
  produces stable, non-duplicating, non-drifting state
Claim-Invariant violated: None — positive finding.
Observed behavior:
  - `install` run twice in the same sandbox: second run reports "already configured" /
    "already registered" / "already in ~/.claude.json" for every idempotent step; no duplicate
    hook entries, no duplicate MCP server entries.
  - `install --force` run immediately after a fresh `install` in the same sandbox: JSON-normalized
    diff of `settings.json` before/after = empty; diff of `.claude.json` before/after = empty;
    md5 of every hook file before/after = identical (no spurious re-writes / no content drift).
  - `uninstall --purge` in a sandbox where `~/.chuzom` had no files yet: correctly printed
    "`<HOME>/.chuzom` does not exist — nothing to purge" and exited 0 rather than erroring.
  - `uninstall` (non-force, second call after already-uninstalled state, from prior session
    evidence `uninstall-run2.log`) is a clean no-op.
Expected behavior: N/A — this is correct behavior and was actively tested for regressions;
  none found.
Exact reproduction: See `evidence/red4/sb4-install-fresh.log`, `sb4-install-force.log`,
  `sb4-settings-before-force.json`, `sb4-hooks-md5-before.txt` / `sb4-hooks-md5-after.txt`
  (identical), `sb5-install.log`, `sb5-uninstall-purge.log`.
Evidence (file:line, command, output): listed above; all in `evidence/red4/`.
Root cause / Why existing tests missed it / Blast radius / Can this defect class exist elsewhere:
  N/A (positive finding).
Recommended systemic fix: None needed.
Regression test that would prevent recurrence: N/A — recommend keeping this behavior covered by
  a repeat-invocation + JSON-diff test in the permanent suite if one doesn't already exist
  (not confirmed either way in this track).
Release blocking? NO
```

---

## Finding RED4-08 — `uninstall` leaves the shared `chuzom_tool_surface.py` hook-support module behind (minor litter)

```
ID: RED4-08
Severity: P3
Confidence: PROVEN
Area: Uninstall completeness
Title: A full `chuzom uninstall` does not remove `chuzom_tool_surface.py` from `~/.claude/hooks/`
Claim-Invariant violated: "Uninstall FULLY restores/cleans" (mandate #5) — minor violation, not
  data-loss-severity, but a real leftover file after a "Done." uninstall message.
Observed behavior: After a full `chuzom uninstall --purge` in a fresh sandbox, every
  chuzom-prefixed hook file was removed and logged as removed, but `~/.claude/hooks/`
  still contained `chuzom_tool_surface.py` (the shared support module hooks import from),
  which is never mentioned in the uninstall log and is not deleted.
Expected behavior: A full uninstall should remove every file it placed under
  `~/.claude/hooks/`, including shared support modules, once no chuzom-prefixed hook remains
  that depends on it.
Why this matters to a real user: Small — an inert, orphaned `.py` file left in
  `~/.claude/hooks/` after uninstall. Not executed by anything once its callers are gone, but it
  is evidence uninstall is not byte-for-byte complete, and could confuse a user auditing their
  own `~/.claude/hooks/` directory post-uninstall wondering why a chuzom-related file remains.
Exact reproduction:
  export HOME=/tmp/some-sandbox
  chuzom install && chuzom uninstall --purge
  ls "$HOME/.claude/hooks/"   # chuzom_tool_surface.py is still present
Evidence (file:line, command, output): observed directly in `/tmp/red4-sandbox5/.claude/hooks/`
  post-`uninstall --purge`; `evidence/red4/sb5-uninstall-purge.log` (file not mentioned in the
  removal log at all).
Root cause: The uninstall routine's removal list is keyed off the chuzom-prefixed hook files it
  registers in `settings.json`'s `hooks` block; `chuzom_tool_surface.py` is a support import, not
  itself a registered hook entry, so it was never added to the removal list.
Why existing tests missed it: No test asserts `~/.claude/hooks/` is empty (or contains only
  pre-existing non-chuzom files) after a full uninstall — only that specific named hooks are gone.
Blast radius: Every user who fully uninstalls chuzom accumulates one orphaned file in
  `~/.claude/hooks/`. Harmless but not clean.
Can this defect class exist elsewhere?: Worth checking whether any other shared/support files
  copied during install (sidecar scripts, etc.) have the same gap — `start-ollama.sh` and
  `start-pxpipe.sh` were both correctly removed in the observed log, so this appears specific to
  `chuzom_tool_surface.py`.
Recommended systemic fix: Add `chuzom_tool_surface.py` (and any other shared support file placed
  in `~/.claude/hooks/`) to the explicit uninstall removal list.
Regression test that would prevent recurrence: After `install()` + `uninstall()` in a fresh temp
  HOME, assert `~/.claude/hooks/` is empty (or diff-equal to its pre-install state).
Release blocking? NO
```

---

## NOT TESTED (explicit, per the "never convert SUSPICION into fact" rule)

These mandate sub-items were not exercised with direct evidence in this track. Each is marked
`NOT TESTED` rather than guessed at, with the specific risk this leaves open:

- **Windows and Linux execution (mandate #7)** — this machine is macOS-only (Darwin 25.5.0).
  Every command-execution finding above (RED4-01, 03, 04, 07, 08) was only observed on macOS.
  Risk left open: Windows-specific branches exist in the code that were read but not executed —
  e.g. `install_hooks.py`'s statusLine block has an explicit
  `if sys.platform == "win32" and not shutil.which("bash")` branch that skips statusLine
  registration with a message rather than crashing; this was read, not run. Any Windows-only
  path-separator, `chmod`, or line-ending bug is `NOT TESTED — unsafe/impossible to execute on
  this machine`.
- **Degraded environments beyond zero-provider**: a deliberately invalid/bad API key, Ollama
  explicitly stopped/unreachable via a genuinely closed port (only a `CHUZOM_URL` override to a
  closed port was attempted for the auto-route hook, not a full doctor/routing run against it),
  and a missing optional dependency (e.g. `tokenizers` or `opentelemetry` extras deliberately
  uninstalled from the venv) were **NOT TESTED** in this continuation. Risk: unknown whether a
  bad key produces an honest, actionable error or a confusing/silent fallback.
- **`--host` variants**: `--claw-code` and the many other declared host targets referenced in the
  install banner (codex, opencode, gemini-cli, copilot-cli, openclaw, trae, pi, factory, desktop,
  copilot, windsurf, kimi) were **NOT TESTED**. Only the default Claude Code + Claude Desktop path
  was exercised. Risk: unknown whether any of these host-specific install paths have their own
  version of the RED4-01 clobbering bug or their own crash-on-missing-binary gap.
- **Full line-by-line read of `commands/install.py` (1246 LOC), `install_manifest.py`,
  `onboard.py`, `quickstart.py`, `hosts/base.py`, `hosts/cursor.py`, `hosts/gemini_cli.py`, and
  `publish-pypi.yml`** — these were enumerated/partially explored but not exhaustively read in
  this track. Risk: additional single-value-field-clobbering bugs (RED4-01's defect class) or
  additional subprocess-safety issues (RED4-06's class) may exist in these files, unverified
  either way.
- **Python 3.11 vs 3.12/3.13 behavioral parity** — confirmed via CI file reading that
  `smoke-test.yml` matrices Python 3.11–3.13 × pip/uv × 3 OSes, and `ci.yml` separately matrices
  3.11–3.14 on Ubuntu only for one job — but this was not independently re-executed in this
  track; taken as `STRONG EVIDENCE` (CI configuration read directly) rather than `PROVEN` (no
  local re-execution across multiple Python versions was performed here).

---

## Evidence index

All raw logs/JSON referenced above are under
`/Users/yaliandrona/Projects/Chuzom/.chuzom/zero-tolerance-audit/evidence/red4/`:
`install-check-cleanroom.log`, `install-cleanroom.log`, `install-preexisting-config.log`,
`uninstall-preexisting-config.log`, `doctor-noproviders.log`, `auto-route-hook-noproviders.log`,
`sandbox2-settings-BEFORE-preexisting-config.json`, `sandbox2-claudejson-BEFORE-preexisting-config.json`,
`sandbox2-settings-AFTER-install-run1.json`, `sandbox2-claudejson-AFTER-install-run1.json`,
`sandbox2-uninstall-run1.log`, `sandbox2-uninstall-run2.log`,
`sb4-install-fresh.log`, `sb4-install-force.log`, `sb4-settings-before-force.json`,
`sb4-claudejson-before-force.json`, `sb4-hooks-md5-before.txt`, `sb4-hooks-md5-after.txt`,
`sb5-install.log`, `sb5-doctor-showing-leaked-daemon.log`, `sb5-uninstall-purge.log`,
`install-run2-idempotent.log`.
