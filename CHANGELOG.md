# Changelog

## [Unreleased]

_Nothing yet. Add a bullet here in your PR when you change routing behavior or a
user-facing surface, then move it under the next version heading at release time._

## v1.2.0 — 2026-08-17 — Zero-tolerance audit remediation

**Release gate status: G-A/B/C/D PASS · G-E satisfiable · G-F NOT QUALIFIED.**

G-F (mutation coverage) is reported as **not qualified** — not waived, not amended, not
deferred. Mutation coverage improved 0.12 → 0.7387 across ~280 individually verified kills,
but that is a **train/validation figure and not a held-out estimate**: the sealed holdout was
contaminated by the audit's own verification method, which enumerated mutants from generated
source rather than from the train split, and then adapted tests to the resulting survivor
lists. Full account in `.chuzom/zero-tolerance-audit/26_HOLDOUT_CONTAMINATION.md`; gate record
in `29_GF_GATE_RECORD.md`. No claim is made that this release satisfies that gate.

Separately and unaffected: on the held-out **quality** benchmark Chuzom scores **q=4.17 vs
static-chain 4.50 and premium 4.50 — a delta of −0.33. Chuzom is not the champion there.**

### Fixed — user-visible

- **The routing hook no longer discards directives it has already computed.** It called
  `execution_ledger.record_event()` *before* writing its JSON to stdout. A profile measured
  that write at 31.19s of a 36.9s invocation, past Claude Code's 30s budget, so the host
  reported "hook timed out — output discarded" and routing silently did not happen. Output is
  now emitted and flushed first; the accounting row can be late without costing the decision.
- **`coverage.snapshot` no longer discards the whole store on one malformed line.** A JSON
  array or string parses successfully but has no `.get`, and the parse had been hoisted out of
  the `try` — so one `[1,2,3]` line raised past the loop and threw away every line counted
  before it. Downstream this rendered coverage as zero rather than as unknown.
- **`fire_budget_alert` and `_native_notify` are now tested for platform dispatch and binary
  name** — previously `fire_budget_alert` had no test coverage at all, so a broken macOS
  branch would have silently stopped every budget alert.
- A duplicate `'anthropic'` entry in the routing-insert provider allowlist, and `malformed`
  counted but never exposed on `Coverage`.

### Changed — reporting

- **The MODELS panel now states what it covers.** The 14-day mix is built from
  `routing_decisions`, which only `llm_route`/`llm_auto` write — the `llm(task=…)` family does
  not — so it is labelled *"classified routes only"*. When rows exist but none fall in the
  window it now says so, instead of rendering nothing, which read as "no routing happened".
  **Treat savings figures derived from that table as covering one tool, not all traffic**
  (`27_ROUTING_DECISIONS_COVERS_ONE_TOOL.md`).
- `paths.is_isolated()` no longer implies process-wide sandboxing. It certifies that
  `chuzom.paths` honours `CHUZOM_HOME`; 182 sites resolve `~/.chuzom` independently and are
  unaffected by it. The limit is now in its docstring rather than only in an audit document.

### Added — guards

- **CHZ-FO-02**: flags a broad `except` that returns *live data* without recording a
  fail-open. The existing check asked whether a failure was *logged*; the redaction defect
  that shipped unredacted prompts logged impeccably and passed. Landed at zero violations.
- **CHZ-SR-01**: ratchets direct `~/.chuzom` resolutions at 182 so the backlog cannot grow.
- **CHZ-FO-HOOK-SLOW**: the hook records its own phase breakdown when it exceeds 5s, so a
  slow invocation diagnoses itself rather than requiring live investigation.
- The hook version stamp is now enforced by a committed content hash — it had been changed
  twice without a bump, which left Cursor/Windsurf/Codex users (where the auto-sync never
  fires) with no staleness warning at all.

## v1.1.1 — 2026-08-08 — Hotfix: routing hints named tools that were not registered (CHZ-SURF-01)

**Every default install was affected.** `chuzom_slim` has defaulted to `consolidated` since
0.10.0, and under that tier the legacy completion tools are not registered — they are
collapsed behind the unified `llm(task=…)` door. But `hooks/auto-route.py` still emitted the
legacy names. Following a hint as written returned `Error: No such tool available`, after
which the caller silently did the work on the expensive model. **The failure was invisible in
every metric we had**: an unroutable hint and "the model chose not to route" are
indistinguishable in the savings dashboard.

- **Fix (critical): every emitted tool name is resolved against the active tier.** New
  `chuzom.tool_surface` is the single source of truth for what is registered and what to call.
  `llm_code` → `llm(task="code")` under `consolidated`, unchanged under `off`. The `task`
  discriminator is preserved — collapsing to a bare `llm` would be callable but would throw
  away the specialization the classifier just chose.
- **The breakage was never consolidated-only.** Each tier hides a different subset while the
  emitters hardcoded one vocabulary: `core` left 4 of 7 route targets unregistered, `routing`
  1 of 7, `consolidated` 5 of 7. Resolution is now tier-aware with capability-ordered
  fallback, so every tier resolves every emittable tool.
- **13 emitters fixed, not 2.** Beyond `auto-route.py`: `enforce-route.py`, `agent-route.py`,
  `subagent-start.py` (taught subagents the wrong names), `agent-error.py`, `session-start.py`
  (the banner injected at session start, which teaches the model for the whole session),
  `status-bar.py`, `usage-refresh.py`, plus user-facing CLI output in `install.py`,
  `doctor.py`, `gain.py`, `router.py`, and the **generated** Cursor / VS Code / Windsurf /
  Copilot rules files, which persist a wrong name for as long as the file exists.
- **Fix: the arguments were wrong too.** The `llm` door takes `tier=fast|balanced|best`; the
  legacy tools take `complexity=simple|moderate|complex`. Renaming a tool without translating
  its arguments only swaps "no such tool" for "unexpected keyword argument". Also dropped
  `profile=` from `agent-route.py`'s suggested call — not a parameter of any completion tool
  on any tier, so that call had never been valid.
- **Guard: `scripts/lint_tool_surface.py`, wired into CI.** Fails the build when a tool name
  is embedded unresolved in an emitted string, or when `route_tool(...)` is followed by an
  argument list (building the uncallable `llm(task="code")(prompt=…)`). It also flags
  interpolation of the logical `tool`/`expected_tool` variables — the variant that survived
  the first pass of this fix, because `{tool:32}` inside an ASCII box contains no tool name in
  the source at all. Internal uses (log records, telemetry, hash keys) carry an explicit
  `# chz-surface-ok: <reason>` pragma.
- **Guard: `scripts/trace_northstar.py`.** End-to-end trace that runs the real hook, extracts
  the tool the caller is told to call, and checks it against the MCP server's **actual**
  registered tool list — deliberately not against `tool_surface` itself, since the bug lived
  precisely in the seam between the hook's idea of the surface and the server's. With
  `--live --fresh` it invokes the tool and reports which model answered.
- **Guard: the lint reaches outside Python.** The CI smoke test asserted
  `'llm_research' in ctx` and stayed green while the emitted hint was unroutable — the test
  was encoding the bug, the worst possible place for it to hide, and an AST scan cannot see
  YAML. The lint now also scans `.github/workflows/*.yml` and `scripts/*.sh` for tool names
  in assertions or printed output. It found three more in `scripts/install.sh`, whose
  post-install "Available tools" list named five tools the default tier does not register.
- **Guard: the lint is version-independent.** Its first version anchored `chz-surface-ok`
  pragmas to line PROXIMITY, which passed on 3.11 and failed on 3.12+: PEP 701 gives
  f-string literal parts their real line numbers, where 3.11 had them inherit the enclosing
  node's. It looked clean locally and broke CI on three interpreters. Pragmas now anchor to
  the enclosing statement, whose position is stable, and a test pins the property.
- **Guard: startup self-check.** The server logs `tool_surface_unroutable` at boot if any
  emittable name fails to resolve under the active tier.
- **Also fixed:** `enforce-route.py` kept a private 6-entry copy of the legacy→door map — the
  reason the knowledge never reached the hook that emits hints. Removed; one definition now.
  Matching uses `door_name()` (never degrades) while display uses `resolve()` (may degrade),
  so a correct call is never recorded as a violation.
- **Fix: the installed rules files taught the wrong names too — in every session.**
  All 13 `src/chuzom/rules/*.md` (installed to `~/.claude/rules/` and the per-host
  equivalents) documented `llm_query` / `llm_analyze` / `llm_code` / `llm_research` /
  `llm_generate`, including a task→tool mapping table. That file is loaded into every
  session, so it was the single strongest teacher of a vocabulary the default tier does not
  register. Rules are now localized at install/refresh time, and drift detection compares
  against the localized text so `off` installs stay byte-identical to the bundle. `localize()`
  rewrites whole call expressions — a name-only rewrite would have produced the uncallable
  `llm(task="code")(complexity="complex")`, which is exactly the failure the new lint exists
  to catch.
- **Fix: routed calls were also going UNCOUNTED (same root cause, measurement side).**
  `usage-refresh.py` gated on `tool_name.startswith("llm_")`. Under the default tier the
  completion door is named exactly `llm`, which fails that test — so every routed call was
  dropped before reaching the savings log. The undercount is indistinguishable from "nothing
  was routed", the same blind spot as the hint bug. The gate now accepts the doors, strips
  MCP qualification (`mcp__chuzom__llm`), and records `task_type="routed"` for the door rather
  than inventing a task the name does not carry. The observability doors
  (`chuzom_status`/`chuzom_admin`/`chuzom_session`) are added to the skip list, so checking
  your savings can never increase your savings.
- **Install:** `tool_surface.py` is now copied beside the hooks as `chuzom_tool_surface.py`,
  so a hook running under an interpreter without `chuzom` importable can still resolve names.

## v1.1.0 — 2026-08-01 — Honest realized-savings measurement + security/correctness hardening

Independently audited across multiple adversarial review passes. No breaking API changes.

- **Realized-savings ledger (measured, not claimed).** New `execution_events` accounting
  computes `net_realized_savings_usd` (gross − classifier − failed-attempt − hook overhead) and,
  for subscription hosts, `realized_quota_tokens_saved` ("Claude tokens not consumed"). Savings
  are counted **only** for verified-adopted routes; a corroborating `content_match` stays
  "likely", never "realized". A `chuzom soak --runs N` harness reports a **conservative floor
  across N runs** (never a single-run point estimate). New `Docs/audit/…` + `Docs/design/VNEXT.md`
  document the honest scope: today the meter reads a small, defensible positive number; a
  production `route_id` reconciliation now makes live `chuzom summary` attribute realized savings.
- **Security / correctness hardening (audit closure).** Plaintext-secret-at-rest sinks now
  redact + `0600` + TTL-purge; budget-envelope races (cap breach, double-decrement, atomic settle,
  single release), cross-process concurrency, and a shared-finalization double-spend/ledger-
  corruption bug are fixed; dashboard unauth token leak (SEC-05), loopback CSRF/DNS-rebind guard
  (SEC-04), and aiosqlite hang-at-exit (PY-004) resolved. Install/uninstall manifest hardened.
- **Claude Code conformance.** PreToolUse blocks now emit the current
  `hookSpecificOutput.permissionDecision:"deny"` alongside the legacy field (no longer reliant on a
  deprecated shim); UserPromptSubmit context uses the documented `additionalContext`.
- **Honesty.** Removed unmeasured marketing claims; enforcement-mode messaging (smart/hard/strict
  banners + labels) corrected to describe what is actually held vs allowed.
- **Chore.** `requires-python >=3.11` smoke matrix aligned; ruff lint clean.

## v1.0.1 — 2026-07-29 — Hotfix: MCP server dead-on-arrival on fresh install (CHZ-PKG-003)

- **Fix (critical): pin `mcp>=1.0.0,<2`.** The unbounded `mcp>=1.0.0` resolved to `mcp==2.0.0`
  on any fresh `pip`/`uv pip`/`pipx` install, which removed `mcp.server.fastmcp`, crashing
  `chuzom.server` at import. The maintainer `uv.lock` (pinned `mcp==1.26.0`) hid this from every
  dev/CI environment. Reproduced and verified by fresh-resolver A/B test: old constraint →
  `mcp 2.0.0` → `ModuleNotFoundError: mcp.server.fastmcp`; new constraint → `mcp 1.29.0` →
  import OK. **1.0.0 should be yanked from PyPI.**
- **Fix (critical): command injection in `statusline-command.sh` (CHZ-SEC-07).** Hook fields
  (`transcript_path`, usage numbers, paths) were interpolated unescaped into `python3 -c`
  source, so a crafted filename executed arbitrary commands on every status-line render. All
  dynamic values now pass through the environment into single-quoted Python source; bash no
  longer interpolates data into code. Regression tests: `tests/test_sec07_statusline_injection.py`
  (behavioral PoC + structural guard against any double-quoted `python3 -c` block).
- **Fix (critical): the routing latch (CHZ-EXT-201).** `_is_short_code_followup` inherited the
  `code` classification for *every* ≤15-word prompt after a code turn — sweeping in
  self-contained questions, disabling direct execution, and pinning `last_route` to `code`
  permanently (measured 2.32% sustained external execution; 0% from per-session turn 10).
  Inheritance now requires a real follow-up signal (anaphora/deixis, a definite reference to a
  code artifact, an inherently-referential verb, or a discourse-marker prefix); self-contained
  prompts fall through to fresh classification, route, and save a non-code `task_type`, so the
  latch cannot accumulate. Regression: `tests/test_ext201_routing_latch.py` — labeled corpus +
  end-to-end `[code] + [self-contained]×12` proving 0/12 inherit (was 0/13 routed).
- **Fix: realization telemetry (CHZ-EXT-204).** The honor path now writes a `verified_used`
  `execution_events` row (enforce-route.py `_record_realization_used`), matching the existing
  `verified_overridden` write on the plain-text-override path. Previously every row had
  NULL `realization_status`/`used_by_host`/`accepted`, so the product could not measure its own
  bypass rate. Regression: `tests/test_ext204_realization_telemetry.py` proves a mixed run has
  0 NULL-realization rows and a computable bypass rate. Related banner over-reporting
  (CHZ-EXT-209) is substantially mitigated by the latch fix, which removes the phantom
  `code-context-inherit` turns that displayed a model name for a call that never happened.
- **Fix: `chuzom verify` exit code (CHZ-PKG-005).** `cli.py` discarded `verify.main()`'s return
  value, so a broken install always exited 0. Now `sys.exit(_verify_main(...))`; a broken
  install exits 1 (verified). _Deferred:_ a real end-to-end canary route inside `verify`
  (CHZ-PKG-010) — tracked for a follow-up.
- **Fix (critical): cross-project semantic-cache leak (CHZ-ST-004).** `semantic_cache` had no
  project column, so a query in project B could return project A's cached response (observed at
  similarity 1.000). Entries are now scoped by a project hash (cwd / `CHUZOM_PROJECT_DIR`), with
  an idempotent column migration; legacy rows age out via TTL. Regression:
  `tests/test_st004_semantic_cache_project_scope.py` — identical-embedding query in a different
  project MISSES; same project still HITS.
- **Fix (critical): fail-open on read-only `~/.chuzom` (CHZ-ST-003).** A module-level
  `PolicyManager` mkdir'd `~/.chuzom/policies` at hook import; a read-only state dir raised
  PermissionError and crashed the hook (exit 1). `_ensure_policy_dir` now fails open, and the
  hook entrypoint wraps `main()` to exit 0 on any unexpected error. Verified: read-only dir →
  exit 0, no traceback; healthy dir still routes.
- **Fix: session_id path traversal (CHZ-ST-001/CHZ-SEC-08).** Per-session state files
  (`last_route_`, `pending_route_`, `transcript_`, `session_`, `violations_`,
  `last_classification_`) interpolated the raw session_id into a `~/.chuzom` path, so
  `../../tmp/evil` escaped the state dir. All sinks now run `_safe_sid` (mirrors
  `session_store._sanitize`: keep `[A-Za-z0-9._-]`, map `/`→`_`). Regression:
  `tests/test_st001_st003_isolation_failopen.py`.
