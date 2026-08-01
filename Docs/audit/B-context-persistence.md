# AUDIT-B: Context Preservation & Persistence

**Scope:** Phases 7 (within-session, cross-provider), 8 (between-session persistence), 9 (fail-open under provider failure), plus the Phase 8-9 cross-session/cross-project leakage sub-investigation.
**Commit under audit:** `f5bf55c2a6e532229979ed90d376557f33698f57` ("fix: iteration-11 — surgical IDE-config uninstall (Critical) + install backups + honesty")
**Repo:** local checkout at `/Users/yaliandrona/Projects/Chuzom` (no clone performed)
**Python used for all execution:** `/Users/yaliandrona/Projects/Chuzom/.venv/bin/python`
**Isolation discipline:** every executed script sets `HOME` to a fresh `tempfile.mkdtemp()` directory *before* importing any `chuzom` module, so all module-level path constants resolve under the hermetic tmp dir. The real `~/.chuzom` was never written to by any test in this audit.
**Providers:** all tests monkeypatch `providers.call_llm` / `providers.call_llm_stream_events` with deterministic canned responses ("canary" models), so no real API keys/network calls were used. No real API keys were present in the test environment (all provider API key env vars were explicitly unset before import).

## Bottom line

**Chuzom persists BOTH content and metadata, split across different stores with very different scoping guarantees:**

- The durable **Session Context Accumulator** (`session_store.py`) persists **full, verbatim, largely-unredacted prompt and response text** to plaintext JSONL files on local disk, indefinitely (no time-based TTL — only a size-based compaction that keeps the newest records). It IS correctly scoped per-project on disk (keyed by `$CHUZOM_PROJECT_ID`), and it DOES fail open safely (corruption, read-only directories) — confirmed by live execution, not just source reading.
- Every other persisted store this audit examined (`usage.db`, session_spend, the routing_quality ledger) persists **metadata/cost only** — no prompt or response text — though `usage.db`'s `project_id` attribution is computed via a completely different, git-remote-based mechanism than the session-context layer's project scoping (CHZ-AUD-B-06), which is a reporting-accuracy defect, not a content leak.
- The **in-process `SessionBuffer`** (an ephemeral, non-persistent, process-lifetime-only cache used to inject "[Recent conversation context]" into prompts) has **zero project or session scoping** — a bare global singleton. Live execution proved this causes an actual, reachable cross-project content leak within a single process (CHZ-AUD-B-04, **Critical**), in contrast to the durable layer, which remains correctly isolated on disk.

See `/Users/yaliandrona/Projects/Chuzom/audit/findings-B.json` for the full, evidence-backed finding list (CHZ-AUD-B-01 through CHZ-AUD-B-08) and `/Users/yaliandrona/Projects/Chuzom/audit/CONTEXT_PERSISTENCE_MATRIX.md` for the requested column-format matrix.

---

## 1. Inventory of persisted stores under `~/.chuzom`

| Store | File(s) | Writer | Reader | What's persisted | Scope key | TTL / cleanup |
|---|---|---|---|---|---|---|
| **Session Context Accumulator (durable)** | `~/.chuzom/projects/<project_id>/session_context_<session_id>.jsonl` | `session_store.record_event()` — called from `router.py`'s primary success path only (router.py ~2459-2476) | `session_store.build_session_context()` → injected into `context.py`'s `build_context_messages()` layer 2b | **Full verbatim content**: `kind` (`user_prompt`/`routed_qa`/`tool_call`/`assistant`), `content` (prompt or response text, passed through `_scrub_secrets()` first), `task_type`, timestamp | `(project_id, session_id)` — `project_id` via `$CHUZOM_PROJECT_ID` env var (sanitized/truncated) else `sha1(cwd)[:16]`; `session_id` via `resolve_session_id()` | No wall-clock TTL found in reviewed code. `_compact_if_needed()` caps file size by keeping only the newest `_COMPACT_TO` records once a size threshold is exceeded — a volume-based cap, not a time-based expiry. No file locking observed in the reviewed code (single-process JSONL append). |
| **In-process SessionBuffer (ephemeral)** | none — RAM only, never written to disk | `context.py`'s `SessionBuffer.record()`, called from `router.py`'s primary success path (~2454-2457) | `SessionBuffer.format_for_injection()` → `context.py` layer 2 | **Full verbatim content** of the last N (bounded `deque(maxlen=...)`) user/assistant turns, injected under a `[Recent conversation context]` marker | **NONE** — single global singleton (`context.py:161`, `_session_buffer: SessionBuffer | None = None`), no project_id/session_id parameter anywhere | Bounded by `deque(maxlen=...)` (oldest evicted on overflow); fully cleared on process restart (RAM only) |
| **usage.db** | `~/.chuzom/usage.db` (SQLite) | `cost.py:log_usage()` | `cost.py`'s reporting/query functions (e.g. `get_usage(project_id=...)`) | **Metadata/cost only**: model, provider, input/output tokens, cost_usd, timestamp, `project_id` (see below), task_type — **no prompt/response text** | `project_id` via `chuzom.team.get_project_id()` — **independent** of `$CHUZOM_PROJECT_ID`; resolves via `git remote get-url origin` → `owner/repo`, else `os.path.basename(cwd)` | No TTL observed in reviewed portions; presumably grows indefinitely (out of this audit's direct scope) |
| **session_spend** | (module referenced in router.py primary path, ~2380-2396; not independently file-path-traced this session) | router.py primary success path only | session_spend budget-tracking logic | Metadata/cost only (spend totals) — no content | Session/budget-period scoped (not independently re-verified this session; carried forward from prior work) | Not independently re-verified this session |
| **routing_quality ledger** | `record_route(RouteLedgerRecord(...))`, router.py ~2407-2452 | router.py primary success path only | ledger analytics/reporting | Metadata only: routing decisions, `actual_cost_usd` (incl. `failed_attempt_cost_usd`), model/provider chosen, gate outcomes — no content | Not independently re-verified this session; carried forward from prior work | Not independently re-verified this session |
| **Previous-session summaries** | referenced via `get_recent_session_summaries()` / `format_session_summaries()`, `context.py` layer 1 | out of this session's direct re-verification scope (function names confirmed via grep, not fully read this segment) | `context.py` layer 1, injected before the SessionBuffer/durable layers | Summaries (abstracted, not necessarily verbatim) of prior sessions | Not independently re-verified this session | Not independently re-verified this session |

