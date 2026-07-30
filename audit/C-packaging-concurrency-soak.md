# AUDIT-C: Packaging, Concurrency & DB Integrity, Soak — Evidence Report

**Scope:** Phase 12 (packaging), Phase 11 (concurrency & DB integrity), Phase 10 (soak).
**Checkout audited:** local, `/Users/yaliandrona/Projects/Chuzom` (commit `f5bf55c`; no GitHub clone performed).
**Reference interpreter:** `/Users/yaliandrona/Projects/Chuzom/.venv/bin/python`.
**Hermeticity:** every test below redirects `HOME` to a fresh `tempfile.mkdtemp()` directory before importing any `chuzom` module. The real `~/.chuzom` and `~/.claude` were never read or written by any test in this report. Tmp dirs are named and left on disk for inspection (paths given per-test below).

---

## 1. Packaging (Phase 12)

### 1.1 Wheel build / clean-venv smoke — PASS (carried over, unchanged this segment)
Build via `hatchling`, install into a fresh venv, `chuzom --version` / `chuzom verify` / core module imports all succeeded. No new packaging build issues surfaced this segment.

### 1.2 `chuzom verify` exit-code propagation — CONFIRMED ALREADY FIXED (not a current defect)
Prior segments (working from transcript-recovered audit narrative) treated "`chuzom verify` always exits 0" as an open finding under the ID `CHZ-PKG-005`. A direct read of the current source this segment disproves that:

```python
# src/chuzom/cli.py, lines 929-935
elif args and args[0] == "verify":
    # CHZ-PKG-005: propagate verify's exit code. main() returns 1 when any
    # health check fails; discarding it made `chuzom verify` always exit 0,
    # so a CI/install gate keying on the exit code treated a broken install
    # as healthy.
    from chuzom.commands.verify import main as _verify_main
    sys.exit(_verify_main(args[1:]))
```

`chuzom audit` (line ~936) and `chuzom gc` (line ~942) follow the identical `sys.exit(_x_main(...))` pattern, indicating exit-code propagation was fixed across multiple subcommands, not just `verify`. **CHZ-PKG-005 is excluded from `findings-C.json`** — it is not a current, open defect in this checkout. This correction supersedes anything said about it in earlier report drafts.

### 1.3 `chuzom verify`'s hook check is stale relative to the real install manifest — OPEN, source-confirmed this segment
`check_hooks()` in `src/chuzom/commands/verify.py` (lines 158-183) hardcodes a 3-item list:
```python
hook_names = [
    "chuzom-auto-route.py",
    "chuzom-session-end.py",
    "chuzom-enforce-route.py",
]
```
The actual install manifest in `src/chuzom/install_hooks.py` (both the `HOOKS`/legacy-alias table around lines 309-324 and the Claude-Code-specific table around lines 338-350) deploys **13 hooks**: `chuzom-session-start.py`, `chuzom-auto-route.py`, `chuzom-status-bar.py`, `chuzom-enforce-route.py`, `chuzom-agent-route.py`, `chuzom-subagent-start.py`, `chuzom-usage-refresh.py`, `chuzom-cc-usage-track.py`, `chuzom-agent-depth-release.py`, `chuzom-playwright-compress.py`, `chuzom-bash-compress.py`, `chuzom-context-capture.py`, `chuzom-session-end.py`. `check_hooks()` only checks 3 of these 13 — the other 10, including `session-start`, `status-bar`, `agent-route`, `subagent-start`, `usage-refresh`, `cc-usage-track`, `agent-depth-release`, and both compress/context-capture hooks, are never checked at all. See §1.2 below and `findings-C.json` (`CHZ-AUD-C-04`).

### 1.4 IDE workspace-config writers use `Path.cwd()`, not a target-project argument — OPEN, source-confirmed this segment
`src/chuzom/cli.py` writes IDE integration files relative to the **current working directory**, not any explicit target path:
```
233: workspace_mcp = Path.cwd() / ".vscode" / "mcp.json"
245: github_dir    = Path.cwd() / ".github"
406: workspace_mcp = Path.cwd() / ".windsurf" / "mcp.json"
418: github_dir    = Path.cwd() / ".github"
463: workspace_mcp = Path.cwd() / ".kimi" / "mcp.json"
475: kimi_md       = Path.cwd() / "KIMI.md"
```
Running `chuzom install`/`setup` from inside the actual Chuzom repo checkout (a very plausible scenario for a developer working on Chuzom itself, or any user who happens to `cd` into a git repo before running the installer) will read/write `.vscode/mcp.json`, `.windsurf/mcp.json`, `.kimi/mcp.json`, `.github/`, and `KIMI.md` inside that real repo/project — not a sandbox. See `findings-C.json` (`CHZ-AUD-C-05`).