- **Fix: one shared secret scrubber (CHZ-SEC-01/02/09, ST-006).** `secret_scrubber.scrub_text`
  is now the single superset (merged the GitHub-token, `UPPER_KEY=value` and PEM patterns from
  the drifted `session_store` scrubber). `transcript_*.jsonl` is scrubbed and written 0600 (was
  full prompt+response at 0644); the `pending_route` prompt is scrubbed (ST-006); `session_store`
  delegates to the canonical scrubber (its `password:` drift is closed). Regression:
  `tests/test_sec01_shared_scrubber.py` — 8-secret battery, 0 unredacted, transcript 0600.
- **Fix: SSRF via `CHUZOM_OLLAMA_URL` (CHZ-SEC-06).** `validate_ollama_url` (also a pydantic
  field validator on `ollama_base_url`) rejects non-`http(s)` schemes (`file://`, `gopher://`)
  and cloud-metadata / link-local / unspecified hosts before any `urlopen`. Regression:
  `tests/test_sec06_ollama_url_ssrf.py`.
- **Fix: env leak to child CLIs (CHZ-SEC-03).** `get_safe_env`'s blocklist missed
  `AWS_ACCESS_KEY_ID`, `GH_PAT`, `DATABASE_URL`; broadened to the credential classes
  (`AWS_*`, `*ACCESS_KEY*`, `*_PAT`, `*DATABASE_URL`, `*_DSN`, `*CONNECTION_STRING*`, …).
  Regression: `tests/test_sec03_env_allowlist.py`. _Deferred:_ local-HTTP-server auth
  (CHZ-SEC-04) and the dashboard token on the unauth index (CHZ-SEC-05) — server-hardening
  tracked for a follow-up.
- **Fix: `requires-python = ">=3.11"` (CHZ-PY-001/002).** The code uses `asyncio.timeout()`
  (classifier.py, ensemble.py) and `import tomllib` unguarded — both 3.11+ — so `>=3.10` was
  false. Floor raised, the 3.10 classifier dropped, `ruff target-version = py311`, and CI now
  also runs 3.12 (previously omitted). Regression: `tests/test_pkg_python_and_install.py`.
- **Fix: `chuzom install --help` is inert (CHZ-PKG-007).** It fell through to a real install
  (file modifications); now it prints usage and exits 0 with no changes.
- **Fix: back up a malformed `settings.json` before overwriting (CHZ-PKG-008).** `_load_settings`
  silently returned `{}` on a parse error, so a user-authored-but-malformed file was overwritten
  and lost. `_save_settings` now copies an unparseable file to `settings.json.corrupt.<ts>.bak`
  first and writes atomically. Regression tests included.
- **Docs: reworded overstated claims (CHZ-AUD-010).** The PyPI description and README hero no
  longer assert unbacked magnitudes ("3× longer sessions", "60–90%") or unqualified absolutes
  ("every prompt flows", "no cloud"); push (Claude Code, hook-intercepted) vs pull
  (Cursor/Copilot, best-effort) is stated, and the cloud-provider data-flow caveat is explicit.
  Guard: `tests/test_claims_no_fabricated_magnitudes.py`. _Deferred:_ wiring `routing.yaml`
  `daily_caps` into `route_and_call` (CHZ-TQ-007, needs spend-ledger integration), the single
  provider-name enum (CHZ-PRV-01/02), and the aiosqlite daemon-thread fix at the remaining 5
  call sites (CHZ-PY-004) — tracked for a follow-up.
- **CI: permanent recurrence gates (G1/G4/G5/G6).** G1 — `publish-pypi.yml` now installs the
  built wheel into a clean venv with **fresh dependency resolution (no lockfile)** and starts the
  MCP server / lists its tools before publishing (the exact check whose absence let CHZ-PKG-003
  ship); proven locally: fresh install → `mcp 1.29` → 11 tools. G4 — a test-hygiene ratchet
  (`scripts/quality_gate_test_hygiene.sh`) fails if new can't-fail (`except: pass`) tests are
  added above the frozen baseline (33). G5 — a dedicated `quality-gates` CI job runs the full
  audit regression suite for the six fixed criticals. G6 — the fabricated-claims guard runs in
  CI. _Deferred:_ G2 (multi-turn canary soak) and G3 (telemetry-completeness in CI) require
  vendoring the fake-provider harness into the repo. **G2 now shipped** — see below.
- **CI: G2 multi-turn soak gate (CHZ-EXT-201).** `tests/test_g2_soak_no_decay.py` drives the real
  hook across 4 sessions × 15 turns, interleaving code edits with self-contained questions, and
  asserts self-contained prompts are routed *fresh* (never inherit `code`) at every turn position
  including turn 10+ — the historically-dead zone. Runs in the `quality-gates` CI job (~8s). This
  is the gate a single-turn test structurally cannot be.
- **CI: G3 realization-telemetry gate (CHZ-EXT-204).** `tests/test_g3_realization_soak.py` drives
  the *real* hooks — `enforce-route.py` on a routed tool call (honor → `verified_used`) and
  `stop-enforce.py` on a plain-text turn (override → `verified_overridden`) — and asserts the
  `execution_events` ledger has zero NULL realization rows, a computable bypass rate, and a
  session_id on every row. Runs in the `quality-gates` CI job.
- **Fix: aiosqlite hang-at-exit at all call sites (CHZ-PY-004).** The daemon-thread fix reached
  only 1 of the `aiosqlite.connect()` sites; a dropped connection at loop shutdown left a
  non-daemon worker keeping the interpreter alive. Extracted the marker to a single shared
  `chuzom/aiosqlite_util.mark_worker_daemon` and applied it — crucially *before* the connection
  is awaited (marking a started worker is a no-op) — at every site (budget, provider_budget,
  receipt_store, quota_tracker, litellm_budget ×2); `cost.py` delegates to the shared helper.
  Regression: `tests/test_py004_aiosqlite_daemon.py` — mechanism (daemon set before await) +
  a subprocess that drops a connection and must exit cleanly within 15s.
- **Fix: dashboard token leak on the unauth index (CHZ-SEC-05).** `auth_middleware` exempted
  `/` from auth, and the index injects the dashboard token into the page — so any
  unauthenticated request to the port received the token and could then call every API. The
  exemption is removed (token compared with `secrets.compare_digest`); the launcher already logs
  the tokenized URL, so a legitimate user still gets in and an unauthenticated `GET /` now
  returns 401 with no token. Regression: `tests/test_sec05_dashboard_token.py` (live server on a
  random port).
- **Fix: CSRF / DNS-rebinding guard on the loopback model-call servers (CHZ-SEC-04).** Every POST
  to `route_server` (127.0.0.1:7338) and the `gateway` (127.0.0.1:17900) can trigger a real,
  possibly paid, model call, but there was no defense against a browser reaching them via CSRF or
  DNS-rebinding. A single shared `route_server.is_forbidden_cross_origin` (also used by a FastAPI
  middleware on the gateway) rejects requests whose `Host` is not loopback (defeats rebinding —
  the browser still sends `Host: attacker.com`) or that carry a cross-site `Origin`/`Referer`.
  CLI/SDK clients (`OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL`) send a loopback Host and no browser
  Origin, so they are unaffected; operators fronting the server behind a proxy can allow their
  host via `CHUZOM_ALLOWED_HOSTS`. Regression: `tests/test_sec04_local_server_origin_guard.py`.

- **Change: daily spend caps DOWNGRADE to free-local instead of hard-blocking (CHZ-TQ-007).**
  routing.yaml `daily_caps` + org-policy `task_caps` were already wired (they blocked); they now
  follow the signed-off graceful behavior: an exceeded daily cap drops paid providers and routes
  to free-local (Ollama/Codex/Gemini-CLI) at $0. If no free-local provider is available, enforce
  mode decides — `hard` blocks, `smart`/`soft` fall through to Claude. Caps apply whenever
  configured, independent of enforce mode (enforce mode only governs the no-free branch). The
  monthly budget remains a hard block. Rewrote the stale `_BUG` test (which passed for the wrong
  reason — it patched the config object but never `effective_config`, masking that caps were
  wired) into a correct positive test. Regression: `tests/test_tq007_daily_cap_downgrade.py`
  (downgrade / hard-block / smart-fallthrough / no-cap / total-cap) + updated
  `tests/audit/test_policy_switching.py`.

## v1.0.0 — 2026-07-28 — First stable release: measured, independently audited routing — non-breaking

The 1.0 milestone. Routing quality and cost savings are no longer *assumed* — they are
**measured by a real control-group benchmark and certified by a formal two-consecutive-audit
process** (verdict: **RELEASE QUALIFIED** on frozen commit `7c6fdaa`). All 20 release gates
pass. **Non-breaking** — every new routing behavior is additive or default-off, so a fresh
install routes exactly as the audited baseline.

### Highlights

- **Audited savings.** Strict full-metering control-group A/B (Chuzom vs. always-GPT-4o):
  net **+$0.027** per run at quality delta **−0.21** (within the 0.5 non-inferiority margin),
  **0 exhaustions**, robust across 4 independent runs. This is the first release where a
  public savings claim is evidence-backed (Gate-14 claim-evidence registry + CI validator).

### Added

- **Precision-tier routing.** Short prompts demanding an exact, verifiable answer
  (arithmetic / code-output / precise count) are fronted to a reliable cheap metered model
  (`gpt-4o-mini`, ~$0.0003) — the one regime where cheap-local-first returns confident-but-
  **wrong** terse answers the runtime quality heuristic cannot detect. This fixed the
  quality gate's run-to-run non-robustness.
- **Control-group benchmark harness + savings verdict.** `bench/` runs Chuzom against a fixed
  premium control over a prompt corpus (objective + judge grading) and emits the Gate
  15/16/17 verdict via `evaluate_savings`. Wired to the real `chuzom.router` (the v0.0.1 stub
  is retired).
- **`CHUZOM_BLOCK_PROVIDERS`** — a hard provider block on *every* routing path (base chain,
  injection, broker), distinct from the subprocess-only `CHUZOM_DISABLE_SUBPROCESS_BACKENDS`
  so the gateway daemon keeps its free broker path.
- **Metered mid-tier + embedding chain hygiene** — `gpt-4o-mini → gpt-4o` injected before o3
  for premium/reasoning escalations; embedding-only models filtered out of generation chains
  (both the discovery write and read paths).
- **Real-token session baseline.** `summary.py` prices its "what if premium did every row"
  counterfactual from the recorded `input_tokens`/`output_tokens` when present, falling back
  to the latency proxy only for token-less rows (counted in `baseline_estimated_rows`) — no
  estimate is ever presented as a measured total.
- **Opt-in dynamic leaderboard chain ordering** (`CHUZOM_DYNAMIC_LEADERBOARD_ORDERING`,
  **default off**) — aligns the dynamic routing table with the static path's
  cheapest-capable-first leaderboard ordering. BUDGET chains are never reordered.
- **Release-scale corpus** — +24 objective-heavy prompts (`moderate2` / `hard2`) for tighter
  quality confidence, kept as separate corpora so the audited 33-prompt baseline stays
  reproducible.
- **Two-consecutive-audit runbook + `scripts/audit_check.sh`** — the mechanical, un-fudgeable
  baseline half of a release audit pass.
- **Lean, badge-rich README** + a `Docs/` reference split (ide-setup, routing, configuration,
  troubleshooting, session-dashboard, local-inference, okf).

### Fixed

- **Enforcement → tool-capable door (GAP-ENF-1..4).** Execution/repo work of any task_type
  now routes to the tool-capable `llm_act` door (never a text-only door that dead-ended the
  moment it reached Bash); context-dependent execution is provisioned with repo state;
  escalation is a first-class ledger event; the high-precision execution signal is honored
  regardless of classifier wobble.
- **Coordination `LOCAL_BASH` → `llm_act` redirect.** A substantial coordination execution
  task's local command no longer soft-exempts to native and silently defeats the redirect;
  trivial one-liners still run native (the cheapest capable executor).
- **Honest accounting & dashboards.** One definition of "saved" (gross vs. realized, labelled),
  no double-counted Codex, no fabricated tokens, explicit per-panel time-window labels, the
  canonical price on every surface, and realization-gated savings (an unknown realization is
  never counted as realized).
- **Lever ① — exhaustion floor + prose-aware quality gate.** Stopped discarding valid answers
  (9 benchmark exhaustions → 0).
- **Flaky-test cleanup.** The aiosqlite `database is locked` Hypothesis flake (trimmed example
  count + raised busy-timeout), the RC-0 registry-probe flake, and quarantined perf tests —
  CI is now deterministically green.
- **README enforce-default consistency** — documented as `smart`, matching
  `enforce_config.DEFAULT_ENFORCE` (was contradictorily shown as `advise` in one place).

### Verified

- **Gate 13 mutation bar** closed on the honest, redefined standard (`gates.py` 253/255 killed;
  every survivor an individually-registered equivalent). **Gates 18/19** — realization
  derivation and additive-schema migration are tested. The two consecutive clean audit passes
  are recorded in `Docs/correctness-reset/11_AUDIT_RUNBOOK.md`.

### Notes

- **Non-breaking.** All new routing behavior is additive or default-off; a fresh install
  matches the audited baseline. `CHUZOM_DYNAMIC_LEADERBOARD_ORDERING` stays **off** by default —
  turning it on as the shipped default is a post-1.0 change gated on its own re-audit.
- **Changelog discipline going forward:** an `## [Unreleased]` section is now maintained at the
  top of this file. Every behavior- or surface-changing PR should append a bullet there as it
  merges, so the one-big-catch-up gap that preceded 1.0 does not recur.

## v0.10.1 — 2026-07-25 — North Star routing quality (measured, not assumed) — non-breaking

Implements the "North Star" remediation: route to the cheapest **capable** model and
**measure** it honestly. **Non-breaking** — every new behavior ships **default-off /
shadow mode**, so routing is unchanged on a fresh install. Opt in per feature.

### Added

- **Honest v2 route-quality ledger.** Completion routes are now recorded (previously only
  agentic/delegate was measured). The new `RouteLedgerRecord` (`schema_version=2`) keeps
  distinct concepts distinct: *route success ≠ verified quality ≠ tool execution*. A
  technical fallback (timeout / rate-limit / health / budget / cost) records
  `mis_route=None`; only capability/verification/quality failures set `mis_route=True`.
  Unverified completion routes record `verification_passed=None` — never a faked pass.
  `summarize()` reports split metrics (no blended `completion_rate`; verified vs.
  unverified; `verification_pass_rate` over attempted-only; `unknown_quality_completion_rate`).
  Delegations are counted once (aggregate-delegation-only, no double-count). Legacy v1
  rows still load and never pollute v2 metrics.
- **Capability-aware classification.** A new single shared predicate
  (`chuzom.capabilities.detect_capabilities`) emits an 8-bit capability vector used for
  exemption / routing / provisioning / permissions, plus bounded, **safe** relevant-context
  collection (path-traversal, symlink, and secret rejection). Opt in with
  `CHUZOM_CAPABILITY_ROUTING=1`; the default keeps the prior routing behavior.
- **`bounded_operational` route.** A *simple* task that genuinely needs to write a file or
  run a command routes to a bounded, single-milestone, pricing-budgeted, **mandatorily
  verified** tool path instead of an untoolable completion. Opt in with
  `CHUZOM_BOUNDED_OPERATIONAL=1` (default off).

### Fixed

- **`block_providers` honored for the auto-selected agentic model.** A dynamically
  auto-selected agentic model no longer bypasses a user's `.chuzom.yml` `block_providers`
  list (it previously re-injected a blocked provider at the front of the chain). Explicit
  env/repo agentic pins remain exempt; a structured `policy_rejection` event is logged.
- **Real `failed_attempt_cost_usd` metering.** The route ledger records the billable cost
  of a rejected attempt (folded into `actual_cost_usd`, no double-count) instead of a
  `0.0` placeholder.

### Notes

- Verified end-to-end on the real agent harness (real executor writes a file on disk,
  verified by an objective check); a live-model E2E test is included and runs opt-in via
  `CHUZOM_LIVE_OLLAMA=1`.

