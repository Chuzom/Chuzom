# Chuzom Release-Hardening Remediation Plan

Commit audited: `f5bf55c` (audit baseline) — verified against current HEAD `1498446fa39a0110fe15b701b8642ac88a49f668` (one commit ahead, no code drift on any of the 20 in-scope findings). All 20 release-target findings were re-traced against current source this pass; **all 20 remain `still-reproducible`** — no fix, partial fix, or contract change has landed for any of them since the audit.

This plan groups the 20 findings into **7 root-cause clusters**. The goal is a small number of structural fixes, not 20 point-patches.

---

## Cluster → Findings Map

| Cluster | Findings | Count |
|---|---|---|
| 1. Sensitive-content lifecycle | D-01, D-02, D-04, B-02, B-03 | 5 |
| 2. Scope identity | B-04 | 1 |
| 3. Successful-turn finalization | B-05 | 1 |
| 4. Attempt/fallback state machine | A-01, A-02, C-02, C-03 | 4 |
| 5. Enforcement/guarantee contract | A-03, A-04, A-05, A-06, D-05 | 5 |
| 6. Concurrent persistence | C-01 | 1 |
| 7. Reachability/neglected paths | B-01, B-07, C-04 | 3 |

Total: 20/20 findings covered, none dropped, none double-counted as primary owner (C-02 has a secondary scope-identity facet shared with cluster 2 — see below).

---

## Cluster 1 — Sensitive-content lifecycle
**Findings:** D-01 (Critical), D-02, D-04, B-02, B-03

**Root cause:** three secret/PII-handling subsystems were built independently and never connected to a shared enforcement point:
- `secret_scrubber.py` — `[:=]`-anchored regex only (session_store JSONL). Misses prose secrets ("here's my key sk-abc123...").
- `enterprise/redaction.py` via `redaction_routing.py` — well-built (Luhn-checked, vendor-prefixed), but **off by default**, fail-open, and wired only into `route_and_call()`'s prompt path — not into `_dispatch_model_loop()` where `semantic_cache.store()` actually persists content.
- `result_cache.py` / `semantic_cache.py` — **zero** scrub/redact/chmod hits. Persist raw prompt+response indefinitely, world-readable by default, FTS-searchable, cross-provider replay risk.
- No TTL anywhere in the persistence layer — only size/count-based compaction in `session_store.py`.
- D-04: no test coverage exists for any of the above gaps (a direct consequence, not an independent defect).