**Critical scoping asymmetry**: the durable session-context layer and the in-process SessionBuffer both claim to serve the same purpose ("recent conversation context for injection") but use **completely different, non-interoperating scoping mechanisms** — one correctly project-scoped on disk, the other a single unscoped global in RAM. This asymmetry is the direct cause of CHZ-AUD-B-04.

---

## 2. Phase 7 — Within-session context across providers

**Scenario executed** (`audit/scripts/phase7_cross_provider.py`): 3 consecutive turns in one session (`CLAUDE_SESSION_ID=audit-b-p7-session-1`, `CHUZOM_PROJECT_ID=audit-b-phase7-project`), each forced to a different provider via `model_override`:

1. `ollama/canary-local`: "The secret code is ORANGE-742. Don't repeat it back to me."
2. `openai/canary-openai`: "Make a python variable that holds the code from before."
3. `perplexity/canary-ppx`: "What value are we using for that variable? Just state it plainly."

`providers.call_llm` was monkeypatched to capture the exact `messages` list handed to each "provider" call.

**Result**: within the same session, context correctly flows forward across provider boundaries (both the in-process SessionBuffer, live in this single process, and the durable JSONL contribute) — turn 2 and turn 3's outbound payloads include the recent-conversation-context block referencing turn 1, satisfying the claim that context is preserved across providers within one session, PROVIDED the referenced fact is still within either (a) the in-process buffer's recency window, or (b) the durable layer's "3 newest events" unconditional window. See Phase 7b below for what happens once it ages out of both.

## 2b. Phase 7b — Buffer eviction & process restart (keyword-fallback dead-code proof)

**Scenario executed** (`audit/scripts/phase7b_buffer_eviction_and_restart.py`, run as a **fresh process** pointed at the same hermetic `TMP_HOME`, same `session_id`, same `project_id` as Phase 7 above — i.e. the in-process SessionBuffer is guaranteed empty at start, isolating the test to the durable layer):

1. Confirmed `get_session_buffer().message_count == 0` at process start (fresh singleton).
2. 4 unrelated filler turns (pasta recipe, TCP handshakes, unit testing, Romeo and Juliet) — none share a keyword with "code" or "ORANGE-742", pushing the original secret-bearing record out of the durable layer's "3 newest unconditionally kept" window.
3. Final turn: *"Going back to the very start of our conversation — what was that secret code again?"* — deliberately reuses the keyword "code" from the original turn, to test whether the durable layer's keyword-overlap fallback resurfaces the original record.

**Result — `orange_742_present_in_final_payload: false`.** Despite:
- the original record still existing verbatim in the durable on-disk JSONL (confirmed separately by `cat`-ing the file),
- the final query literally containing the shared keyword "code",

the secret does NOT resurface in the final outbound payload. Root cause traced to source (CHZ-AUD-B-01): the keyword-overlap fallback in `session_store.build_session_context()` depends on a `query` parameter that is populated exclusively from `caller_context`, which — confirmed via a system-wide grep across all of `src/chuzom/*.py` — is never populated by any real MCP-tool call site with the live user prompt text. It is passed as `None` on every real invocation, so `query_words` is always the empty set and the fallback branch is structurally unreachable, not merely weak.