---

## 2. Concurrency & DB Integrity (Phase 11)

### 2.1 Budget backend (SQLite, WAL) — PASS, freshly re-confirmed this segment
`test_budget_multiprocess.py`, 10 real OS processes x 40 calls/proc = 400 concurrent `reserve`/`release` calls against a shared SQLite budget DB (WAL mode, `busy_timeout=5000ms`, `isolation_level=None`, retry-on-`SQLITE_BUSY`), cap = $0.20, cost/call = $0.001 → 200 calls should succeed, 200 should be correctly rejected once the cap is hit.

```
processes=10 calls/proc=40 total_calls=400
cap=$0.2 cost/call=$0.001 expected_success=200
per_proc_success=[40, 14, 10, 29, 25, 37, 29, 8, 4, 4]
total_success=200  (expected 200)
lock/busy errors surfaced to caller: 0
final pending_usd=0.200000 (expected 0.200000)
final consumed_usd=0.000000 (expected 0.0)
elapsed=0.22s
RESULT: PASS
```
Exact expected success count, no `SQLITE_BUSY` leaked to any caller, correct final ledger totals. The budget backend's concurrency primitives are sound under real cross-process contention.

### 2.2 Session-store lost-write race — **FAIL, real data-loss race, freshly re-confirmed this segment** (headline finding)
`test_session_store_concurrency.py`: 6 real OS processes each call `session_store.record_event()` 200 times (1200 total) against the **same** `session_id`, with unique content per write (so the legitimate consecutive-duplicate dedupe never fires) and, after every write, immediately re-scan the file for their own just-written marker. Production compaction thresholds (`_MAX_RECORDS=300`, `_COMPACT_TO=150`) are left at default, guaranteeing several organic compaction cycles mid-run while other processes are actively appending — i.e., this exercises "cleanup running during an active session" for real, not synthetically.