## v0.10.0 — 2026-07-25 — Consolidated tool surface (1.0 cutover) — **BREAKING**

The MCP tool surface collapses from ~73 tools to **11 front doors**, and the
consolidated surface becomes the **default** (`CHUZOM_SLIM=consolidated`). This is the
1.0-direction cutover: one obvious door per capability, and ~8,000 fewer schema tokens
injected per session (better routing accuracy in long sessions).

### The 11 doors

| Door | Replaces |
|---|---|
| `llm` | `llm_query` / `llm_analyze` / `llm_code` / `llm_research` / `llm_generate` (select via `task=`, `tier=`) |
| `llm_act` | `llm_delegate` (agentic execution) |
| `chuzom_status` | `llm_savings` / `session_savings` / `session_spend` / `usage` / `health` / `providers` / `gain` (select via `view=`) |
| `chuzom_admin` | `llm_set_profile` / `import_profile` / `cache_clear` / `policy` / `budget` (select via `action=`) |
| `chuzom_session` | `chuzom_agent_list` / `check_budget` / `complete_session` / `lineage` (select via `action=`) |
| `llm_route`, `llm_image`, `llm_audio`, `llm_edit`, `chuzom_agent_start_session`, `chuzom_agent_route` | unchanged (first-class doors) |

### What changed

- **Default tier** flipped `routing` → `consolidated`. The 11 doors are what a fresh
  install exposes.
- **Enforcement** names the door by default: an operational block now says "call `llm`"
  / "call `llm_act`" rather than a legacy tool name.
- **Nothing was deleted.** Every legacy tool remains an importable Python function that
  its door dispatches to (`DEPRECATED_TOOLS` in `tools/consolidated.py` is the map). Only
  their MCP *registration* is gated off by default.

### Escape hatch / migration

- Set **`CHUZOM_SLIM=off`** to restore the full legacy tool surface for all of 0.10 (also
  `routing` / `core` tiers remain available). Users whose MCP config pins `CHUZOM_SLIM=routing`
  should drop it (or set `consolidated`) to get the new surface.
- Breaking for anyone that invokes legacy tool *names* directly via MCP; use the door
  (or the escape hatch) — see the mapping table above.

## v0.9.0 — 2026-07-24 — Agentic router (MGEE) + classifier-selectable delegation

Adds an **agentic delegation** path so a routed task can be *done* (tools + verification),
not just answered. A new `llm_delegate` tool decomposes a task into milestones with
OBJECTIVE acceptance checks and runs them on the cheapest capable tier, escalating on
failure without redoing completed work (Milestone-Gated Escalating Execution). The
router can now *select* delegation automatically for operational prompts.

### Agentic delegation (`llm_delegate`)