**Fix (single shared primitive):**
1. Extract a `persist_redact(text: str) -> str` helper that wraps `enterprise/redaction.py`'s redactor with a fallback to a **broadened** (not just `[:=]`-anchored) pattern set covering common prose-secret shapes (`sk-...`, `ghp_...`, bearer tokens, AWS keys, etc.).
2. Call it unconditionally, gated by a new **persistence-scoped** flag `CHUZOM_PERSIST_REDACTION` (default `"on"`) — deliberately independent of the existing `CHUZOM_REDACTION` prompt-routing flag, which defaults off and governs a different call site.
3. Wire into all three write paths: `result_cache.store_result()`, `semantic_cache.store()`, `session_store.record_event()` (replacing `_scrub_secrets()`'s narrow patterns with the shared helper).
4. Harden file perms: `os.chmod(0o600)` on `result_cache.db` and `semantic_cache.db` creation (mirroring the correct pattern already used in `cost.py:542`).
5. Add TTL: `CHUZOM_PERSIST_TTL_DAYS` (default `30`), physically deleted (not just filtered) during each store's existing compaction pass.
6. D-04: add regression tests asserting (a) prose secrets are redacted in all three stores, (b) file perms are `0600`, (c) records older than TTL are physically absent after compaction.

**Migration/backcompat:** existing `result_cache.db`/`semantic_cache.db`/session JSONL files predate redaction — ship a one-time migration command (`chuzom migrate redact-existing`) that re-writes historical records through `persist_redact()` in place; document that this is destructive to exact historical text (expected/intended).
**Security impact:** closes the single highest-severity finding (D-01, Critical) plus 4 related gaps in one pass.
**Docs impact:** document the new flags and the migration command in `Docs/configuration.md`; this is also referenced by Cluster 5's docs fix.

---

## Cluster 2 — Scope identity
**Findings:** B-04 (Critical)

**Root cause:** `context.py`'s `SessionBuffer` is a module-level singleton (`get_session_buffer()` takes no args) — not keyed by project or session. Within one long-lived process, content from project/session A leaks into project/session B's context reinjection.

**Fix:** convert the singleton into a registry keyed by `(project_id, session_id)`, e.g. `_buffers: dict[tuple[str,str], SessionBuffer]`, with `get_session_buffer(project_id, session_id)` requiring both keys (breaking change to the call signature — update all 5 call sites confirmed in `context.py` lines 96/161/164-169/220/255/473, plus router.py's callers). Apply an LRU/idle eviction so the registry doesn't grow unbounded across a long process lifetime.

**Note on C-02 synergy:** `quality_feedback.py`'s `_quality_store` (Cluster 4) has the *same* unscoped-global-dict shape. Once the keyed-registry pattern exists for `SessionBuffer`, reuse it for `_quality_store` as a secondary hardening step under Cluster 4's ticket — do not duplicate the pattern from scratch.

**Migration/backcompat:** breaking signature change to `get_session_buffer()` — all internal callers updated in the same PR; no external API surface (internal module only) so no public backcompat concern.
**Security impact:** closes a Critical cross-project data leak.

---

## Cluster 3 — Successful-turn finalization
**Findings:** B-05

**Root cause:** the "BUDGET emergency fallback" success branch in `router.py` (~line 2712 trigger, 2767–2775 success emits) calls `_emit_ledger_attempt`/`_emit_ledger_terminal` and logs `emergency_fallback_success`, but — unlike the primary success path — never calls `session_spend` recording, `routing_quality.record_route()`, `buf.record()`, or `_session_store.record_event()`. A turn that succeeds via fallback is invisible to spend accounting, quality feedback, context continuity, and durable history.

**Fix:** extract a single `finalize_successful_turn(...)` helper containing the primary path's full post-success side-effect sequence (session_spend, routing_quality, buf.record, session_store.record_event, ledger terminal). Call it from **both** the primary success path and the BUDGET-fallback success path, replacing the duplicated/partial inline calls in each.

**Dependency:** land after Cluster 4 (Attempt/fallback state machine). Cluster 4 clarifies exactly which conditions route into the BUDGET-fallback branch (A-01/C-02/C-03) and fixes `attempt_failed` emission — the finalize-helper's call sites and its accounting of "was this an override/fallback attempt" are cleaner to write once cluster 4's dispatch-loop signaling is correct, avoiding rework.

**Migration/backcompat:** none — purely internal control-flow consolidation, no schema change.
**Security/docs impact:** none directly, but closes an accounting-integrity gap (spend/quality data silently incomplete for a non-trivial fraction of turns).

---

## Cluster 4 — Attempt/fallback state machine
**Findings:** A-01, A-02, C-02, C-03

**Root cause:** the dispatch loop's bookkeeping of *what actually happened* to an attempt is incomplete and inconsistent:
- A-01: `attempt_failed` is a defined ledger event type with **zero** call sites in `router.py` — failed attempts are never recorded as failed.
- A-02: `agent_session_id` (used for policy lookup and OKF turn capture) is never threaded into `execution_ledger.py`'s `session_id` column — `get_session_accounting()` can't attribute ledger rows to the calling agent session.
- C-02: `should_skip_model()` (quality circuit breaker) is applied unconditionally in the dispatch loop (router.py:1995-1996), even when the caller passed an explicit `model_override` that produces a single-element forced chain (`_build_and_filter_chain` → `return [model_override]`, router.py:387). After 3 low-quality calls the breaker silently swaps away from the caller's explicit choice with no signal to the caller.
- C-03: the output-length gate (<20 chars) triggers the *same* undifferentiated BUDGET-fallback re-dispatch as C-02's quality-skip — both silently re-route through a branch with no caller-visible distinction between "your explicit choice was honored," "quality breaker overrode it," and "length gate forced a retry."

**Fix (one dispatch-loop pass):**
1. Add `attempt_failed` emission at every exception/failure branch currently falling through without a ledger call (closes A-01).
2. Thread `agent_session_id` into the ledger's `session_id` field at all `_emit_ledger_attempt`/`_emit_ledger_terminal` call sites (closes A-02).
3. Add an explicit-override bypass: when the dispatch candidate came from `model_override`, skip `should_skip_model()` entirely (closes C-02's primary defect). As defense-in-depth, also scope `_quality_store` by session using the Cluster 2 keyed-registry pattern.
4. Introduce a `fallback_reason` enum (`quality_skip | length_gate | chain_exhausted`) recorded on every BUDGET-fallback dispatch, so C-02/C-03's distinct triggers are distinguishable in the ledger instead of collapsing into one undifferentiated branch (closes C-03; also gives Cluster 3's `finalize_successful_turn` a reason code to record).

**Migration/backcompat:** `execution_ledger` schema gains `fallback_reason` (nullable, additive — no migration needed for existing rows). `model_override` callers get strictly *more* honored behavior (bugfix, not a behavior contract most callers depend on breaking).
**Security impact:** none direct; closes an enforcement-honesty gap (callers who pass `model_override` for compliance/cost reasons were silently not getting it).

---

## Cluster 5 — Enforcement/guarantee contract
**Findings:** A-03, A-04, A-05, A-06, D-05

**Root cause:** messaging across `auto-route.py`, `enforce-route.py`, `rules/chuzom.md` (both the source and the installed copy), `session-start.py`'s `_enforce_label()`, and `Docs/configuration.md` all claim routing is advisory-only / "never blocks", but the actual default (`DEFAULT_ENFORCE = "smart"` in `enforce_config.py`) genuinely blocks Edit/Write/MultiEdit for all task types, and `hard` blocks Bash/Edit/Write/MultiEdit/NotebookEdit unconditionally. This is a trust/contract-honesty defect, not a functional bug in most of the 5 findings — except A-04, which has a real fail-open code defect (malformed JSON on the hook's stdin causes an early-exit that fails open instead of closed).

**Fix:**
1. Single source of truth: derive all user-facing "what does this mode do" strings (banners, `_enforce_label()`, docs) from one table in `enforce_config.py` keyed by mode, instead of hand-maintained prose in 4+ separate files. Eliminates drift between what the code does and what it claims.
2. Fix A-04's fail-open early-exit to fail **closed** (i.e., treat malformed hook input as "block," not "approve") — the only code-behavior change in this cluster; everything else is copy/messaging.
3. Update `rules/chuzom.md` (both source and installed copy) and `Docs/configuration.md` to state plainly which modes block which tools, matching the derived table from step 1.

**Migration/backcompat:** A-04's fail-closed change is a behavior change for malformed-hook-input edge cases only (should be rare/adversarial input) — note in release notes as a hardening change, not a regression.
**Docs impact:** this cluster *is* primarily a docs/messaging fix — `Docs/configuration.md` and `rules/chuzom.md` are the main deliverables alongside the derived-label refactor.
**Security impact:** A-04's fail-closed fix is a real security hardening (prevents malformed input from being used to silently bypass enforcement).

---

## Cluster 6 — Concurrent persistence
**Findings:** C-01

**Root cause:** `session_store.py`'s `_maybe_compact()` rewrites the JSONL file via `tempfile.mkstemp()` + `os.replace()` with **no lock** coordinating concurrent writers against the replace. Audit's 6-process concurrency test showed 22/1200 writes lost (1.83%), 0 corrupt lines — consistent with inode-orphaning: a writer appends to the old inode after another process has already replaced it.

**Fix:** add an `fcntl.flock()` (POSIX) advisory exclusive lock around the append-then-maybe-compact critical section in `record_event()`, held for the duration of both the append and any triggered compaction, so a compacting process can't replace the file out from under a concurrent appender. Use a sibling `.lock` file rather than locking the JSONL itself, to avoid interaction with the `os.replace()` swap.

**Dependency:** land **first**, ahead of Cluster 1's session_store-specific piece (B-02/B-03's redaction wiring into `session_store.record_event()`). Adding new logic to a write path that has an unresolved race is how you compound the bug — fix the lock, then add redaction on top of a correct primitive.