Fresh run this segment, executed with `HOME` redirected to `/var/folders/.../chuzom-audit-c-home-n4k25glc`:
```
processes=6 iters/proc=200 total_writes=1200
(production thresholds: _MAX_RECORDS=300, _COMPACT_TO=150 -- expect multiple organic compactions)
  [proc 0] LOST 2/200 -- seqs (first 20): [58, 159]
  [proc 1] LOST 5/200 -- seqs (first 20): [113, 142, 168, 169, 197]
  [proc 2] LOST 5/200 -- seqs (first 20): [51, 78, 105, 154, 155]
  [proc 3] LOST 2/200 -- seqs (first 20): [118, 170]
  [proc 4] LOST 4/200 -- seqs (first 20): [47, 100, 129, 184]
  [proc 5] LOST 4/200 -- seqs (first 20): [72, 98, 151, 175]

final_line_count=253 corrupt_lines=0
total_attempted=1200 total_lost_via_readback=22
elapsed=0.18s
RESULT: FAIL
```
**22/1200 writes (1.83%) lost.** Each loss is a write that `record_event()` returned from normally (no exception raised to the caller) but which is not present anywhere in the final file, confirmed by an independent structural-integrity re-scan performed by the harness process itself (not just the writer's own claim).

`corrupt_lines=0` is a load-bearing detail: every line present in the final file is well-formed JSON. This rules out torn/interleaved writes (two processes' `write()` calls physically clobbering each other mid-line) as the mechanism. It is consistent with an inode-orphaning race in `_maybe_compact()`: `record_event()` calls `_maybe_compact()` inline after every append; compaction rewrites the file to a tempfile and `os.replace()`s it over the original path. If another process's file handle was opened against the pre-replace inode and its `write()` lands *after* the `os.replace()` has already unlinked that inode from the visible path, the write succeeds (no exception) but is invisible in the file anyone reads via the path afterward — exactly the observed signature (clean exit, no exception, no corruption, silently missing content). `session_store.py` has no explicit lock (file lock, `asyncio.Lock`, or OS-level advisory lock) around `record_event()`/`_maybe_compact()`, unlike the budget backend's SQLite WAL + retry discipline in §2.1.

**This is the headline concurrency/DB integrity finding for this audit.** See `findings-C.json` (`CHZ-AUD-C-01`).

### 2.3 aiosqlite / daemon-thread-at-exit coverage
Not independently re-verified this segment (carried over as pending from prior segments). Marked **UNABLE TO VERIFY** in this report rather than asserted either way.

---

## 3. Soak (Phase 10)

### 3.1 Design
`soak_driver.py` runs `chuzom.router.route_and_call()` **sequentially** (not concurrently) against a monkeypatched `_call_text` (no real network call, no real API key) for a fixed 210-second wall-clock budget, with `model_override="openai/gpt-4o-mini"` (chosen specifically so the real RBAC/quota/deadline-preflight/P1-7 token-reservation path executes against a non-local provider — `reserve_tokens`/`release_tokens` are a no-op for `LOCAL_PROVIDERS` members like `ollama`). It samples RSS, thread count/names, open-FD count, and `budget._pending_tokens` every 25 iterations, and checks `_pending_tokens['openai'] == 0` after every single call (drift detector).

### 3.2 Results — completed cleanly per the script's own ALL_CLEAN criteria
```
=== SOAK SUMMARY ===
wall_clock_seconds=210.03 (target 210.0)
iterations_completed_N=5418
n_ok=5418 n_err=0
fake_call_text_invocations=5418 (expected == N == 5418; ratio 1.000)
models_seen_by_fake={'ollama/qwen2.5-coder:7b', 'openai/gpt-4o-mini'}
errors (first 20): []
total_errors_including_drift=0

rss_maxrss: start=213106688 end=230883328 delta=17776640
threads: start=1 end=2 delta=1
fds: start=10 end=15 delta=5
end thread names: ['MainThread', 'asyncio_0']

ALL_CLEAN=True
```
5418 sequential `route_and_call` invocations, 0 errors, 0 pending-token drift events, exactly 1 `_call_text` invocation per iteration (no duplicate dispatch at soak scale — see §3.4 for a related but distinct behavior seen only in the shorter smoke test), and modest/stable resource deltas (~17.8 MB RSS growth over 5418 iterations, +1 thread settling at 2 total, +5 FDs) consistent with normal asyncio-loop steady state rather than a leak. **No memory, thread, or file-descriptor leak of concern was observed.**

### 3.3 Significant new discovery: `model_override` is silently overridden by the quality-feedback circuit breaker
`soak_full_run.log` shows: the first 3 iterations dispatch directly to `openai/gpt-4o-mini` as requested (`routing_decision ... model=openai/gpt-4o-mini provider=openai`). Starting at iteration 4, **every remaining iteration (5415 of 5418, 99.94%)** instead logs:
```
Skipping low-quality model for generate/moderate: openai/gpt-4o-mini
model_quality_skip ...
Primary balanced chain exhausted, attempting BUDGET emergency fallback
emergency_fallback_success ... fallback_model=ollama/qwen2.5-coder:7b
```
`fallback_model=` is **exclusively** `ollama/qwen2.5-coder:7b` for all 5415 substituted calls (grep counts: `model_quality_skip`=5415, `emergency_fallback_success`=5415, `route_start`=5418). No exception is raised, no warning is surfaced to the caller, and `resp.model`/`resp.provider` on the returned `LLMResponse` reflect the actual (substituted) model — the caller receives a normal-looking successful response from a completely different model/provider than the one it explicitly requested via `model_override`.

**Root cause, confirmed by direct source read of `src/chuzom/router.py` and `src/chuzom/quality_feedback.py`:**
- `_build_and_filter_chain()`'s docstring explicitly promises: `model_override: If set, use only this model` (line 342), and its implementation returns `[model_override]` — a single-element candidate list (line 387).
- That single-element list is then run through the *same* per-model dispatch loop as any dynamically-built chain, including an unconditional quality-feedback gate (lines 1993-2003):
  ```python
  from chuzom.quality_feedback import should_skip_model
  if should_skip_model(model, task_type.value, c.value):
      log.info("Skipping low-quality model for %s/%s: %s", task_type.value, c.value, model)
      route_log.info("model_quality_skip", ...)
      continue
  ```
  There is no bypass or exemption for the case where `model` is the caller's explicit override and is the *only* candidate — skipping it here immediately exhausts the "primary chain" and triggers `BUDGET emergency fallback`.
- `should_skip_model()` (`src/chuzom/quality_feedback.py`) skips a model once it has `>= _MIN_CALLS_FOR_SIGNAL` (=3) recorded calls for the exact `(model, task_type, complexity)` key with `avg_quality < QUALITY_THRESHOLD` (=0.4). The quality store (`_quality_store`) is a **process-global, in-memory, unscoped dict** — not keyed by caller, session, or agent — so once *any* 3 calls to a given model/task/complexity triple average below 0.4 (from any caller in the process), *every other caller* in that same process requesting that exact model for that task/complexity is silently redirected, for the remainder of the process's lifetime (or until `reset_quality_store()` is called, which is not part of any normal request path).
- The math is self-consistent with the observed `avg=0.3`: `score_response()`'s rubric for `task_type="generate"` gives 0.1 (non-empty) + 0.2 (no refusal) with no length/structure bonus for the fake soak response (13 estimated tokens, no heading/blank-line, no trailing punctuation) = exactly 0.3, which is `< QUALITY_THRESHOLD` (0.4), so the 4th and every subsequent call to `openai/gpt-4o-mini` for `generate/moderate` is skipped.

**Impact:** `model_override` is documented and coded as "use only this model," but is not authoritative once the model's rolling quality average degrades below threshold for that task/complexity pattern — the router silently substitutes a different provider/model with no error, no log-level warning visible outside structured route logs, and no field on the response that flags "this was not the model you asked for" (the response's `model`/`provider` fields are simply set to the substitute, so a caller inspecting only `resp.content` would not notice at all). Any caller relying on `model_override` for reproducibility, cost control (routing to a specific cheap/paid model deliberately), compliance (routing away from a specific provider), or A/B comparison work would get silently wrong results. See `findings-C.json` (`CHZ-AUD-C-02`).

**Methodological caveat, disclosed per the audit's evidence standard:** because 5415 of 5418 iterations fell back to `ollama` (a `LOCAL_PROVIDERS` member, for which `reserve_tokens`/`release_tokens` are a no-op per source), the soak run's "0 pending-token drift" result is strong evidence only from the first 3 genuinely non-local dispatches, not from 5418 repeated non-local reservations as the driver was originally designed to exercise. The soak run still provides strong, valid evidence for: no leak across 5418 sequential invocations spanning both the direct-dispatch and emergency-fallback code paths, no lost/duplicate executions (`fake_call_text_invocations == N` exactly), and the quality-skip/fallback-substitution behavior itself being real, deterministic, and sustained at scale.

### 3.4 Related, distinct discovery from the pre-soak smoke test: output-length gate causes double dispatch
`soak_driver.py`'s own docstring (lines 12-17) records that the first run of `soak_smoke.py`, before its fake response content was lengthened to pass a minimum-length check, produced **10 `_call_text` invocations for 5 iterations** (a 2x ratio) — i.e., a response shorter than the router's output-length floor is rejected by a post-dispatch quality gate and silently triggers a second dispatch ("BUDGET emergency fallback") within the same `route_and_call`, without raising to the caller. This is mechanistically related to but distinct from §3.3: §3.3 is a **pre-dispatch** skip driven by a rolling quality average across calls; this is a **post-dispatch** rejection of a single response's raw length, both funneling into the same "BUDGET emergency fallback" path and both invisible to the caller beyond the final (substituted) response. This was fixed in the *test harness* (lengthening the fake content) rather than being a defect in itself to reproduce against production traffic, but it demonstrates the same class of "silent model substitution with no caller-visible signal" behavior and is recorded here as a methodology note / minor finding. See `findings-C.json` (`CHZ-AUD-C-03`).

---

## 4. Summary Table

| Area | Result | Evidence |
|---|---|---|
| Wheel build + clean-venv smoke | PASS (carried over) | prior segment, unchanged |
| `chuzom verify` exit-code propagation (CHZ-PKG-005) | Already fixed, not a current defect | `cli.py:929-935`, direct read this segment |
| `chuzom verify` hook-list completeness | OPEN — checks 3/13 real hooks | `verify.py:158-183` vs `install_hooks.py:309-350` |
| IDE config writers use `Path.cwd()` | OPEN — real-repo-mutation risk | `cli.py:233,245,406,418,463,475` |
| Budget-backend (SQLite/WAL) concurrency | PASS, re-confirmed this segment | `test_budget_multiprocess.py`: 400 calls, 200/200 expected successes, 0 leaked lock errors |
| Session-store concurrency | **FAIL — real data-loss race, re-confirmed this segment** | `test_session_store_concurrency.py`: 22/1200 (1.83%) lost writes, 0 corrupt lines |
| Soak (5418 sequential iterations, 210s) | Clean — no leak/drift by script's own criteria | `soak_full_run.log`: 0 errors, 0 drift, modest resource deltas |
| `model_override` vs quality-feedback circuit breaker | **NEW — silent override, 5415/5418 soak iterations** | `soak_full_run.log` + `router.py:387,1993-2003` + `quality_feedback.py` |
| Output-length gate double-dispatch | Minor/methodology finding | `soak_driver.py` docstring + confirmed mechanism class |
| aiosqlite daemon-thread-at-exit coverage | UNABLE TO VERIFY | not re-executed this segment |

All test scripts, worker scripts, and raw logs referenced above live under `/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/audit-C/` and are hermetic (redirected `HOME`, never touching the real `~/.chuzom`).