- **MGEE engine** — decompose → run cheapest tier → objective acceptance (cmd/lint/diff/
  canary/validator; **never** the model's self-report) → escalate carrying the frozen
  done-frontier forward. Bounded and monotonic: an unmeetable milestone is *surfaced*,
  never looped. Fully transparent event stream + honest savings ledger.
- **Backends** — live planner (routes a model to emit an objective-check milestone plan,
  fails closed on error); **Codex tier** (`codex exec` with `workspace-write`, captures
  the produced diff) — verified live end-to-end; **local ReAct/Ollama tier-0** (bounded
  tool loop over Ollama native tool-calling, sandboxed executor with path-traversal
  containment) — best-effort, escalation-covered.

### Classifier-selectable delegation (enforced)

- Operational prompts (a code-mutating verb **and** an objective-verification demand) are
  hard-routed to `llm_delegate` via a new high-precision `operational_signal`. Rails: any
  `llm_*` call still clears the lock (never a trap), `CHUZOM_DELEGATE=off` and
  `CHUZOM_ENFORCE=soft/off` disable it, fail-open if the signal module is absent, and every
  redirect logs a `DELEGATE_ROUTE` security event with the matched verb/cue.

### Known limitations (honest scoping)

- The delegated agents receive the task's own milestone context but **not** the broader
  Claude Code session conversation yet.
- Local tier-0 reliability is best-effort; Codex is the dependable tier and escalation
  covers tier-0 gaps.
- `llm_delegate` requires a healthy analyze/query route for planning.

## v0.8.7 — 2026-07-23 — Audit remediation (P1–P5) + durable session context + version-scoped drift

Combines three tracks: truth-in-advertising fixes from the post-v0.8.6 audit
(`~/audits/chuzom-audit/`, findings P1–P5), a durable session-context accumulator so
routed models keep answering with real context, and a version-scoped base-model-drift
signal for the routing-audit-agent.

### Audit remediation (P1–P5)

- **P1 — Truthful routing claim in default mode.** `CHUZOM_RENDER_MODE=auto` is now
  the default: self-contained prompts with a successful free/local draft render
  `block` (Claude skipped, zero subscription tokens consumed); context-dependent
  prompts still render advisory `echo` (Claude runs the turn as before). Previously
  the default (`echo`) silently consumed a Claude turn on every prompt regardless of
  routing claims. README/banner copy corrected to match (no more unconditional
  "Claude never sees them" claims).
- **P2 — Conversation context for routed models.** Direct-execution calls now carry
  recent conversation history (`_load_conversation_history`, token-budgeted at
  `max_turns=6` / `max_chars=16000`) so a routed model isn't answering
  context-dependent follow-ups blind. Persisted via a per-session transcript shard
  (`~/.chuzom/transcript_<sid>.jsonl`) merged with the CLI transcript when present.
  Zero-claude mode fails closed (`{"decision": "block"}`) rather than routing a
  fabricated answer when context is missing or over budget. Gated by
  `CHUZOM_HISTORY_RELAY` (default: on) — **note:** the audit's fix plan refers to
  this as `CHUZOM_CONTEXT_RELAY`; the shipped flag name is `CHUZOM_HISTORY_RELAY`.
  Banners now report actual context inclusion instead of a fixed claim.
- **P3 — Enforcement mode correctness.** Tool-call classification (not
  session-level) drives hard-mode blocking; read-only `Bash` and non-generative
  `Write` calls are no longer caught by a stale `code/moderate` lock. Block text is
  now advisory framing instead of imperative "NEXT STEP (required)" prose. Default
  enforcement stays `soft` (nothing blocked, violations logged); hard mode's
  trap/loop escape valves (2-same-tool same-turn trap, 3-in-2-min loop detector) are
  now documented accurately in both the README and the module docstring (previously
  said "after 2 violations" for a mechanism that actually pivots at 4).
- **P4 — Honest metrics.** Banner latency and token counts are now measured
  wall-clock / provider-reported, replacing the previous fixed "0ms · 15 tokens"
  placeholder that fed directly into `savings_log.jsonl` and the dashboard.
- **P5 — Hygiene follow-ups.** Python 3.14 confirmed across classifiers and CI;
  `requires_codex` pytest mark registered; new `TaskType.COORDINATE` fast-path
  (advisory-only, never direct-executed); `chuzom gc [--ttl-days N] [--apply]` sweeps
  stale `~/.chuzom` shards (dry-run by default, protected files never touched);
  fixed a test-order env-leakage bug where `session-start.py`'s `_load_dotenv()`
  mutated real `os.environ` during test collection.

### Session-context accumulator

Routed models (local Ollama/Codex, Claude subscription, and external OpenAI/Gemini
APIs) previously answered stateless — a cheap drafted answer could not see the
session's files, decisions, or prior turns. Session events are now accumulated into
a durable per-session store and injected as a token-budgeted context block into
**every** provider path, so routing can keep happening all the time without
sacrificing answer quality.

- **New `session_store.py`**: records prompts, tool results, and decisions to
  `~/.chuzom/session_context_<sid>.jsonl`; `build_session_context()` returns a
  sentinel-wrapped, token-budgeted block (dedup + newest-first selection,
  re-ordered chronologically).
- **New `hooks/context-capture.py`**: UserPromptSubmit/PostToolUse capture hook
  (installed via `chuzom-install-hooks`).
- **All-provider injection**: wired into the MCP path (`context.py`) and all 5
  CLI-dispatch call sites in `router.py` (codex×2, gemini_cli×2, anthropic×1) via
  `_cli_prompt_with_context`.
- **Privacy modes** via `CHUZOM_SESSION_CONTEXT`: `all` (default) / `local` (context
  stripped from external openai/gemini targets only) / `off` — enforced inside
  `session_store` itself.
- **Fail-open guarantee**: any store/config failure falls back to routing without
  context; the accumulator can never block or skip routing. Empty context leaves
  prompts byte-identical (no empty sentinel blocks).
- **Lifecycle**: session-end deletes the store; session-start prunes stores older
  than 7 days in a detached subprocess.
- **Note:** this ships alongside the P2 history-relay mechanism (`CHUZOM_HISTORY_RELAY`)
  as a separate, coexisting mechanism this release — they are not yet unified.
  History relay carries recent *conversation turns* into direct-execution Q&A calls;
  the session-context accumulator carries a broader *session event* summary
  (prompts, tool results, decisions) into every provider path including CLI
  dispatch. Both are fail-open and additive today; unifying them into one context
  pipeline is a candidate for a future release.

### Base-model-drift versioning (G-METRIC-1 follow-up)

The routing-audit-agent's base-model-drift alert now reflects only the current
chuzom release instead of being contaminated by behavior carried over from older
versions in the durable `routing_outcomes` ledger:

- `chuzom_version` recorded on each `session_outcomes` upsert (+ migration for
  pre-versioned ledgers; older rows keep a `NULL` version and are excluded from any
  version-filtered read).
- `read_base_drift(period, version=...)`: filter to a given version;
  `version="current"` resolves to the running `chuzom.__version__`; `version=None`
  keeps the existing cross-version aggregate (back-compat).
- The routing-audit-agent spec now calls `read_base_drift(version="current")` and
  makes `base_drift_share` the primary base-model-drift alert, demoting the old
  subscription-escalation proxy to a secondary cross-check.

## v0.8.6 — 2026-07-20 — Savings integrity: correct + unify the savings baseline, add an honest dollar figure

Prompted by the 2026-07-20 routing retrospective. Multiple savings surfaces used
different windows, labels, baseline **models**, and baseline **prices**, so their
reported numbers disagreed by an order of magnitude. Full write-up:
`Docs/archive/savings-integrity-corrections.md`.

> ⚠️ **Reported savings numbers change.** The baseline price was ~3× too high, so
> historical `saved_usd` was ~3× inflated; the corrected figures are lower. This is
> the fix, not a regression. Free-local savings on a flat-rate subscription now also
> report `real_dollars_avoided_usd ≈ $0` beside the (unchanged-in-meaning but
> renamed) baseline-avoided figure.

### Baseline correctness (B-8)
- **Opus baseline corrected to $5/$25 and de-staled.** `cost.py` priced the host
  baseline at `$15/$75` labelled "Opus 4.6" — both frozen to a stale version and
  ~3× above the real Opus price (Opus 4.5+ is $5/$25). Now resolved from a single
  `LATEST_OPUS_MODEL` + `_OPUS_PRICING` source of truth (optionally refreshable via
  the Models API), so a future Opus release updates one place. The dead/misleading
  `BASELINE_MODEL_FOR_SAVINGS = "sonnet"` constant is repointed to the latest Opus.

### Surface reconciliation (B-6)
- **One baseline everywhere.** The SessionStart weekly digest priced against
  **Sonnet** (`_SONNET_*_PER_M`) while every other surface used Opus; it now sources
  the same latest-Opus rate.
- **Fixed the all-time-as-weekly mislabel.** SessionEnd summed the **all-time**
  savings row but printed `"saved this week"`; it now reads the weekly bucket.
- **Truthful window labels.** "Last 7 days" (rolling, banners) and "this week"
  (calendar, dashboard) are distinct-by-design and each labelled accordingly —
  forcing byte-identity would break `today ≤ week ≤ month` nesting.
- **Dashboard relabelled.** `llm_savings` no longer says "vs SONNET BASELINE" /
  "than using Sonnet" while computing against Opus.

### Honest dollar accounting (B-7)
- **Two figures, never conflated.** `baseline_avoided_usd` (Opus-baseline vs
  actual — a quota/token-smoothing story) and `real_dollars_avoided_usd` (dollars
  the user would actually have paid: ~$0 on a flat-rate subscription, the full
  baseline only in metered API mode, keyed on `CHUZOM_CLAUDE_SUBSCRIPTION`).
  Surfaced in `llm_savings`, `SessionSpend.get_summary`, and `get_savings_by_period`.

### Tests & offline experiment suite
- Red→green characterization tests: `test_baseline_price`,
  `test_real_dollars_avoided`, `test_savings_surface_reconciliation`,
  `test_baseline_is_labeled`, `test_subagent_routing_credited`.
- New deterministic, offline `bench/experiments` harness (`python -m
  bench.experiments`) replays three realistic session shapes through the real
  savings code and checks reconciliation, a counterfactual dollar model, and
  property invariants — the reproducible replacement for the retro's contradictory
  hand-math. Runs in CI via `test_bench_experiments`.

## v0.8.5 — 2026-07-17 — Self-audit remediation: observability, research-trust, benchmark keystone, subscription-only harness fixes

A remediation release from a full self-audit plus a live-reproduced MCP-generation bug
report. Fixes one real observability bug and a cancellation-audit gap, hardens
research-output trust and enforcement precision, adds a quality×cost benchmark with a CI
freshness/regression guard, and makes the benchmark + Ollama usable on a
Claude-subscription-only machine (no API keys). Full suite green.

### Observability
- **OTel span events emit again (G-OBS-1).** `observability.setup()` binds the tracer to
  its own provider instance rather than the process-global one (robust even if another
  library set the global first), so inversion / PII span events are exported again.
- **Cancelled turns keep their audit breadcrumb (G-OBS-2).** The router's
  `CancelledError` handler now writes the synchronous `"cancelled"` audit row before its
  async budget/envelope cleanup — under external `task.cancel()` the still-pending cancel
  re-raised at the first `await` and previously lost the record.

### Routing / Enforcement
- **Enforcement no longer hard-blocks operational prompts (G-ENF-1).** The
  context-dependent detector now catches operational commands (`stop`/`kill`/`cancel`/
  `delete`/…) and definite anaphora (`the rest`/`others`/`remaining`/…), so a prompt
  mis-classified `query/simple` that acts on local/session state stays advisory instead
  of blocking tool use.

### Research / Trust
- **`llm_research` enforces a source-trust contract (G-RESEARCH-NOKEY).** Citations
  render under **Sources** only when a web-grounded model answered; without a web backend
  the output leads with an UNVERIFIED banner and quarantines citations, so a non-web
  fallback can't present fabricated references as authoritative.

### Benchmark (quality×cost)
- **Corpus grown to 53 prompts across easy/moderate/hard** — the new hard tier makes the
  cost/quality frontier honest, since cheap models only visibly degrade on hard prompts.
- **`bench/guard.py` + `make bench` / `make bench-guard`** — a CI gate that fails when
  routing quality regresses below a floor or the newest results go stale.
- **Judge degrades gracefully (`CHUZOM_BENCH_JUDGE_FALLBACK`).** With no
  `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` the judge falls back to a local Ollama model
  instead of crashing the run, so a subscription-only environment can still produce a
  frontier.

### Providers
- **Configurable Ollama context window (`CHUZOM_OLLAMA_NUM_CTX`).** Opt-in; raises the
  4096 default so page-sized generations stop overflowing and returning empty content.

## v0.8.4 — 2026-07-15 — LLM-first ensemble routing, verified-only OKF session context

A routing-quality release. The classifier becomes LLM-first with a measured golden-set
lift, OKF context is safe-by-default and now carries verified-only session memory, and
the enforcement hook stops writing a pending route for prompts that can't be routed.
All changes ship green (full suite passing on the v0.8.3 base).

### Routing / Classifier
- **LLM-first ensemble classifier (`chuzom.ensemble`).** Every routed prompt is
  classified by a local Ollama model first, blended by weight with the deterministic
  signal engine, with a second local model breaking only thin-margin ties. Wired into
  the MCP routing tools via `classify_for_routing` (`CHUZOM_ENSEMBLE`, default on);
  degrades internally to the heuristic on cold start / model failure, so it never
  stalls or bounces. Full-100 golden set: **48% → 95% exact** (ensemble), **→ 85%** on
  the free 0ms heuristic path alone.
- **Task-type complexity floor** in the shared classifier — the anti-under-routing
  rule. Analysis/research route to the premium tier and code/writing to at least
  mid-tier regardless of how "easy" a prompt reads, so work isn't sent to a too-cheap
  model that fails and bounces back. Free (0ms/$0); **+28 points alone** (48% → 76%).
- **`research` signal fix.** "Find the latest/current/best-practices X" now classifies
  as research (fresh external info), not a query lookup (heuristic 76% → 85%); the
  classifier prompt was updated to match.
- **Cold-start warmup (`warm_primary`).** The primary local classifier is loaded at
  server startup in a daemon thread, so the first routed prompt pays warm latency
  (~2.5s) instead of an Ollama cold start (~56s).

### Enforcement
- **Context-dependent prompts write no pending route state.** Complements v0.8.3
  (which stopped blocking read-only local ops): a prompt referencing local files/repo/
  history has no correct external route, so the hook now suppresses enforcement instead
  of emitting a hard directive — closing the last path where a repo task forced a
  throwaway `llm_query` call. Auto-route hook → v26.

### OKF / Context
- **OKF on by default (verified-only policy).** The knowledge store now holds only
  checkable facts — seeded model-capability docs, extracted symbol names, real file
  paths, and the user's own prompts — and never model free-text prose, the
  hallucination amplifier that self-poisoned the store and got it disabled. With prose
  excluded there is nothing to hallucinate, so default-on is safe.
- **Verified-only session context (`record_session_turn` / `find_relevant_sessions`).**
  Each routed turn captures the user's real prompt plus extracted file/symbol structure
  under `sessions/<id>/`. Because relevance search rglobs the whole store, these notes
  are retrievable from any later session — cross-session memory that feeds the working
  model, so local routing has context instead of guessing.

## v0.8.3 — 2026-07-14 — Stop route-blocking non-routable local operations

### Enforcement — local dev commands are never routable
A Bash command that runs a local dev tool (git/gh writes, package managers,
build/test/lint, filesystem mutations, infra CLIs) is never LLM reasoning, so
no routed model can perform it — blocking it to "force routing" saves nothing
and just traps the user, especially on terse operational follow-ups like
"yes, delete the merged branch" (the git-branch-delete drift class).
- New `_is_local_only_bash()` + local-tool allowlist and a routable-escape
  guard: `curl https://…`, `wget`, `ollama run`, and other shell-driven LLM
  calls stay route-eligible so the shell can't be used to dodge routing.
- Such Bash is exempted in `hard`/`smart` modes, **scoped to non-QA, non-code
  task types**: QA still routes by passing content to `llm_analyze`, and code
  keeps the route-first gate (one `llm_code` call clears the lock). Only
  operational task types (e.g. `coordination`) are exempted — that is where
  the drift was. Disabled under `strict`, consistent with the read-only valve.

### Enforcement — native local file ops are never routable
`Edit` / `Write` / `MultiEdit` / `NotebookEdit` (mutations) and `Read` / `Grep`
/ `Glob` / `LS` (inspection) only ever touch local files, which no stateless
routed model can do — so blocking them to force routing is drift on terse
operational follow-ups ("yes, do it"). Exempted in `hard`/`smart` with the
**same scoping** as the Bash rule: QA keeps routing via `llm_analyze`, code
keeps the route-first gate, only operational task types are exempted. Disabled
under `strict`.

## v0.8.2 — 2026-07-13 — Drift-free local agent loop + self-calibrating model registry

### Agent loop reliability
Local tool-calling models could silently no-op: small models (e.g.
qwen2.5-coder:7b) emit the tool call as text in `content` instead of a
structured `tool_calls` entry, so the loop returned the blob as a "final
answer" and wrote nothing.
- **Repair shim** (`hooks/agent_loop.py`): recover text-embedded tool calls
  and execute them (qwen2.5-coder:7b: 0/3 → 3/3; no-op for well-behaved models).
- **Loud fallback ladder** (`hooks/agent_loop.py`, `hooks/direct_executor.py`):
  zero tools executed on a file task returns `None` (no fake success);
  verified tool-callers ordered first; stderr on chain exhaustion instead of a
  silent `None`.

### Enforcement — no more blocking on local tasks
- **FS_EXEMPT** (`hooks/enforce-route.py`): filesystem/local prompts (detected
  via `needs_claude_tools`) never block native tools in any mode — fixes the
  hard-mode `BLOCKED`/`AUTO-PIVOT` churn on tasks a stateless routed model
  cannot satisfy.

### Self-calibrating agentic model registry
- **`agentic_registry.py`**: best-of-N ground-truth probe of each installed
  Ollama model (the `tools` capability flag is not trustworthy), cached to
  `~/.chuzom/agentic_models.json` keyed by model-set hash + TTL so new/drifting
  models auto re-probe.
- **`best_agentic_model()`**: dynamic, per-user pick of the best *verified*
  model — cache-only on the router hot path, gated on availability so
  PREMIUM/REASONING and no-local-provider environments never get a phantom
  local model.
- **`chuzom probe`** CLI + first-run background probe on install.

## v0.8.1 — 2026-07-12 — Library layer (context distillation), hermetic routing CI, domain-router exploration

### Library layer — persistent session memory
New `chuzom.library` package: an OKF-frontmatter Library store with index
regeneration (`store.py`), a PostToolUse harvest hook
(`hooks/library-harvest.py`) appending JSONL events + entities + delta.md,
chapter sealing on git events with librarian distillation (`sealer.py`),
book closing with conservative Biography merge (`book_closer.py`), budget-
tiered abridgement with a (chapter_sha, tier) cache (`abridge.py`), and
router integration via `pack_for()` with 5 freshness gates (`pack.py`).
Covered by the `tests/library/` suite.

### CI — hermetic routing unit
New `routing-hermetic` CI job runs the `routing_hermetic`-tagged suites on
a bare runner with no API keys and no `~/.chuzom` state, proving the
autouse `_hermetic_host_state` fixture guarantee holds and catching tests
that silently lean on local routing.yaml pins or CLIs.

### RouterArena — domain-expert routing exploration
Domain centroid build/measure/fetch scripts, domain train/holdout datasets,
domain model map, and sandbox runners (`run_domain_router.py`,
`run_solo.py`) for per-domain expert routing experiments.

## v0.8.0 — 2026-07-12 — opus-equivalent savings ledger, secrets vault, invoice reporting, RouterArena closeout

### Savings ledger — opus-equivalent baseline
Savings display rewired to an opus-equivalent-only baseline: every routed
turn is compared against the cost of the same tokens through Opus, with
DIRECT-call metering and a per-session JSONL bridge from the gateway to the
session ledger. Receipt store persists fire-and-forget receipts to SQLite
with token/savings reclamation and correlation-id tracking.

### Secrets vault + gated live OIDC test
New `chuzom.secrets_vault` module. A live Okta OIDC integration test
exercises the full production validation path; it is env-gated and never
runs in CI or without an operator-provided tenant.

### Invoice reporting
New `chuzom invoice` command producing per-session cost/savings reports
from the receipt store.

### Gateway/router
Routing-value config fixes, gateway presets, runtime router wiring,
session-summary x-axis fix, and fail-open alert-sink tests.

### CI
Capability-claim lint guard (`scripts/lint_capability_claims.sh`) with a
recorded baseline blocks new unbaselined capability claims.

### RouterArena closeout
Submission scripts, eval harnesses (cascade/hedge/vote/self-consistency,
killgates, MCTS council, memorytree), history + commit chronicle committed;
derived artifacts (logs, result/eval JSONs, npz) gitignored.

## v0.7.8 — 2026-07-11 — control plane (G-004), claude_agent offload provider, RouterArena sandbox

Three merged feature PRs (#127–#129).

### Sidecar-per-tenant control plane — gap G-004 closed (#129)
Central control plane owning canonical, versioned per-tenant policy,
distributing Ed25519-signed policy bundles to per-tenant sidecars. Instances
keep routing, budget reservations, and their local audit chain; a
control-plane outage never blocks a routed turn (fail-static).
- Store: SQLite + Postgres backends (tenants, versioned policy, active
  pointer, instances, append-only heartbeats).
- Policy bundles: deterministic normalization + sha256 digest; secure YAML
  scanner rejects plaintext secrets in bundles.
- Signing: Ed25519 sign/verify; sidecars verify against a PINNED public key
  (rejects key substitution), atomic last-known-good disk cache.
- Control plane's own tamper-evident hash-chained audit log.
- FastAPI admin/sidecar API: policy push, heartbeats, signed bundles,
  /public-key; effective-version heartbeats with transition-only audit;
  SSE policy-change push for the <5s SLO; migration + reconciliation.
- Router enforces control-plane-installed policy via `apply_policy`;
  behaviour-identical when none is installed.

### claude_agent — Claude Code CLI as a pressure-gated offload provider (#127)
Claude Code CLI wired in as an offload provider, engaged under budget
pressure like other gated backends.

### RouterArena Phase 0 sandbox (#129)
RA-independent offline eval + sealed one-shot measurement: read-only
sha256-pinned import of RA's official metrics, 192 self-generated proxy
items (zero RA/RouterBench data), tamper-evident hash-chain ledger that
refuses re-runs, PROVENANCE.md mapping each PR-155 rule to compliance.

### Docs
- README imagery refresh (#128).

### Test reliability
- Reset module-global quality-feedback store between tests (fixes
  order-dependent failures under pytest-randomly).

## v0.7.7 — 2026-07-10 — model registry refresh + DeepSeek alias migration

Routing-critical model/pricing update. No API or behavior changes beyond the
model set and cost data.

### DeepSeek alias migration (the urgent bit)
DeepSeek deprecates the `deepseek-chat` and `deepseek-reasoner` API aliases on
**2026-07-24** (requests error after that). Migrated all runtime references:
- `deepseek/deepseek-chat` → `deepseek/deepseek-v4-flash` ($0.14/$0.28 per 1M),
  in `auto_profile.py`, `profiles.py` (`_CHEAP_MODELS`, `CLASSIFIER_MODELS`),
  `tools/setup.py`.
- `deepseek/deepseek-reasoner` → `deepseek/deepseek-v4-pro` ($1.74/$3.48),
  retiered cheap→mid. v4-pro chosen (not v4-flash) because Chuzom has no
  thinking-mode parameter wiring, so v4-flash would default to non-thinking and
  silently drop reasoning. Follow-up: wire V4 Flash thinking mode to reclaim the
  cheaper reasoning path.
- Added v4-flash/v4-pro keys to all cost/limit/benchmark tables
  (`provider_budget.py`, `benchmarks.py`, `tools/text.py`,
  `inference_robustness.py`, `token_budget.py`, `benchmark_fetcher.py`).

### OpenAI registry refresh
- Added current lineup: `gpt-5.6-sol/terra/luna`, `gpt-5.5`, `gpt-5.4`/`-mini`/`-nano`.
- **Repriced `o3` $60/$240 → $2/$8** (was badly stale, corrupted cost math).
- Removed delisted base `gpt-5`.

### Other providers refreshed in `config/models.yaml`
- Anthropic: `claude-3.5-haiku`→`claude-haiku-4-5` ($1/$5),
  `claude-3.5-sonnet`→`claude-sonnet-5` ($2/$10 intro, $3/$15 from 2026-09-01),
  `claude-3-opus`→`claude-opus-4-8` ($5/$25).
- Gemini (slug `google/`→`gemini/` to match the router): `gemini-3-pro`,
  `gemini-3.5-flash`, `gemini-3.1-flash-lite`.
- New providers added: `xai/grok-4.3` + `grok-4.1-fast`, `mistral/mistral-large-latest`.

Known non-blocker: two pre-existing `test_router.py` claw-code tests fail on the
current tree due to unrelated Codex subscription-mode injection work; not caused
by this change (verified by stashing these edits).

## v0.7.6 — 2026-07-05 — pxpipe integration: cut context cost on heavy-model calls

New, fully opt-in (off by default). [pxpipe](https://github.com/teamchong/pxpipe)
is a local proxy that rewrites bulky request context (system prompt, tool docs,
older history) into compact PNGs before it reaches Claude's API — image tokens
are cheaper than dense text tokens at Anthropic's pricing, cutting the bill on
expensive, high-token-count calls. Two independent integration points, since
Chuzom's own dispatch and Claude Code's own subscription traffic go through
completely different paths:

### Router-level (API-key mode)
- New `AnthropicPxpipeQuirk` in `provider_quirks.py`, registered for the
  `anthropic` provider in Chuzom's existing per-provider transform-hook
  registry. When a dispatch's model is on the configured heavy-models list
  (`CHUZOM_PXPIPE_HEAVY_MODELS`, default `claude-fable-5` — mirrors pxpipe's
  own conservative default, since Opus has a documented ~7% image-misread
  rate), pxpipe is enabled (`CHUZOM_PXPIPE_ENABLED`), and the proxy is
  actually reachable, redirects that call through it. Everything else —
  cheap models, pxpipe not running, feature disabled — passes through
  completely untouched.

### Claude Code subscription mode
- Chuzom's own routing never makes a real Anthropic API call in subscription
  mode (that's Claude Code's own turn), so the router-level quirk above has
  no effect there. Added a second, independent path: a new SessionStart hook
  step that auto-starts a local pxpipe proxy (`start-pxpipe.sh`, mirrors the
  existing `start-ollama.sh` pattern) and syncs `ANTHROPIC_BASE_URL` into
  `~/.claude/settings.json`'s `env` block — so Claude Code's *own* traffic,
  not just Chuzom-routed calls, benefits.
- Safety-critical since this affects *every* Claude Code API call, not just
  heavy-model ones: only ever writes when the key is currently unset (never
  overwrites a corporate proxy or anything else you set deliberately), and
  always self-heals the override away — reverting to Anthropic's default
  endpoint — the moment pxpipe is disabled or not actually reachable, rather
  than leaving Claude Code pointed at a dead endpoint (it has no fallback if
  the configured base URL doesn't answer).
- Takes effect on the *next* Claude Code session — `ANTHROPIC_BASE_URL` is
  read before this hook, or any hook, ever runs.

### Installer fix (found along the way)
- `start-ollama.sh` had never actually been wired into the installer at all
  — a pre-existing gap independent of pxpipe. A fresh install always left
  `_ensure_ollama_running()` unable to find the script it shells out to.
  Fixed for both scripts via a small new sidecar-copy step.

Verified against a real, live pxpipe instance (not just mocks): actually
started it via `npx pxpipe-proxy`, confirmed reachability detection and the
settings.json read-modify-write round-trip against a copy of a real
`~/.claude/settings.json` (write, no-op-when-correct, and self-heal-on-down
all confirmed, with every unrelated existing key left untouched), and sent a
real request through it to `/v1/messages` — got back a genuine Anthropic
`authentication_error` response, confirming the proxy correctly intercepts
and forwards to the real API. 34 new tests, all passing; lint clean.

## v0.7.5 — 2026-07-04 — test isolation: health tracker no longer leaks across tests

Follow-up to v0.7.4's CI fix. No functional changes to the router itself.

- **The provider `HealthTracker` is a process-lifetime singleton** — a test that
  makes a real, failing provider call (v0.7.4 added a dummy `OPENAI_API_KEY` to CI
  so ~20 pre-existing tests could reach the dispatch stage) marked "openai"
  unhealthy for the rest of the pytest run, silently breaking two later,
  unrelated tests (`test_chain_all_disallowed_raises_permission_denied`,
  `test_strict_with_all_providers_forbidden_raises_permission_denied`) that
  expected it to still be healthy. Added `reset_tracker_for_tests()` plus an
  autouse conftest fixture so every test starts with a clean tracker.
- Full local suite run (matching CI's exact command) confirmed clean.

## v0.7.4 — 2026-07-04 — CI fixes following v0.7.3 (no functional changes)

v0.7.3's routing fixes are correct and unaffected — this release only fixes gaps the
CI run surfaced *after* that release was already tagged and published, so main's
test suite is green again. Nothing here changes runtime behavior.

- **Plugin manifest versions were out of sync** — `.claude-plugin`, `.codex-plugin`,
  and `.factory-plugin`'s `plugin.json`/`marketplace.json` files still said 0.7.2;
  re-ran `scripts/sync-versions.py`.
- **Two pre-existing test files hardcoded the old shared `agent_depth.json` path**
  (`tests/test_agent_route_hook.py`, `tests/test_agent_resource_budgeting.py`) —
  the v0.7.3 circuit-breaker fix moved depth-tracking to a per-session file on
  purpose (that's the whole fix for cross-session interference), so these needed
  updating to write/read the new per-session path instead of the retired one.
- **CI's bare test runner had zero providers configured**, and a v0.7.3 fix
  correctly stopped unavailable providers from silently surviving the chain
  filter — surfacing that ~20 pre-existing tests (RBAC, deadlines, cancel-shield,
  enterprise enforcement, redaction, idempotency) implicitly relied on that bug to
  get any candidate into the chain at all, even though they patch the dispatch
  layer and never make a real call. Added one dummy `OPENAI_API_KEY` to the CI
  job so `available_providers` is non-empty — no real network calls are made.
- **8 ruff lint errors** in the new `tests/audit/` files from v0.7.3 (unused
  imports/variables) — fixed.

## v0.7.3 — 2026-07-04 — routing-variety audit: fixes a structural single-model collapse

A full routing audit (chain-building, execution, policy switching, multi-provider
generalization, telemetry, concurrency) found and fixed a chain of bugs that could
silently collapse ANY user's routing to one model, regardless of how many providers
or per-task pins they configured. All changes ship green (142 tests passing).

### Routing
- **Fixed the root single-model collapse**: an unconditional Ollama-injection step
  used to prepend every local model to the front of every candidate chain,
  clobbering per-task pins — every task type routed to whichever local model was
  configured first, no matter the use case.
- **Fixed the same collapse for the no-pin default path**: without an explicit pin
  (the default for most users), QUERY/CODE/ANALYZE/GENERATE all resolved to the
  identical chain. Added task-aware default ordering (light naming heuristics +
  a deterministic per-task rotation) so routing varies by use case out of the box.
- **`_reorder_for_agent_context` no longer buries pins**: it regroups the chain
  strictly by provider tier with no notion of an explicit pin — a per-task model
  *or* provider pin now survives every reorder pass, not just the model pin.
- **Provider-availability filter now checks real availability**: `codex`/`ollama`/
  `gemini_cli`/subscription-mode `anthropic` candidates used to survive the filter
  unconditionally, so an environment missing one of those tiers could still see
  phantom, unreachable models in its chain (including a case that produced a fully
  empty chain for Claude-subscription-only setups).
- **`block_providers`/`block_models`/`allow_models` now apply after injection
  too** — previously only checked once before Ollama/Codex/Gemini-CLI injection,
  so a blocked provider's freshly-injected model slipped through anyway.
- **Codex CLI dispatch fixed**: a stale CLI binary rejecting current model IDs, the
  installer forcing Codex's global default provider through Chuzom's own gateway
  (which doesn't yet speak Codex's expected wire format, breaking Codex entirely),
  and a missing environment variable required by an unrelated registered provider.

### Fixes
- **`llm_savings` always reported zero** regardless of real usage — the underlying
  query referenced columns that don't exist on the real schema, silently raising
  and swallowing an error on every call.
- **`routing.yaml`'s `daily_caps`/`enforce` are no longer dead config** — they were
  previously read only by `chuzom config`'s display output, never by live routing.
  Both are now real: a routing.yaml cap and an org-policy.yaml cap combine to the
  more restrictive of the two, and `enforce: soft` now downgrades a would-be block
  into a warning instead of one hard-coded blocking behavior for every mode.
- **Fixed a 100x-too-permissive unit bug**: per-task spend caps are stored in
  cents but were compared directly against dollar-denominated spend.
- **Installer no longer breaks Codex CLI for other host integrations** — it
  previously force-set a global default that made every Codex call (not just
  Chuzom's own) fail; now only registers the provider for explicit opt-in, and
  self-heals an existing broken config on reinstall.
- **Dashboard "tokens saved/day" chart no longer mixes units** on one axis (e.g.
  "3.2M" next to "450.7k") — the whole axis now locks to a single unit.
- **Claude Code agent-nesting circuit breaker no longer shares state across
  concurrent sessions** — depth tracking was keyed to a single machine-wide file
  regenerated by every session's startup hook, so two Claude Code windows running
  at once could trip each other's circuit breaker. Also added the missing
  post-completion release, since depth previously only ever went up.

## v0.7.2 — 2026-07-01 — audit mitigation: unified classifier, honest fixes, portability

Follow-up to the v0.7.1 audit — closes credibility gaps in routing, onboarding, and
observability. All changes ship green (full suite passing).

### Routing
- **Unified, parameterized classifier (`chuzom.classify`).** `router.py` and
  `gateway.py` now share one scoring+complexity engine via per-path `ClassifyPolicy`,
  replacing a pure-length heuristic (router) and a crude code/analyze regex (gateway) —
  each keeps its tuned thresholds, so behavior is preserved while the drift is gone.
  Tables backfilled verbatim from the hook (now includes image-task detection).
- **Fable 5 as the last-resort deep-reasoning escalation** in the REASONING chain.

### Fixes
- **`onboard.py` no longer wipes unmanaged `.env` keys** on re-run (merges instead).
- **Session-start stops nagging "ANTHROPIC_API_KEY missing"** under
  `CHUZOM_CLAUDE_SUBSCRIPTION` — Claude arrives via the subscription.
- **`session_spend` re-syncs** when the session-start hook resets the file, so a
  long-lived router no longer clobbers the per-session reset with a stale total.
- **14-day dashboard x-axis** no longer collides date labels (`23/627  1` → `23/6  1/7`),
  via a testable `_date_axis_label_row` (oldest/today d/m at the edges, midpoint day
  only when it fits with a gap on each side) with 6 regression tests.
- **Session-end savings now tells one consistent story.** The headline ("Routing
  saved N% of baseline") and the per-tier Routing Summary both derive from the same
  rollups, so they always agree. Removed the "Opus would cost / Actually spent / Net
  preserved" trio — it compared the Opus baseline of the *reclaimed* calls against
  *total* spend (incl. non-reclaimed paid calls), a mixed-scope figure that
  contradicted the tier table (e.g. "Net preserved $0.01" next to "Saved $0.05").
- **Honest overspend signal.** When paid routes cost more than the Sonnet baseline,
  the effective-ratio line now reads "⚠ paid routes ran N× OVER the baseline" instead
  of presenting a sub-1× ratio as savings.
- Removed hardcoded author paths from `cli.py` and `scripts/verify_three_checks.sh`.

### Portability & docs
- **Per-user gateway service generator** (`chuzom.gateway_service`) renders the launchd
  agent (macOS) / systemd user unit (Linux) from `sys.executable` — no more checked-in
  machine-specific paths; the reference plist is now a placeholder template.
- Routing-savings dashboard labels the figure as an **estimate vs the Opus baseline**.
- Synced plugin-manifest versions with `pyproject`.

## v0.7.1 — 2026-07-01 — honest routing, context-aware drafts, unified gateway metering

### Routing correctness & safety
- **Context-aware routing (no blind drafts).** A much stronger `_is_context_dependent`
  detector (adjective-tolerant nouns, operational verbs, deictic pronouns, file paths)
  suppresses the DIRECT draft for prompts that reference the user's files/repo/history
  and emits a "route WITH context via `llm_query(context=…)`" directive instead — the
  fix for context-blind fabrication (e.g. `npm run start` for a Python repo).
- **Free-tier-only drafts + per-session paid cap.** Drafts can never hit a paid API
  (chain filtered to ollama/codex/gemini_cli); a `CHUZOM_SESSION_PAID_CAP` (default
  $0.50) tells the caller to stop routing to paid tiers once crossed.

### Honesty
- **De-fanged the route banner and violation notice.** The "🚫 ALL BLOCKED / will
  reject any native tool call" banner and the "PREVIOUS TURN VIOLATED ROUTING …
  escalated" line were empty threats; both now reflect what the enforcer actually
  does. Banner tone is task-aware under `smart`.
- **Honest net savings.** Session summary shows an unclamped NET line (baseline −
  actual across all tiers), flagged as `⚠ NET LOSS` when paid routing made it negative.

### Enforcement
- **Unified enforcement config.** New `chuzom.enforce_config.resolve_enforce_mode`
  is the single source of truth for both the banner and the enforcer (priority: env
  > repo `.chuzom.yml` > `~/.chuzom/routing.yaml` > `smart`), so enforcement is
  consistent across sessions/launch methods instead of depending on a `~/.zshrc` export.

### Gateway / external agents (LoopHole)
- **Unified gateway on `route_and_call`.** All wire-format endpoints (OpenAI/Anthropic/
  Ollama) plus a new native `POST /route` now go through the full router, so external
  callers get budget caps, caching, and the paid-spend cap uniformly. `route_server`
  kept as the zero-dependency fallback.
- **Host-tagged metering for external traffic.** Gateway/LoopHole routes now write a
  `host`-tagged savings record (without polluting the session ledger), and the
  cross-surface indicators read the durable `savings_stats` store so they survive
  `savings_log.jsonl` truncation and show external traffic.

### Observability
- **`llm_health` reflects the real routable set** (counts a reachable local Ollama
  instead of reporting "0 providers" while routing to it).
- **Cross-surface indicators + token amounts** on every routing surface (compact line,
  terminal title, statusline, SUGGEST estimate).

### Fixed
- **macOS statusline quota never refreshed** — the refresh was gated behind `flock`
  (Linux-only); replaced with a portable timestamp throttle.
- **Timezone-correct "today"/period reporting** — savings, usage, digests, dashboards,
  and the statusline now compare UTC-stored timestamps in the user's local timezone
  (they mis-bucketed the last N hours near midnight for non-UTC users).
- **Fully hermetic test suite** — removed environment dependence (timezone-seeded rows,
  the BM25 result cache) so the suite is deterministic regardless of TZ, wall clock, or
  the developer's `~/.chuzom` state.

## v0.7.0 — 2026-06-30 — multi-agent subagents + fabrication-safety fix

### Features
- **Subagents now WORK (route, don't block).** `chuzom-agent-route.py` no longer
  blocks reasoning subagents. It ALLOWS a real spawn on a cheap Claude tier
  (haiku/sonnet, capped — never opus) and injects the chuzom routing contract into
  the subagent prompt, so the subagent self-routes its substantive work to the
  chuzom MCP. Councils / parallel reviews / fan-out finally run as real subagents
  while cost stays bounded (cheap harness + offloaded thinking + depth breaker).
  - Helpers: `_allow_routed_spawn()`, `_spawn_model()` (downgrade-only),
    `_with_routing_note()`. Toggle `CHUZOM_ALLOW_SUBAGENTS=off` for legacy behavior.
- New `chuzom-worker` agent type for explicit cheap committees.

### Fixed (safety)
- **Fabricated answers no longer presented as fact.**
  `response_formatter.format_echo_context` dropped the "deliver the cached answer
  verbatim" instruction. A context-free local model can't see the user's files,
  codebase, tools, or history, so it fabricated for context-dependent prompts (it
  once invented a non-existent "previous session"). Drafts are now labeled
  UNVERIFIED and the agent is told to ignore them and answer from real context
  whenever the question depends on anything the draft model couldn't see. Block-mode
  output carries the same warning.

### Known / follow-up
- Deeper fix: gate draft pre-generation in `chuzom-auto-route.py` to skip
  context-dependent prompts entirely (saves the wasted local call; the formatter
  fix already removes the harm).

## v0.6.3 — 2026-06-28 — IDE rules overhaul + routing reliability

### Features

- **All IDE rule templates rewritten** — every `src/chuzom/rules/*.md` file now
  has a `<!-- chuzom-rules-version: 2 -->` marker (idempotency: re-running
  `chuzom install` no longer duplicates content), explicit pull-routing emphasis,
  consistent Ollama→Flash→GPT-4o-mini provider chain notation, and `llm_reason`
  row in all tool tables. Affected: `vscode-rules.md`, `cursor-rules.md`,
  `copilot-rules.md`, `copilot-cli-rules.md`, `gemini-rules.md`,
  `gemini-cli-rules.md`, `opencode-rules.md`, `openclaw-rules.md`,
  `desktop-rules.md`, `trae-rules.md`, `pi-rules.md`, `codex-rules.md`.
- **Trae IDE rules now deployed** — `chuzom install trae` previously wrote only
  `~/.trae/mcp.json`; now also appends `trae-rules.md` to
  `~/.trae/rules/chuzom.md`.
- **Gemini CLI subcommand uses correct rules file** — `chuzom install gemini-cli`
  was appending the 19-line stub (`gemini-rules.md`); now correctly uses the full
  `gemini-cli-rules.md`, consistent with the full `chuzom install` path.
- **Copilot CLI subcommand uses correct rules file** — `chuzom install copilot-cli`
  was appending `copilot-rules.md` (a documentation page); now uses
  `copilot-cli-rules.md` (the proper rule file), consistent with the full
  `chuzom install` path.
- **Ollama pre-flight** — 0.5 s GET `/api/tags` before any Ollama call; chain
  skips all Ollama steps immediately on timeout instead of waiting 4 s per model.
  `CHUZOM_OLLAMA_TIMEOUT` default lowered from 15 s → 4 s.
- **`CHUZOM_CLASSIFY_LOCAL_ONLY` auto-detection** — when not explicitly set,
  allows API classifiers if Ollama is unreachable AND an API key is present;
  stays local-only otherwise (privacy-safe default).
- **Windsurf pull-routing rules** — `.windsurf/rules/use-chuzom.md` now created
  by `chuzom install windsurf`, matching the Cursor `.mdc` rule file.
- **Pull-routing session banner** — `session-start.py` detects `.cursor/` and
  `.windsurf/` dirs and adds a `pull →` line listing which IDEs use pull routing.
- **Pull-routing auto-update** — once per 24 h, `session-start.py` silently
  updates stale `.cursor/rules/use-chuzom.mdc` and
  `.windsurf/rules/use-chuzom.md` to the bundled template without user action.
- **Hook self-healing** — `enforce-route.py` emits a user-visible warning when
  `chuzom-auto-route.py` is missing from `~/.claude/hooks/`, prompting
  `chuzom install` to restore it.
- **CI smoke-test matrix** — `.github/workflows/smoke-test.yml` runs import,
  routing, research-bypass, and install-hooks dry-run across
  ubuntu/macOS/windows × py3.10/3.11/3.12 × pip/uv.
- **`~/.chuzom/` initialized at onboard** — `chuzom onboard` now creates the
  state directory and `usage.db` schema before hook installation, preventing
  first-run errors on clean machines.
- **No-provider error clarity** — `RouterConfig` raises a structured
  `ValueError` with `chuzom doctor` guidance and provider links when no model
  is configured.

### Fixes

- Research task type now correctly bypasses Ollama chain at all complexities and
  falls through to `llm_research` (Perplexity) in both direct-execution and MCP
  paths.
- Windows: `chuzom install` no longer hardcodes `bash` for the status-line hook;
  falls back gracefully when bash is absent. `APPDATA` → `LOCALAPPDATA` fallback
  for Claude config path.
- Test suite: 15 previously failing tests fixed (format drift E1–E6, binary PATH
  E4, Ollama model discovery E5, JSON parse E6, pre-flight D4).

## v0.6.2 — 2026-06-27 — Route everything: gateway, SDK, multi-protocol, observability

### Features

- **OpenAI-compatible gateway** (`chuzom gateway`) — wraps the router behind
  `POST /v1/chat/completions`; any litellm/openai client routes through Chuzom via
  `OPENAI_BASE_URL`. Meters into `usage.db` + `savings_log` + `model_tracking.jsonl`.
  The Surface-C fix: external agents (Stockagent, cron, Agno) finally hit the ledger.
- **Multi-protocol** — the gateway also serves Anthropic `/v1/messages` and Ollama
  `/api/chat` + `/api/generate`, so a client enrolls via whatever SDK it speaks.
- **In-process SDK** — `from chuzom import route` for Python agents (no HTTP).
- **Infra presets** — `~/.chuzom/presets.yaml` + `CHUZOM_PRESET`; gateway & clients
  resolve endpoint/host/port/profile from it. No hardcoded URLs across users/infra.
- **`advise` enforce mode** — route everywhere but never block a tool or log a
  violation (`auto-route` keeps DIRECT-executing). Removes the override friction.
- **Agent-loop routing** — file/local prompts route to a local tool-calling model
  (gateway + SDK), so every prompt routes. (Local-model agentic quality is the limit.)
- **Observability** — `chuzom routing-report`: per-model tokens/latency/savings,
  routing-outcome matrix, model-swap latency note.
- **CI gate** — `make verify` (enforcement lint + tests + version-sync + report);
  `scripts/lint_no_direct_llm.py` fails on direct provider calls bypassing Chuzom.
- **Gateway launchd service** so it's always up; richer/consistent `🎯 Chuzom routed`
  indicator (model · task · latency · tokens) in both the reply line and stderr banner.

### Fixes

- Gateway/SDK routings now also write `model_tracking.jsonl`, so they show in
  `chuzom summary`, not just `chuzom routing-report`.

## v0.6.1 — 2026-06-27 — Don't route local-machine tasks; atomic release script

### Fixes

- **Routing no longer misfires on local-machine / credential / run-app prompts.**
  `needs_claude_tools()` early-returned `False` for research/query/generate task
  types, so prompts like "search my machine for the token" routed to a web model
  that can't touch the disk. Added an all-task-type gate that keeps local
  filesystem / credential-location / env-keychain / run-the-app intents native,
  while genuine general questions still route. Regression test:
  `tests/test_local_task_no_route.py` (14 cases).

### Tooling

- **`scripts/release.sh` — one atomic release.** Bumps the version across
  `pyproject.toml` + all 6 plugin manifests, requires a matching CHANGELOG entry,
  runs the version-sync + unit tests, builds + `twine`-checks + clean-room-verifies
  the wheel, commits, tags, then pushes + publishes + drafts the GitHub release
  (credentialed steps degrade to printed commands when auth is absent). No more
  PyPI/GitHub/plugin version drift.

## v0.6.0 — 2026-06-26 — Honest, grounded session savings (potential vs realized)

### Fixes

- **DIRECT-routed turns showed $0 in the session views.** `llm_session_spend` /
  `llm_session_savings` (and `session_spend.json`) read the session ledger, but the
  DIRECT (hook) path only wrote `usage.db` — it never called `session_spend.record()`.
  So a session that routed exclusively through the DIRECT path reported `$0 / 0 calls`
  even though `usage.db` had recorded real token savings (two ledgers, the session one
  blind to DIRECT). `savings_logger.log_direct_savings()` now mirrors each DIRECT
  routing into `SessionSpend` via `record()` + `record_reclaimed()`, fire-and-forget.

### Features

- **Honest savings split — potential vs realized.** Routing savings are a
  counterfactual; they are only *realized* if the main model actually uses the routed
  answer. New `SessionSpend.potential_savings_usd` / `realized_savings_usd` /
  `overridden_turns`: when the enforce hook sees a routing violation (the model does the
  work itself), it calls `mark_overridden()` (deduped per `prompt_sequence`), and those
  turns are excluded from realized savings. `llm_session_spend` now renders both figures
  plus an override count, so the number can no longer overstate savings.

### Internal

- `SessionSpend` round-trips `prompt_sequence` (and the new override fields) so
  DIRECT-path persistence no longer drops the hook's prompt counter.
- New regression suite `tests/test_direct_session_spend.py` — grounds every aggregate in
  the input token counts and covers override proration + per-turn dedup.

## v0.5.10 — 2026-06-25 — DIRECT routing fully visible in usage + routing_decisions

### Fixes

- **DIRECT-routed turns were invisible in the routing view.** The DIRECT (hook) path
  only wrote to `savings_log.jsonl` → `savings_stats`; it never called
  `cost.log_usage` / `cost.log_routing_decision`. Since DIRECT intercepts every
  prompt, the `usage` and `routing_decisions` tables (which the routing view/summary
  read) stayed frozen. New `savings_logger.log_direct_to_db()` mirrors the MCP path
  and writes both tables (rows tagged `reason_code='direct'`), fire-and-forget so the
  hook never blocks. Hook bumped to v24 so the installer redeploys.
- **Token metering for DIRECT-routed calls.** Free-provider (Ollama/Codex) routes
  captured token counts in `DirectResult` but dropped them at `savings_logger`, so
  `savings_stats` (and the dashboard token totals) under-counted. Tokens now flow
  logger → `savings_stats` (new `input_tokens`/`output_tokens` cols + migration) →
  `dashboard_data.query_window` totals. Old DBs migrate idempotently.
- **Green CI.** Fixed a pre-existing ruff E702, synced plugin manifests to the
  release version, and made the enforcement-logging hook test hermetic
  (`CHUZOM_DIRECT_EXECUTION=0`) so it no longer OOM-kills its subprocess under
  full-suite load.

## v0.5.8 — 2026-06-24 — Accurate savings report + subagent allowlist

### Fixes

- **`savings-report` contradicted itself.** It read the `usage` table and recomputed a flat-Opus
  baseline, while the authoritative per-call savings live in `savings_stats` (per-complexity
  baselines) — so the report total disagreed with the stored stats. Worse, the "External (Paid)"
  and "Free" sections both matched the local/ollama rows, **listing the same calls twice**. The
  report now reads `savings_stats` as the single source of truth, splits paid vs free by
  `external_cost` (no overlap), and reports the stored saved amount directly — so the report
  equals the ledger exactly. Adds an explicit note that downstream agent/tool tokens are not metered.

### New features

- **`CHUZOM_AGENT_ROUTE_ALLOW`** — allowlist subagent types that bypass the agent-route hook
  (always approved) for agents that must do real tool-work (run tests, edit files, QA/validation)
  where redirecting to an `llm_*` text call is no substitute. Read from env, then `~/.chuzom/.env`
  (takes effect without restarting the host). Example: `CHUZOM_AGENT_ROUTE_ALLOW=code-reviewer,qa`.

---

## v0.5.7 — 2026-06-24 — Fix: public MCP server boots without enterprise

### Fixes

- **MCP server refused to boot on the public distribution** — even after the v0.5.6 import
  guards, `_critical_modules_or_die()` (the boot-time module check in `chuzom.server`) listed
  `chuzom.enterprise.{identity,rbac,quotas}` as critical and aborted startup when they were
  missing. Those modules are intentionally excluded from the public wheel/sdist, so
  `pip install`ed Chuzom still couldn't start its MCP server (`No module named
  'chuzom.enterprise'`). The enterprise modules are now split into a separate
  `_ENTERPRISE_CRITICAL_MODULES` tuple that is only verified under the enterprise profile
  (`is_enterprise()`); the universal check no longer requires them. Adds a regression test
  (`test_critical_module_check_boots_without_enterprise`). Together with v0.5.6 this makes the
  published package usable as an MCP server (verified end-to-end with an Agno agent calling
  `llm_query` through the Chuzom MCP server).

---

## v0.5.6 — 2026-06-24 — Fix: public package import without enterprise

### Fixes

- **Public distribution import crash** — `chuzom.server` / `chuzom.router` (and the `chuzom`
  MCP entrypoint) failed to import when installed from PyPI with
  `ModuleNotFoundError: No module named 'chuzom.enterprise'`. The `enterprise/` package is
  intentionally excluded from the published wheel/sdist, but five modules
  (`audit_routing`, `rbac_routing`, `admin_api`, `scim_api`, `commands/audit`) imported it at
  top level without a guard. These imports are now wrapped in `try/except ImportError` so the
  public package imports and routes cleanly; enterprise features remain gated behind
  `is_enterprise()`. Adds `tests/test_public_import.py`, which imports the core modules with
  `chuzom.enterprise` forced absent to prevent regressions.

---

## v0.5.5 — 2026-06-24 — Agentic model routing

### New features

- **`CHUZOM_AGENTIC_MODEL` / `agentic_model` routing pin** — designate a preferred model for
  agentic / tool-reasoning tasks (`analyze`, `generate`, `query`, `research`). When set, it is
  pinned at the absolute front of the routing chain for those task types — ahead of the generic
  Ollama injection and every other reorder — so a strong tool-calling model (e.g. Hermes) leads
  agent work. `CODE` is intentionally excluded so dedicated coder models still win coding tasks.
  Configure via the `CHUZOM_AGENTIC_MODEL` env var or the `agentic_model:` key in
  `~/.chuzom/routing.yaml` (env > repo > user precedence). Example:
  `CHUZOM_AGENTIC_MODEL=ollama/hermes3:8b`. The `agent-route` hook surfaces the pinned model in
  its route indicator.

### Fixes & docs

- **Ghost-model fix** — `auto_profile` no longer hardcodes `ollama/qwen3.5:latest` (and other
  example tags) into the free-local tier when those models are not installed. It now prefers the
  models actually discovered from the running Ollama instance, falling back to the example list
  only before discovery has run. Prevents routes to a model the user doesn't have.

---

## v0.5.4 — 2026-06-17 — PyPI metadata & discoverability improvements

### Improvements

- **PyPI metadata**: bumped classifier from `3 - Alpha` to `4 - Beta`; added keywords
  `claude`, `anthropic`, `ollama`, `token-optimization`, `cost-saving`, `quota-saver`,
  `ai-routing`, `llm-proxy`, `copilot`, `windsurf` for search discoverability.
- **Project URLs**: fixed `Bug Tracker` and `Changelog` links (previously pointed to
  personal fork instead of `Chuzom/Chuzom` org repo); added `Documentation` link.
- **Short description**: now mentions Cursor and Copilot explicitly alongside Claude Code.
- **README**: hero image now uses absolute GitHub URL — was previously broken on PyPI
  (relative `assets/` paths do not resolve in PyPI's renderer).

---

## v0.5.1 — 2026-06-14 — GitHub Copilot & Windsurf IDE support

### New features

- **`chuzom install --host copilot`** — installs full VS Code / GitHub Copilot pull-routing
  stack: user-level `~/Library/Application Support/Code/User/mcp.json`, workspace
  `.vscode/mcp.json`, `.github/copilot-instructions.md` (instructs Copilot to call
  Chuzom tools first), and `.github/agents/chuzom.agent.md` (Copilot agent with
  `tools: ['chuzom']` for strongest tool-first enforcement in Agent mode).

- **`chuzom install --host windsurf`** — installs Windsurf / Cascade pull-routing stack:
  global `~/.codeium/windsurf/mcp_config.json`, workspace `.windsurf/mcp.json`, and
  `.github/copilot-instructions.md` (also read by Windsurf).

- **`install_hooks.py ide` subcommand** — `python install_hooks.py ide` writes
  `.vscode/mcp.json`, `.windsurf/mcp.json`, and `.cursor/rules/use-chuzom.mdc` to the
  project root. `python install_hooks.py ide --uninstall` removes them.

### Architecture

- **Push vs pull routing** explained clearly in README: Claude Code uses push routing
  (hooks intercept 100% of prompts automatically); Copilot/Cursor/Windsurf use pull
  routing (model must choose to call the tool). IDE support matrix added.

- **`--host all`** now includes `windsurf` in the installation loop.

### Bug fixes

- `--host copilot` previously called `_print_vs_code_copilot_config()` (print-only);
  now correctly calls `_install_vscode_files()` which writes all config files.

---

## v0.5.0 — 2026-06-14 — Deep Reasoning tier (DeepSeek-R1 · o3 · Gemini thinking)

### New features

- **`RoutingProfile.REASONING` — dedicated 4th routing tier.** `Complexity.DEEP_REASONING` previously mapped to `PREMIUM` (identical chain to `complex`). It now maps to a dedicated `REASONING` profile with a cost-ordered chain prioritising native reasoning models:
  `ollama/qwen3.6:27b → deepseek/deepseek-reasoner → openai/o3 → gemini/gemini-2.5-pro → anthropic/claude-opus-4-6 → anthropic/claude-sonnet-4-6`.
  DeepSeek-R1 costs $0.0014/1K vs $0.04/1K for general frontier models — 28× cheaper for deep-reasoning tasks.

- **`llm_reason` MCP tool (6th text tool).** Always routes with `complexity="deep_reasoning"`. No caller-supplied complexity parameter — the tool always invokes the REASONING chain. Best for: formal proofs, mathematical derivations, step-by-step reasoning, root-cause analysis.

- **Gemini 2.5 Pro extended thinking via `thinkingConfig`.** When `use_thinking=True` (set automatically for `deep_reasoning` tasks), Gemini 2.5 Pro now receives `thinkingConfig: {thinkingBudget: 8192}` in addition to the existing Anthropic `thinking: {type: enabled, budget_tokens: 16000}` block. No temperature constraint is needed for Gemini (unlike Anthropic which requires `temperature=1`).

- **Expanded `COMPLEXITY_DEEP_REASONING` regex.** Natural-language chain-of-thought triggers added alongside the existing formal/academic vocabulary: `step by step`, `think through`, `walk me through the reasoning`, `chain of thought`, `root cause analysis`, `show your work`, `first principles`, and more. Same regex applied in both `auto-route.py` and the RouterArena submission router.

- **`CHUZOM_REASONING_TIMEOUT` env var (default: 300s).** Dedicated timeout for deep reasoning API calls. DeepSeek-R1 and o3 can take 60–300s for complex proofs; the existing `CHUZOM_REQUEST_TIMEOUT` (120s) was insufficient.

### Architecture SVG

- Hero diagram updated with a 4th tier card (purple, "🧠 Deep Reasoning") and animated routing dot.

### Migration notes

> **If you use `match profile:` with exhaustive case arms**, add a `case RoutingProfile.REASONING:` branch.
> The new value is the string `"reasoning"`. Code that passes `profile="reasoning"` to `ChuzomAgent` or `_resolve_profile()` will now correctly resolve to the REASONING chain rather than falling back to BALANCED.

### Internal

- `agno.py`: `_PROFILE_MAP` now includes `"reasoning": RoutingProfile.REASONING`.
- `memory/profiles.py`: `tool_to_task` map now includes `"llm_reason": TaskType.ANALYZE`.
- `tools/routing.py`: `valid_tools` set in `llm_reroute` now includes `"llm_reason"`.
- `release.py`: `_EXTRA_VERSION_FILES` now wires `tui/__init__.py` into the release script so its hardcoded `__version__` is never left behind.

---

## v0.4.2 — 2026-06-14 — Dashboard polish, inversion fix, routing signals

### Bug fixes

- **MODELS panel showed routing method names instead of model names.** Commit `dc0ccea` removed `tools_data = report_data.get("tools", {})` when refactoring `model_breakdown` to use a DB query, but left the block that still referenced it. The resulting `NameError` caused the Rich renderer to crash and fall back to a legacy path that populated `model_breakdown` with method names. Fixed by restoring the variable assignment.

- **UP-inversions reduced from ~16% to near-zero.** Complex tasks (deep analysis, code) were leading with Ollama in all pressure zones. Reordered `chain_builder.py` so `mid_externals` (GPT-4o, Gemini Pro) lead before Ollama for complex tasks in yellow/orange/red/critical zones.

- **DOWN-inversions eliminated for Codex/Gemini CLI.** `codex/*` and `gemini_cli/*` model prefixes were mapping to `Tier.MID/PREMIUM`, producing false DOWN-inversions when those free-subscription models handled simple tasks after Ollama failed. Now mapped to `Tier.CHEAP`.

### Dashboard

- **SAVINGS panel now shows token counts.** Each period (today, this week, this month, lifetime) shows `$X.XX label` on one line and `N tok` on the next in dimmed text.

### RouterArena classifier

- `failure modes?` added to `_COMPLEXITY_COMPLEX` so prompts asking to "cite failure modes" are correctly classified as complex analysis.
- `brief` removed from `_COMPLEXITY_SIMPLE` — it is a format instruction ("Keep it brief"), not a complexity signal; length-based classification handles the rest.
- `approach` removed from `analyze.topic` — too generic; appeared in ML explanation prompts ("each approach in a domain") causing false positives.

### CI

- All plugin manifests (`.claude-plugin`, `.codex-plugin`, `.factory-plugin`) synced to `0.4.2`.

---

## v0.4.1 — 2026-06-13 — CI fixes, session summary visible, deadline guard

### Bug fixes

- **Session summary now visible in Claude Code UI.** Root cause: `Console(record=True)` without `file=` defaults to writing to stdout AND recording simultaneously. Claude Code's Stop hook contract requires exactly one JSON line on stdout — anything else on stdout before the `{"systemMessage": ...}` line is silently discarded, causing the summary to never appear. Fixed by redirecting Rich to `io.StringIO()` (`file=_rich_buf`) so stdout stays clean for the JSON envelope. Colored output is saved to `~/.chuzom/last_summary.ansi` and visible via `cat ~/.chuzom/last_summary.ansi` or `chuzom summary` in a real terminal.

- **`test_min_cap_wins_when_both_set` deadline guard.** When a workflow deadline expires *during routing setup* (chain-build, idempotency check, budget lock acquisition) rather than during dispatch, the computed `_dl_remaining_at_dispatch` went negative. The `_effective_timeout > 0` guard then silently skipped `asyncio.wait_for`, running the dispatch coroutine without any timeout and never raising `DeadlineExceeded`. Fixed by adding a pre-dispatch deadline re-check that raises `DeadlineExceeded` immediately when remaining time ≤ 0 at dispatch entry. Test deadline increased from 50 ms to 500 ms to reliably exercise the `asyncio.wait_for` path.

- **`test_code_task_codex_after_first_claude_not_last` routing mock.** The test's `_selective_fail` mock only failed `anthropic/*` models, but the dynamic routing table for `(BALANCED, CODE)` starts with `ollama/qwen3.5:latest` before Claude. The Ollama model succeeded via the litellm mock, so the router returned before reaching Codex. Fixed by failing ALL litellm models so only `run_codex` (the Codex CLI path) can succeed.

- **Ollama models gated behind reachability probe.** `build_dynamic_routing_table` previously always added `ollama` to the available-providers set regardless of actual Ollama availability. Routing chains could include Ollama models that immediately timed out on every request. Now guarded by `probe_ollama()` (1-second HTTP check with 60-second TTL cache); Ollama only enters the chain when the server is reachable.

### Packaging

- Description updated to emphasize token savings and session preservation for Claude Code/subscription users.
- PyPI `Homepage`/`Repository` URLs corrected from `ypollak2/chuzom` to `Chuzom/chuzom`.
- README: added "For Claude Code / Claude Pro / Max Subscribers" section explaining 3× session extension.

### Linting

- Fixed all 16 ruff errors: F821 (missing `Callable`/`Awaitable` imports in `codex_agent.py` and `gemini_cli_agent.py`), F841 (unused `PLOT_LEFT` in `session_summary.py`), F401/F841 in test files.

---

## v0.3.0 — 2026-06-11 — Enterprise enforcement wired + honest packaging

> Closes the audit's anchor finding (INV-010): the enterprise control plane is now **wired into and enforced on the routing path** under `CHUZOM_DEPLOYMENT_PROFILE=enterprise`, and the packaging/README are reconciled to reality. The developer router stays stable; the enterprise control plane is labelled **beta** with a per-feature status table in the README.

### Enterprise control plane (now enforced under the enterprise profile)

- **INV-010 closed.** RBAC (`check_route_prompt` / `check_provider` / `check_model`) and the audit chain are consulted on every routed turn. The enterprise profile flips RBAC→strict, audit→mandatory, redaction→on, forecast→strict (G-001/G-003/G-012/G-016). End-to-end enforcement proof added.
- **Phase 3b — per-identity allow-lists.** The authenticated SSO/OIDC identity now carries `permissions` + per-identity `allowed_providers` / `allowed_models` from the `IdentityStore`, so a restricted token enforces through the wired gates. Empty lists normalise to `None` (unrestricted) — an empty allow-list can never silently deny-all.
- **Loop-5 / G-039.** `CHUZOM_DEPLOYMENT_PROFILE` deployment-profile detection back-ported into the auto-route hook; the self-reference bypass is refused under the enterprise profile.
- **G-029 agent ledger.** `SessionStore.recent()` / `cancel()` (cascade) / `record_tool_call()` + `last_activity_at`; admin agent status + cancel endpoints.

### Security

- **G-004 — RBAC allow-list prefix-spoof closed.** A forged `provider/forged-model` candidate could match a bare allow-list entry (the provider prefix was stripped before comparison). `check_model` now matches the full id exactly; the `provider/model` and bare forms never cross-match.

### Packaging & docs (P0-6)

- `chuzom --version` reports the **installed distribution's version** (installed wheels previously reported a stale hardcoded `10.1.2`).
- `chuzom install --host claude-code` / `--host claude-desktop` now resolve; generated MCP configs invoke the canonical `chuzom` stdio entry instead of the deprecated `uvx claude-code-chuzom` package.
- README rewritten concise + honest (806 → ~140 lines) with a real "How it works" section and a per-feature beta status table; the overclaimed SOC 2 / GDPR / OTEL badges were dropped.

### Known gaps (on the roadmap; labelled beta in the README)

- SCIM mounting + role/group mapping; team-budget enforcement; multi-instance (Postgres) HA; control-plane→routing wiring for provider-disable / policy-versioning; audit-chain verify CLI/endpoint.

## v0.2.0 — 2026-06-08 — Audit Tracks 1 & 2 + lineage API rewrite

> **Security advisory + claims reconciliation + honest test signal + lineage API rewrite.** This release closes the developer-focused subset of the 2026-06 internal audit (`Docs/audit/FINDINGS.md`): **2 Critical** and **6 High** findings across security defaults (SEC-001/002/003), session isolation (INV-007 + ROU-001), truth-in-claims (INV-001/002), and test-suite integrity (TST-001). It also lands the **v0.2.x `LineageStore` API rewrite** that was implicit in TST-001's follow-up. Multi-tenancy / identity-layer items (INV-010, INV-011, ROU-002, PRI-001, OBS-001, TST-003) are deferred to Phase 2 pending the multi-tenancy product decision.
>
> The two Critical findings (SEC-001, SEC-002) were exploitable with default settings. Operators running prior versions on a reachable network should review the mitigations below.

### Security

- **SEC-001 — Removed `chuzom-sse` console script (BREAKING).** Prior versions installed a `chuzom-sse` binary that, when invoked, bound `0.0.0.0:$PORT` and exposed the full 60-tool MCP surface — including filesystem tools, wallet, and routing controls — with **zero authentication**. The entry point has been removed from `pyproject.toml`. The `chuzom.server.main_sse` function is retained in source for future re-introduction behind proper authentication + identity (post-INV-010); attempting to re-add the entry point without an auth wrapper is now guarded by a regression test (`tests/test_no_chuzom_sse_entry_point.py`).
  - **Mitigation if you were running `chuzom-sse`:** stop the process, review any logs you have for unauthorised tool invocations during the exposure window, rotate credentials accessible from the host, and switch to the stdio transport (`chuzom`) until a hardened SSE wrapper ships.
- **SEC-002 — `llm_fs_*` tools are now opt-in and sandboxed (BREAKING).** Prior versions registered four filesystem tools (`llm_fs_find`, `llm_fs_rename`, `llm_fs_edit_many`, `llm_fs_analyze_context`) by default. `llm_fs_edit_many` accepted an arbitrary glob and read up to 32 KB per match into the model prompt; `llm_fs_edit_many(glob_pattern="~/.ssh/**")` was a one-call exfiltration vector. Two independent gates now apply:
  1. **Opt-in env.** Tools are registered only when `CHUZOM_FS_TOOLS=on` (or `1`/`true`/`yes`) is set. Without the opt-in, `mcp.list_tools()` exposes zero `llm_fs_*` entries.
  2. **`project_root` sandbox.** `llm_fs_edit_many` and `llm_fs_analyze_context` now require a `project_root` parameter. The root is resolved with `Path.resolve()` (closing the symlink-escape hole); paths that resolve outside it are rejected before any file read or route call. `project_root='/'` is refused outright.
- **SEC-003 — `agoragentic_*` MCP tools are now opt-in (BREAKING).** Prior versions registered four marketplace tools (`agoragentic_task`, `agoragentic_browse`, `agoragentic_wallet`, `agoragentic_status`) by default, even when `CHUZOM_SLIM=routing` was set. **`agoragentic_task` performs USDC settlement on the Base L2 blockchain** — it can spend real money via the credentials stored at `~/.chuzom/agoragentic.json`. An LLM agent enumerating tools, an MCP client probing the tool list, or a hallucinated tool call could trigger an unintended on-chain transaction. The four tools are now gated behind `CHUZOM_AGORAGENTIC=on` (or `1`/`true`/`yes`). Without the opt-in, `mcp.list_tools()` exposes zero `agoragentic_*` entries.
- **INV-007 / ROU-001 — Per-session classification side channel (BREAKING).** The auto-route hook previously wrote a shared `~/.chuzom/last_classification.json` that every MCP server on the machine read from. Two failure modes: (1) two Claude Code sessions raced on the same file (whoever fired last set the verdict for both); (2) any same-user process could forge a classification within the 120 s freshness window. The hook now writes `~/.chuzom/last_classification_<session_id>.json` and the MCP reader pins to `CLAUDE_SESSION_ID` from the env that Claude Code injects when it spawns the MCP server. A belt-and-braces inner-payload check rejects shards whose inner `session_id` doesn't match the env. The legacy shared file is no longer written or read; consumers that still look for it gracefully return `None` and fall back to the length heuristic.

### Truth-in-claims

- **INV-001 — Pre-existing self-audit rescoped, not retracted.** `AUDIT_FINDINGS.txt` and `CHUZOM_AUDIT_REPORT.md` (both dated 2026-06-07, narrow lineage-subsystem reviews) previously stamped the project as "✅ APPROVED FOR IMMEDIATE PRODUCTION DEPLOYMENT" with 5★ ratings across the board. The 2026-06-08 comprehensive audit identified 3 Critical, 11 High, 11 Medium, 3 Low findings and scored enterprise-readiness at 1.65 / 5 — the prior claims were a scoping error, not a measurement of the whole project. Both files now carry a top-of-document scope notice, every overclaiming line is contextualised to "lineage subsystem only", and the documents point at `Docs/audit/` as the authoritative whole-project assessment. The lineage subsystem verdict (production-ready as a subsystem) is preserved.
- **INV-002 — README hero reconciled with `pyproject.toml` Alpha status.** The README first paragraph previously read "The enterprise-ready LLM router for developer organizations." while `pyproject.toml` classified the project `Development Status :: 3 - Alpha`. The hero now describes the project as "Local-first LLM router for developer workstations" and adds a maturity line stating that the developer-tool layer is the production path today (alpha per `pyproject.toml`) and the enterprise control plane (RBAC, tamper-evident audit chain, per-user / per-team budgets, OpenTelemetry export) is scaffolded but not yet wired into the routing path (`INV-010`). The reader of the first 30 lines of README and the first 20 lines of `pyproject.toml` now arrives at the same maturity conclusion.

### Testing

- **TST-001 — Un-skipped 9 silently-excluded test suites.** `tests/conftest.py:collect_ignore` had dropped 206 tests at collection time, including integrity, performance, observability, session-summary rendering, framework scenarios, and lineage roundtrips. The original justification (lineage symbols missing) was stale — PR #10 restored the exports but the exclusion list was never cleaned up. The README's "766 tests passing" badge ran against a suite that hid these. `collect_ignore` is now empty (every test file is collected); the residual failures all share one root cause (`LineageStore(db_path=...)` signature drift, fixed below in the lineage rewrite) and were individually marked via `_KNOWN_BROKEN_TESTS` with reasons that show up in `pytest -v`. New meta-test `tests/test_no_silent_collect_ignore.py` guards against future silent-exclusion regressions.

### Lineage API rewrite

- **`LineageStore` — dual-keyword constructor + planned `LineageRecord` write/query surface.** PR #16 (TST-001) exposed ~30 tests across 8 files that referenced a `LineageStore` API never implemented. That API now exists, additively:
  - **Constructor** (`__init__`) accepts both `router_dir` (directory, production shape — every `src/` caller hits this) and keyword-only `db_path` (specific SQLite file, test shape). Passing both raises `ValueError`. Production callers are unchanged — none used either keyword pre-rewrite.
  - **New `lineage` SQLite table** parallel to the existing `routing_decisions` table; mirrors `LineageRecord.to_row()` (22 columns including agent_id / session_id / step_index / parent_session_id / framework). Forward-compatible migration: if a pre-v0.0.2 DB is opened with a lineage table that lacks the agent-session columns, `_init_db` `ALTER`s the table to add them.
  - **New methods**: `record(LineageRecord)` writes to JSONL + the new table; `inversions(kind=None)` filters by `Inversion` enum; `summary()` aggregates total / up / down / none + inversion_rate; `by_session(session_id, agent_id=None)` returns rows ordered by step_index; `by_framework(slug)` returns rows matching the framework column; `close()` is a no-op symmetry shim.
  - **Result**: 14 `_KNOWN_BROKEN_TESTS` entries removed from `conftest.py`; the previously-skipped suites now contribute **~350 newly-visible passing tests** to coverage. Total: `tests/test_lineage.py` + `tests/qa/` + `tests/scenarios/` go from 116 → **470 passing** with 0 failures.

### Breaking changes

- The `chuzom-sse` console script no longer exists. Use the stdio transport (`chuzom`) until an authenticated SSE wrapper ships.
- `llm_fs_edit_many` now requires `project_root: str` as a positional argument (was previously sandbox-less).
- `llm_fs_analyze_context` renamed its first argument from `path` (default `"."`) to `project_root` (required). The previous default that quietly analysed the process cwd is gone.
- `llm_fs_*` tools are NOT registered unless `CHUZOM_FS_TOOLS=on` is set.
- `agoragentic_*` tools are NOT registered unless `CHUZOM_AGORAGENTIC=on` is set.
- The hook → MCP classification bridge moved from `~/.chuzom/last_classification.json` to per-session shards `~/.chuzom/last_classification_<session_id>.json`. Consumers that still target the legacy filename will see no data (and the router will fall back to its length heuristic, which is the correct conservative default).

### Added

- `tests/test_no_chuzom_sse_entry_point.py` — 3 regression tests guarding SEC-001.
- `tests/test_fs_path_validation.py` — 26 tests covering the SEC-002 env gate and sandbox helpers (`_resolve_root`, `_assert_under_root`, `_filter_files_under_root`), including symlink-escape and absolute-path-outside-root cases.
- `tests/test_agoragentic_opt_in.py` — 18 regression tests covering the SEC-003 env-gate truth table.
- `tests/test_classification_side_channel_isolation.py` — 12 tests covering session isolation, adversarial forgery (ROU-001), inner-payload mismatch, staleness, and malformed-input resilience.
- `tests/test_no_silent_collect_ignore.py` — 2 meta-tests asserting `collect_ignore` stays empty and every `_KNOWN_BROKEN_TESTS` entry carries a reason.
- `chuzom.tools.fs.FsSandboxError` — raised when a path escapes the configured `project_root`.
- `chuzom.lineage.LineageStore.{record, inversions, summary, by_session, by_framework, close}` — planned-API methods for writing and querying `LineageRecord` instances.
- `lineage` SQLite table — parallel to `routing_decisions`; mirrors `LineageRecord.to_row()` with forward-compatible migration of pre-v0.0.2 schemas.
- Security notice docstrings on `chuzom.server.main_sse`, `chuzom.tools.fs.register`, and `chuzom.tools.agoragentic.register` explaining the threat model and the conditions under which the prior behaviour may be reintroduced.

### Notes for operators

- Anyone who was relying on the default-on filesystem tools must add `CHUZOM_FS_TOOLS=on` to their environment AND pass `project_root` on every call.
- Anyone who was intentionally using the Agoragentic marketplace must add `CHUZOM_AGORAGENTIC=on` to the environment that launches the MCP server. The credentials file at `~/.chuzom/agoragentic.json` is unchanged.
- **If you discover unauthorised on-chain activity from `~/.chuzom/agoragentic.json`'s `agent_id` predating this release:** rotate the API key, revoke the agent, and review settlements on the Base L2 explorer. The pre-fix default was exploitable.
- Symlink escapes are now closed because path validation runs after `Path.resolve()`, not against the raw user-supplied string.
- The full audit context — including findings' file:line evidence and the rejected alternatives — lives in `Docs/audit/HIGH_PRIORITY_WORK_PLAN.md` and `Docs/audit/FINDINGS.md`.

### Phase 2 (parked pending multi-tenancy product decision)

- `INV-010` (identity → routing → audit chain wiring), `INV-011` + `TST-003` (per-identity budgets + concurrency tests), `ROU-002` (per-tenant routing tables), `PRI-001` (redaction in routing path), `OBS-001` (tenant/user/agent fields in logs). All blocked on `Q-P-2` in `Docs/audit/OPEN_QUESTIONS.md`.

---

## v0.1.1 — Stop misrouting display-intent prompts to llm_code

> **Patch release.** Targets the most common "Chuzom appears stuck" experience: trivial follow-ups like `show me the report` issued after code-heavy turns were being classified `code/moderate` via `code-context-inherit`, then forced through `mcp__chuzom__llm_code` — an external LLM that can't read local files. The tool would spin for 2-4 minutes before the user cancelled. No actual hang; just a misroute taking the slow path that couldn't help anyway. Full analysis in [`STUCK_PATTERNS_ANALYSIS.md`](./STUCK_PATTERNS_ANALYSIS.md).

### Added
- **Display-intent override** (`auto-route.py`) — `_DISPLAY_INTENT_RE` matches short prompts (≤100 chars) starting with `show`/`display`/`view`/`read`/`cat`/`print`/`list`/`open`/`see` followed by a display target (`the/my/this/<file>.md/report/file/output/log/diff/...`). Such prompts always route to `llm_query` regardless of inherited context, tagged `intent-override-display` for telemetry. Does **not** save to `last_route` so subsequent genuine code follow-ups still inherit the prior code context correctly.
- **`STUCK_PATTERNS_ANALYSIS.md`** — comprehensive 4-mode taxonomy of perceived "stuck" events across Claude Code CLI, VS Code/JetBrains extensions, Cursor/Windsurf, and Claude.ai web. Includes evidence trail from `auto-route-debug.log` + the d4cd6a72 session transcript, defense-gap matrix, prioritised fix list, and an instrumentation patch proposal for catching the next one.
- **`tests/test_display_intent_override.py`** — 41 cases covering positive matches, negative matches against real code-generation prompts (`show me a function that…`), length-cap behaviour, and source-integration smoke check that asserts the override branch remains wired.

### Changed
- **Continuation bypass narrowed to strict acks** (`auto-route.py`) — the early UserPromptSubmit bypass at `chuzom-auto-route.py:1988` now triggers only on strict `_CONTINUATION_RE` matches (single-word `yes`/`ok`/`go ahead`/etc.), not the broader `_is_short_followup` union. Multi-word directives like `please go ahead and do the change` after a code task now fall through to the classification block instead of silently exiting with no output. Behaviour change: prompts starting with `please`/`now`/`let's` no longer bypass — they're routed normally.
- **Classification branch order** (`auto-route.py`) — `_is_short_code_followup` is now checked **before** `_is_continuation` so short follow-ups after code tasks get the specific `code-context-inherit` telemetry tag instead of the generic `context-inherit`. Routing destination is functionally identical; observability is sharper.
- **`LineageStore` exported from `chuzom.lineage`** — adds `LineageStore` to `chuzom/lineage/__init__.py`'s `__all__` so `chuzom.tools.agents` (and the 5 QA-suite test modules) can import it without `ImportError`. Class existed in `lineage_store.py`; export was missing.
- **Live-hook tests find the renamed file** (`tests/test_auto_route_fix_verb.py`) — `_find_live_hook()` helper checks `~/.claude/hooks/chuzom-auto-route.py` first, falls back to legacy `llm-router-auto-route.py`. Resolves post-rebrand test drift where v0.0.2 fix-pattern assertions still pointed at the pre-rebrand binary path.

### Fixed
- **Silent hook exit on multi-word follow-ups** — `test_short_followup_after_code_inherits_code` was failing because the broad bypass swallowed prompts like `please go ahead and do the change now`. Now correctly emits the `code-context-inherit` routing directive.
- **Perceived 2-4 minute hangs on display-intent prompts** — the misroute path is closed at the classifier. `show me the report` after a code-heavy session now routes to `llm_query` (cheap, fast) instead of `llm_code` (slow external LLM that can't help).

### Internal
- 41 new regression tests in `test_display_intent_override.py`; 198/198 passing across `test_auto_route_*` + `test_display_intent_override` + `tests/lineage/` suites.

---

## v0.1.0 — Stability promise + first benchmark numbers + brand sweep

> **First stable-shape release.** The 0.0.x phase shipped fast and broke things on the way; 0.1.0 commits to:
> - SQL schema migrations land via `_safe_migrate` (idempotent ALTER TABLE) — no destructive resets.
> - Public CLI entry points (`chuzom`, `chuzom-install-hooks`, `chuzom-onboard`, `chuzom-quickstart`, `chuzom-sse`) and MCP tool names (`llm_*`, `chuzom_agent_*`) are frozen. Removals will go through a deprecation cycle in 0.2.x.
> - Enforcement mode names (`off`, `soft`, `smart`, `hard`, `strict`) are stable.
> - SQLite database file paths (`~/.chuzom/{usage,lineage,sessions,quotas,audit}.db`) are stable.

### Added
- **First end-to-end benchmark numbers** — ran `python -m bench --easy-only` against the smoke corpus (5 prompts × 4 routers). On objective easy prompts, Chuzom matches AlwaysCheap (q=2.60, $0.00 spend) — proves the heuristic-first cascade routes correctly when no escalation is warranted. AlwaysPremium errored on OpenAI rate limit, so cost-vs-quality Pareto vs GPT-4o isn't measurable yet; see `bench/results/20260606-150229.{json,md}` for the raw data.
- **`scripts/verify_chuzom_hooks.sh`** — end-to-end verifier that pipes representative payloads into the installed hooks (`~/.claude/hooks/chuzom-*.py`) and asserts the production code paths contain the live brand + enforcement logic. 11 checks; run after every reinstall.
- **`scripts/backfill_sidecars.py`** — replays `~/.chuzom/last_route_*.json` sidecars (written by `auto-route.py` when a directive fires) into `routing_decisions`. Idempotent via stable `correlation_id` (`sidecar:<session>:<saved_at>`). Sidecars carry intent only, so rows land as `success=0, reason_code='sidecar_backfill'`.
- **`token_budget.count_tokens(text, model=None)`** — accurate per-model token counting via tiktoken when available; falls back to `chars/4` when tiktoken is missing, the model is unknown, or encoding load fails. Used by cost-attribution paths (`tools/codex.py`, `tools/gemini_cli.py`); hot-path budget checks keep `estimate_tokens()` for speed.
- **`CHUZOM_ENFORCE=strict`** — new enforcement mode that disables every escape valve: the read-only Bash exception (smart mode allows `git log`/`ls`), the loop auto-pivot (3× same tool in 2 min → unblock), and the count auto-pivot (4 violations/turn → unblock). Use when bypass discipline matters more than uninterrupted flow.
- **Outcome-stamped enforcement log** — every VIOLATION line in `~/.chuzom/enforcement.log` now carries `outcome={BLOCKED, BLOCKED(strict), ALLOWED(soft), ALLOWED(readonly_bash)}` so the log is self-explanatory without source reads.
- **Schema bootstrap in `tools/admin.py:llm_usage`** — fresh / 0-byte `usage.db` now renders the empty-state UI instead of erroring with `no such table: usage`. Matches the resilience already in `dashboard_data.py`.

### Changed
- **Full brand sweep**: 37 source files (`.py` + `rules/*.md`) swept from `LLM Router` → `Chuzom` / `LLM ROUTER` → `CHUZOM`. Stop summary header now renders `⚡ CHUZOM`; dashboards, digests, install messages, web TUI, and routing rules are all consistent. Routing rules file regenerated as `chuzom-rules-version: 5`.
- **Cyber-grid Stop summary layout** — long classifier names (`code-context-inherit` at 20 chars, `content-generation-fast-path` at 28 chars) were rendered with `f"{name:<16}"` which pads but doesn't truncate, so labels bled into the SAVINGS column on the right. Adds method-name aliases (`build-fast`, `ctx-inherit`, `content-gen`, `heuristic·w`) plus a 16-char hard truncation guard so future classifier names can't reintroduce the overflow.

### Fixed
- **`outcome=BLOCKED` actually means blocked.** Pre-0.1.0, VIOLATION lines in `enforcement.log` left the disposition (blocked vs auto-pivot-allowed vs soft-mode-allowed) implicit — readers had to know the source to disambiguate. Now every exit path stamps its own outcome.

### Known gaps (will be addressed in 0.1.x)
- Easy-only benchmark can't differentiate routers (all classify as `simple` → all route to local). Moderate-corpus run with judge-grading is needed to show the classifier's value. Deferred until empty-response detection lands.
- Empty-response from local model (`ollama/qwen3.5`) on 3 of 5 easy prompts does NOT trigger cascade — the router silently returns the empty string instead of escalating. Tracked.
- AlwaysPremium baseline requires a working `OPENAI_API_KEY`; smoke run hit rate-limit. Cost-savings vs GPT-4o not yet measurable. Workaround: use `litellm`-routed Sonnet via Claude subscription as the premium baseline.
- `__version__` in `src/chuzom/__init__.py` is set to `10.1.2` (internal numbering); `pyproject.toml` is the public version source. Sync drift to be resolved.

### Internal
- 15 new regression tests covering: schema bootstrap, sidecar backfill (7 tests), strict enforcement (4 tests), cyber-grid layout (2 tests), token counting (6 tests). Full suite green at v0.1.0 cut.

---

## v0.0.2 — Agent layer + framework adapters + benchmark harness

### Added
- **`chuzom/agents/` module** — agent-aware routing without owning the agent loop.
    - `AgentProfile` dataclass — tier preference, signal boosts, preferred chain, budget envelope.
    - `AgentRegistry` — YAML-loaded (`config/agents.yaml`); 3 default profiles ship: `code-reviewer`, `trend-researcher`, `tdd-guide`.
    - `AgentSession` + `SessionStore` — SQLite-backed at `~/.chuzom/sessions.db`. State machine: ACTIVE → COMPLETED / ERRORED / BUDGET_EXCEEDED. Nested sessions via `parent_session_id` with full descendant `rollup`.
    - `BudgetEnvelope` + `BudgetExceeded` — immutable envelope, pre-emptive `would_exceed`, raise-or-pass `raise_if_would_exceed`.
- **`chuzom/tools/agents.py`** — 6 MCP tools:
    - `chuzom_agent_list` / `chuzom_agent_start_session` / `chuzom_agent_check_budget` / `chuzom_agent_route` / `chuzom_agent_complete_session` / `chuzom_agent_lineage`.
    - Budget enforcement at the route boundary — sessions refuse calls that would breach.
- **`chuzom/frameworks/` module** — adapter shape for agent frameworks.
    - `FrameworkAdapter` protocol (3 methods: `wrap_model`, `detect_agent_id`, `is_available`).
    - **Agno** — concrete, re-exports `RouteredModel` + `RouteredTeam` from `chuzom.integrations.agno`.
    - **Hermes** — skeleton; v0.0.3 lands the concrete tool-use protocol.
    - **LangGraph / CrewAI / OpenAI Agents SDK / Claude Agent SDK / Pydantic AI** — adapter stubs.
- **Lineage schema extension** — 5 new optional columns: `agent_id`, `session_id`, `step_index`, `parent_session_id`, `framework`. Idempotent migration handles pre-v0.0.2 databases via `ALTER TABLE ADD COLUMN` with duplicate-column guard. New indexes on `session_id` and `agent_id`.
- **Decision engine boosts** — `DecisionEngine.choose(scores, boosts={"signal": multiplier})`. Applied as score multipliers; thresholds untouched; scores clamped to [0,1]. Evidence annotated so lineage shows the boost was active.
- **`bench/` benchmark harness** — router-agnostic head-to-head comparison.
    - `Router` protocol — any router that returns `RouterResult` competes.
    - Built-in routers: `ChuzomRouter`, `FixedModelRouter` (cheap/premium endpoints), `StaticChainRouter` (ablation).
    - Hybrid judge: deterministic substring grading for objective prompts, LLM-as-judge for subjective.
    - Pareto frontier — only routers worth picking from at any quality budget.
    - Smoke corpus (5 easy + 5 moderate).
- **Local installability** — `pip install -e .` now works cleanly. CLI binary `chuzom`, `chuzom doctor`, full subcommand surface verified.

### Changed
- `chuzom/cache/` package now re-exports legacy `get_cache` / `ClassificationCache` from `cache/classification.py` (moved from `chuzom/cache.py`) alongside the new `SemanticCache` skeleton.
- `LineageRecord` gained 5 nullable fields. Existing call sites unchanged; new fields default to `None`.
- `make_record()` accepts optional `agent_id`, `session_id`, `step_index`, `parent_session_id`, `framework` keyword args.

### Tests
- **112 passing** (51 new for v0.0.2: 35 agent tests, 11 decision-boost tests, 5 framework smoke tests via tools).
- Coverage: budget envelope (consume / would_exceed / raise patterns), session lifecycle (create / record_step / complete / error / nested rollup), registry (YAML loader, duplicate-id rejection, default-template parse), MCP tool surface (refuse on breach, clamp to hard_max, unknown-agent error shapes), decision boosts (clamp to [0,1], priority preserved, evidence annotated).

### Deferred to v0.0.3+
- Hermes adapter concrete implementation (pending tool-use format decision).
- LangGraph / CrewAI / OpenAI Agents SDK / Claude Agent SDK / Pydantic AI concrete adapters.
- Embedding signal (`sentence-transformers/all-MiniLM-L6-v2`).
- Semantic response cache (`sqlite-vec` backend).
- `chuzom_agent_route` wiring to `chuzom.router.route_and_call` (currently returns `would_route: true` + step metadata; caller dispatches).
- Empirical `quality_gap` + `handoff_penalty` lookup tables deriving from lineage outcomes.

---

## v0.0.1 — Genesis (private fork from llm-router)

### Added
- Forked llm-router → chuzom. Package renamed, CLI binary renamed, all internal references updated.
- New module skeletons: `chuzom/signals/`, `chuzom/decisions/`, `chuzom/cache/`, `chuzom/hosts/`, `chuzom/lineage.py`.
- Config template at `config/signals.yaml` defining the v0 signal/decision DSL.
- Architecture design at `Docs/ARCHITECTURE.md` (local-only, gitignored).

### Carried over from llm-router
- Multi-provider routing chain (Ollama → Codex → cheap API → premium).
- MCP server + tool surface (`llm_query`, `llm_research`, `llm_analyze`, `llm_code`, `llm_generate`, `llm_image`, `llm_orchestrate`).
- Hooks system (auto-route, enforce-route, session-end, usage-refresh).
- Cost tracking + circuit breaker per provider.
- Caveman mode for token-efficient output.

### Deferred to v0.2+
- Full implementation of signal/decision engine (v0 ships scaffolding only).
- Semantic response cache backed by sqlite-vec.
- Empirical lookup tables (quality_gap, handoff_penalty).
- Reask, fact-check, reasoning-effort signals.