**Migration/backcompat:** none — internal locking only, file format unchanged.
**Regression risk:** low; flock is a well-understood primitive, but must be tested on the project's supported platforms (POSIX-only — confirm no Windows support claim exists, or add an `msvcrt` fallback if it does).

---

## Cluster 7 — Reachability/neglected paths
**Findings:** B-01, B-07, C-04

**Root cause:** three unrelated-but-same-shaped defects where a code path is either dead or structurally unreachable, and nothing enforces that it's exercised:
- B-01: `caller_context`'s `query` field (the only input to `session_store.build_session_context()`'s keyword-relevance fallback) is never populated with the live prompt by any real caller — the fallback is unreachable in production.
- B-07: `route_and_stream()` calls `build_context_messages()` (async, keyword-only, `context.py:390`) with 3 positional args and no `await` (`router.py:4486`) — guaranteed `TypeError` whenever reached. Currently dead since `route_and_stream()` has no live caller, but a landmine for the first caller.
- C-04: `chuzom verify`'s `check_hooks()` hardcodes 3 of the 13 hook filenames actually installed by `install_hooks.py` — 10 installed hooks have zero health-check coverage.

**Fix (three independent, low-risk point-fixes — no shared code, but same "verify reachability" theme):**
1. B-01: default `caller_context.query` to the live `prompt` at router.py's `build_context_messages()` call sites, actually activating the keyword-relevance fallback; add a test proving it fires.
2. B-07: fix the call to `await build_context_messages(...)` with correct keyword args; add a smoke test that actually calls `route_and_stream()` end-to-end so this class of defect can't reappear silently.
3. C-04: derive `check_hooks()`'s expected filename list from the same source `install_hooks.py` uses (don't hand-maintain a second list) — closes the 10-hook blind spot structurally, not just by adding 10 more strings.