## 2c. Phase 7c — Streaming path

**Scenario executed** (`audit/scripts/phase7c_streaming_context_bug.py`): `router.route_and_stream(TaskType.QUERY, "does streaming crash on context injection?", model_override="openai/canary-stream")` against a monkeypatched `providers.call_llm_stream_events`.

**Result**: raised `TypeError` (captured type/message/traceback in the script's JSON output) at the `build_context_messages(prompt, system_prompt, caller_context)` call site in `route_and_stream()` (router.py ~4486) — a synchronous, positional call against `build_context_messages()`, which is `async def build_context_messages(*, ...)` (keyword-only, coroutine). A second bug (uncaught `ValueError: Unknown media task type`) was also captured. **Dead-code caveat**: `route_and_stream()` was established, prior to this session, to be unreachable from any current live entry point (no CLI command, MCP tool, or dashboard wires up to it) — documented as CHZ-AUD-B-07/08 for completeness and as a landmine for any future feature that does wire it up.

---

## 3. Phase 8 — Between-session persistence

**Key question**: does Chuzom persist actual conversational content between sessions, or only metadata?

**Answer, stated plainly**: **Actual content**, in the durable Session Context Accumulator. `session_store.record_event()` writes the full, verbatim `content` field (prompt or response text) to a per-`(project_id, session_id)` JSONL file, after passing it through `_scrub_secrets()` — which only strips syntactically-anchored (`key[:=]value`) credential-shaped strings and a handful of known vendor token prefixes (`sk-ant-`, `sk-`, `AIza`, `AKIA`, `gh[pousr]_`, PEM blocks). Anything phrased as prose ("the secret is X") passes through completely unredacted (CHZ-AUD-B-03, confirmed live: "PURPLE-999" from a prose-phrased prompt appears byte-for-byte in a later cross-project payload). This content has no time-based expiry — only a size-based compaction that trims to the newest N records once a file grows past a threshold (CHZ-AUD-B-02).

By contrast, `usage.db`, session_spend, and the routing_quality ledger persist **metadata/cost only** (model, tokens, cost, routing decisions) — confirmed via source read of `cost.py:log_usage()`'s INSERT statement and router.py's `record_route(RouteLedgerRecord(...))` call, neither of which includes prompt/response text in their persisted fields.

---

## 4. Phases 8-9 — Cross-session / cross-project leakage investigation

Four sub-investigations were run, all via `audit/scripts/phase8_leakage_and_failopen.py` in one hermetic HOME so results are directly comparable.

### (a) Two sessions, same project

Not independently isolated as a standalone test this segment (Test B below, session-id reuse *within* one project, is the closest executed variant); the durable layer's `(project_id, session_id)` file-per-session keying means two genuinely different session_ids under the same project produce two separate JSONL files with no cross-contamination by construction (source-level reasoning, consistent with — and not contradicted by — every other test run this audit).

### (b) Two different projects with similar prompts — **LEAK CONFIRMED (in-process layer only)**

**Test A** (`phase8_leakage_and_failopen.py`): same `CLAUDE_SESSION_ID` ("shared-session-id-collision-test"), `CHUZOM_PROJECT_ID` switched from `project-alpha` to `project-beta` mid-process (same process — this is the realistic case of one long-running chuzom process, e.g. an MCP server, serving multiple projects/repos over its lifetime).

1. `project-alpha`: *"Project ALPHA secret is PURPLE-999. Remember it."*
2. Switch `CHUZOM_PROJECT_ID` to `project-beta`, ask: *"What secret did we just discuss?"*

**Result**:
- `project_alpha_secret_leaked_into_project_beta_payload: true` — "PURPLE-999" appears verbatim inside the `[Recent conversation context]` block of project-beta's outbound payload.
- **Durable layer remains correctly isolated**: `project_alpha_dir_exists: true` and `project_beta_dir_exists: true`, each with its own separate on-disk JSONL under its own `projects/<id>/` directory; the leak does not appear in the durable per-project files — it happens exclusively via the shared, unscoped in-process `SessionBuffer` (CHZ-AUD-B-04, **Critical** — this is the headline finding of the audit segment).

### (c) Session-id collision (same project) — confirmed as by-design mixing, not a new bug

**Test B**: `CHUZOM_PROJECT_ID=project-gamma` held constant; `CLAUDE_SESSION_ID=reused-session-id` reused across two logically-unrelated conversations.

1. *"Conversation ONE secret is TEAL-111."*
2. *"Unrelated new conversation — what secret was mentioned?"* (same reused session_id)

**Result**: `teal_111_present_in_second_conversation_payload: true` — content mixes, exactly as expected given the store keys purely on `(project_id, session_id)` with no third disambiguating axis. This was established as expected-by-design behavior (not a bug) prior to this session and is re-confirmed here; documented for completeness but not separately minted as a new finding.

### (d) Semantic cache project-scoping claim — **UNABLE TO VERIFY**

The semantic-cache layer's `store()` call (fire-and-forget, referenced in router.py's primary success path ~2629-2635) was not independently exercised this audit. No live test was run against it, and its source was not read in sufficient depth this session to confirm or refute its project-scoping claim. **Marked UNABLE TO VERIFY** rather than asserting a result not actually produced by execution.