**Migration/backcompat:** none. **Regression risk:** low — these are independent, narrowly-scoped fixes; can be parallelized against every other cluster.

---

## Dependency-Ordered Execution Plan

**Wave 1 — parallel, no cross-cluster dependencies:**
- Cluster 6 (C-01): lock the session_store write path.
- Cluster 2 (B-04): scope `SessionBuffer` by `(project_id, session_id)`.
- Cluster 5 (A-03..A-06, D-05): derive enforcement labels from one table; fix A-04 fail-open→fail-closed; update docs.
- Cluster 4 (A-01, A-02, C-02, C-03): dispatch-loop attempt/fallback bookkeeping fixes.
- Cluster 7 (B-01, B-07, C-04): three independent reachability fixes.
- Cluster 1, cache-only portion (D-01, D-02 for `result_cache.py`/`semantic_cache.py`; D-04's cache tests): redaction + 0600 perms + TTL — no dependency on Cluster 6 since these are different files.

**Wave 2 — depends on Wave 1:**
- Cluster 1, session_store portion (B-02, B-03; remainder of D-04): wire `persist_redact()` + TTL into `session_store.record_event()` — sequenced after Cluster 6's lock fix lands, to avoid adding new write-path logic on top of an unresolved race.
- Cluster 3 (B-05): extract `finalize_successful_turn()` — sequenced after Cluster 4, since it consumes Cluster 4's `fallback_reason` enum and corrected attempt bookkeeping.

**Cross-cluster synergy note:** Cluster 2's `(project_id, session_id)`-keyed registry pattern should be reused (not reimplemented) for `quality_feedback.py`'s `_quality_store` as part of Cluster 4's defense-in-depth step.

---

## Sensitive-Content Default — Decision

**Recommendation: Option 2 — persist scrubbed, by default.**

Rationale: Chuzom's core value proposition (cheap-model routing with context continuity via `session_store`/`result_cache`/`semantic_cache`) structurally depends on being able to read back real prior content — a default of "don't persist anything real" (Option 3) would silently degrade the product's primary feature for every zero-config install. Given a capable redaction module (`enterprise/redaction.py`) already exists and merely needs to be connected and broadened (Cluster 1), scrubbed-by-default closes the disclosure risk (world-readable, FTS-searchable, cross-provider-replayed secrets — D-01, Critical) without sacrificing the feature.

**Concrete flags (new, additive):**
- `CHUZOM_PERSIST_REDACTION` — default `"on"`. Governs redaction for **all** persistence writes (`result_cache`, `semantic_cache`, `session_store`). Independent of the pre-existing `CHUZOM_REDACTION` flag, which governs only the prompt-routing call site and keeps its own (off) default — the two flags are not conflated.
- `CHUZOM_PERSIST_RAW` — default `"0"`. Explicit, narrow opt-in escape hatch for operators who want full verbatim transcript retention and accept the disclosure risk (Option 3's behavior, available but never the default).
- `CHUZOM_PERSIST_TTL_DAYS` — default `30`. Physical deletion of persisted records past this age, enforced during each store's existing compaction pass.

This is a decisive default (redact-and-keep, not silently-drop), with an explicit and separately-named opt-out for teams that have made an informed choice to retain raw content.

---

## Already-fixed / No-longer-applicable

None. All 20 findings were independently re-traced against current HEAD source this pass (grep + full-file reads of `router.py`, `session_store.py`, `context.py`, `quality_feedback.py`, `execution_ledger.py`, `enforce_config.py`, `commands/verify.py`) and every one showed exact or near-exact line-number correspondence to the audit's cited evidence. Zero drift, zero remediation landed since the audit.