### Fail-open behavior (Tests C and D)

**Test C — corrupted JSONL**: wrote garbage/torn lines (`"{not valid json at all\n{\"kind\": \"user_prompt\"\n"`) directly to a session's JSONL file, then called `build_session_context()` and a full `route_and_call()`. **Result**: no exception raised; `build_session_context()` returned cleanly (its documented `try/except: return ""` fail-open behavior); routing completed successfully end-to-end.

**Test D — read-only session directory**: `chmod`'d the session directory to `r-x` (no write permission) before calling `route_and_call()`. **Result**: no exception raised; routing completed successfully end-to-end (the write failure inside `record_event()` fails open silently, consistent with the try/except pattern established via source read).

Both confirm Phase 9's core question — **prompt/response delivery to the caller is preserved exactly, and routing succeeds, even when the persistence layer is corrupted or unwritable** — the persistence layer's failure is fully isolated from the routing/response-delivery path, by design and confirmed via live execution, not just source inspection.

---

## 5. Phase 9 — Fail-open under provider failure / recording-skip on emergency fallback

Two distinct fail-open/degradation mechanisms exist and must not be conflated:

1. **Persistence-layer fail-open** (Tests C/D above): if `session_store.record_event()`/`build_session_context()` themselves fail (corrupt file, permission denied), the call still succeeds and the prompt is delivered exactly as given — confirmed live.
2. **Emergency BUDGET fallback recording-skip** (CHZ-AUD-B-05, established via source read of router.py 2380-2799): when the *primary* routing chain is exhausted (e.g. every candidate response fails the dispatch quality/length gate, or all candidates are rate-limited/unhealthy) and the router falls back to its emergency BUDGET path, a **structurally separate code block** handles the eventual success — and that block does NOT perform session_spend recording, routing_quality ledger recording, in-process SessionBuffer recording, or durable `session_store.record_event()`, even though the caller receives an ordinary successful response. `cost.log_usage()` IS still called on this path, so basic per-call cost in `usage.db` is populated (no double-billing), but the turn is invisible to every context-injection and quality-ledger mechanism.

   This was indirectly re-confirmed this session: the *first* run of `phase8_leakage_and_failopen.py` originally used a 3-character canned reply ("ack"), which failed the dispatch quality/length gate for every call and silently diverted every test call through the emergency fallback path — and the resulting hermetic HOME had **no project directories created under `~/.chuzom/projects/` at all**, exactly as source analysis predicts. The script was fixed to return a ≥20-character canned reply so subsequent runs correctly exercised the primary path instead (this was a test-design fix made prior to this session, not a new finding about production code — but its diagnostic side-effect independently reconfirms CHZ-AUD-B-05's behavior).

**Is cost/quota double-counted?** No evidence of double-counting was found — `cost.log_usage()` is called exactly once per successful attempt on both the primary and emergency-fallback paths. The gap is under-counting/invisibility in the *routing_quality* and *context* layers specifically, not duplicate billing.

---

## 6. Summary of findings (see findings-B.json for full detail)

| ID | Title | Severity |
|---|---|---|
| CHZ-AUD-B-01 | Durable keyword-relevance context fallback is structurally dead code (caller_context never wired) | Medium |
| CHZ-AUD-B-02 | Durable session_store persists full verbatim content indefinitely, plaintext, no TTL | High |
| CHZ-AUD-B-03 | Secret-scrubbing regexes require key=value syntax; prose-phrased secrets bypass redaction | Medium |
| CHZ-AUD-B-04 | In-process SessionBuffer has zero project scoping — confirmed cross-project content leak | **Critical** |
| CHZ-AUD-B-05 | Emergency BUDGET fallback success path skips all context/ledger recording | High |
| CHZ-AUD-B-06 | usage.db project_id resolution is independent of/inconsistent with session_store's project scoping | Low |
| CHZ-AUD-B-07 | Streaming context-injection call raises TypeError (dead code today) | Medium |
| CHZ-AUD-B-08 | Streaming path also raises an uncaught, misleadingly-labeled ValueError (dead code today) | Low |

**Totals: 1 Critical, 2 High, 3 Medium, 2 Low (8 findings total).**
