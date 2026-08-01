# AUDIT-A — Routing Execution & Guarantee

**Scope:** Does Chuzom actually route prompts to another model and execute them, or does it
only *suggest* routing while Claude answers anyway? What does the observability layer
actually count? What prompts silently bypass interception?

**Audited artifact:** local checkout at `/Users/yaliandrona/Projects/Chuzom`
**Commit under audit:** `f5bf55c2a6e532229979ed90d376557f33698f57`
**Interpreter used for all execution:** `/Users/yaliandrona/Projects/Chuzom/.venv/bin/python`
**Isolation:** every run below uses a fresh `tempfile.mkdtemp()` as `HOME`/`CHUZOM_HOME`; the
developer's real `~/.chuzom` and `~/.claude` were never touched.
**Method:** every claim in this document is backed by a command that was actually executed
in this session. Nothing here is inferred from documentation alone unless explicitly labeled
`UNABLE TO VERIFY` or `(source-only, not executed)`.

---

## 1. Fake-provider canary harness — does the recorded provider match the provider that
   actually produced the content?

### Harness

`/private/tmp/.../scratchpad/canary_harness.py` patches `chuzom.providers.litellm.acompletion`
(and the `chuzom.router._maybe_broker_dispatch` / codex / gemini-cli code paths) so that
**every** provider, regardless of which one `route_and_call()` picks, returns a unique,
provider-tagged canary string: `PROVIDER_OLLAMA_CANARY`, `PROVIDER_OPENAI_CANARY`,
`PROVIDER_ANTHROPIC_CANARY`, `PROVIDER_CODEX_CANARY`, `PROVIDER_GEMINI_CANARY`. It then drives
`router.route_and_call()` across 48 representative prompts spanning categories: simple,
moderate, complex, code, query, research, generate, greeting, continuation, empty,
whitespace, unicode, huge, injection-y, profile-check.

For every call it records: `outcome`, `recorded_model` / `recorded_provider` (what the router
*says* it routed to), `canary_found` (the literal canary string extracted from the returned
content — i.e. proof of which mock actually ran), and
`canary_matches_recorded_provider` (cross-check of the two).

Command actually run:
```
/Users/yaliandrona/Projects/Chuzom/.venv/bin/python /private/tmp/.../scratchpad/canary_harness.py
```
Output persisted to `canary_results.json` (`commit` field confirms
`f5bf55c2a6e532229979ed90d376557f33698f57`).

### Results (n = 48, all `outcome == "success"`)

| Metric | Value |
|---|---|
| Routing coverage (every prompt produced a routed call + a recorded provider) | 48/48 = 100% |
| Canary found in returned content (i.e. a real provider mock actually ran and its content reached the caller) | 48/48 = 100% |
| **Lost-response rate** (routed successfully but no canary in the final content) | 0/48 = **0.0%** |
| Canary ↔ recorded-provider exact match | 47/48 = 97.9% |
| **True wrong-provider rate** (misattribution bug — canary from provider X but router *records* provider Y as having answered) | **0/48 = 0%** (see reconciliation below) |
| `call_log_count` (total underlying provider-call-shaped invocations across all 48 prompts, including internal retries/classification calls) | 56 |

**Provider distribution actually recorded** (`recorded_provider`):

| Provider | Count | % |
|---|---|---|
| ollama | 38 | 79.2% |
| anthropic (Claude) | 5 | 10.4% |
| openai | 3 | 6.3% |
| codex | 1 | 2.1% |
| cache | 1 | 2.1% |

### The one apparent mismatch — reconciled, not a bug

The single `canary_matches_recorded_provider == false` row:

```json
{
  "category": "whitespace",
  "prompt_preview": "\\n\t\\n",
  "recorded_model": "cache/ollama/qwen3:32b",
  "recorded_provider": "cache",
  "content_preview": "PROVIDER_OLLAMA_CANARY :: response to prompt",
  "canary_found": "PROVIDER_OLLAMA_CANARY",
  "canary_matches_recorded_provider": false,
  "elapsed_ms": 46.8
}
```

`recorded_model` is `cache/ollama/qwen3:32b` — Chuzom's own semantic-cache layer prefixes the
model tag with `cache/` when it serves a previously-cached response instead of re-invoking the
provider (46.8 ms elapsed vs. hundreds of ms for a live call is corroborating evidence: this
is a cache hit, not a new inference call). The canary content is `PROVIDER_OLLAMA_CANARY`
because that's what got cached from an earlier identical (or near-identical, post-normalization)
prompt in the same harness run. This is **not a misattribution bug** — the router honestly
records `cache` as the provider rather than falsely claiming `ollama` served a fresh response.
Classified as a **positive finding** (honest telemetry), not a defect.

### Claude-fallback rate

5/48 (10.4%) prompts were routed to `anthropic` (Claude). Inspecting those 5 rows shows they
are `complex`/`moderate`-category prompts where `anthropic` was the *deliberate* routing
decision (task complexity appropriate for the profile), not a failure-triggered fallback —
`outcome` is `success` for all 48 rows and no failure was injected in this harness. **True
failure→Claude-fallback behavior is evidenced separately in §3** (the ledger probe), where an
injected failure on the first 2 dispatch attempts caused the chain to retry with a different
model in the *same* provider pool, not an automatic escalation to Claude specifically.

**`run_claude` (the Claude Code CLI subprocess dispatch path in router.py) was never actually
triggered in either harness** — marked **UNABLE TO VERIFY** for that specific code path; the
canary harness only patches the API/litellm dispatch layer, not the CLI-subprocess path, and
no prompt in the 48-prompt set routed there.

---

## 2. The push hook (`auto-route.py`): does it EXECUTE via another model, or only INJECT a
   suggestion that Claude answers itself?

This is the audit's central adversarial question. Answered with **both** static source
evidence and a real subprocess harness driving the actual hook file.

### 2.1 Source-level mechanism

`/Users/yaliandrona/Projects/Chuzom/src/chuzom/hooks/auto-route.py` (chuzom-hook-version: 27):

- `_enforce_mode` ∈ `{shadow, advise, hard, suggest}` via `chuzom.enforce_config.resolve_enforce_mode()`.
- `_direct_enabled` defaults **true**; forced **false** for context-dependent prompts (unless
  zero-Claude), for conversational context-inheritance, and always for `task_type == "coordinate"`.
- **Direct Execution actually fires a real external model** only when
  `_direct_enabled and _enforce_mode not in ("shadow", "off")`.
- `_resolve_auto_render_mode()` — the function that decides whether a successful Direct
  Execution *replaces* Claude's turn (`decision: "block"`) or is merely offered as advisory
  context (`decision: "approve"`) — has this docstring, which is itself the clearest
  first-party admission of the answer to the audit's question:

  > "Outside zero-Claude, 'auto' always resolves to advisory 'echo': the draft becomes
  > context the assistant verifies, never a fabricated answer that replaces the turn."

  I.e.: **by the code's own design intent, in the default (non-zero-Claude) configuration a
  successful real external execution is never allowed to silently replace what Claude
  produces.**

### 2.2 Execution harness

`/private/tmp/.../scratchpad/auto_route_hook_harness.py` runs the real hook file as a real
subprocess (`[PY, HOOK]`, real UserPromptSubmit-contract stdin JSON, hermetic per-cell tmp
HOME) across 9 mode/direct/zero-claude cells, using the prompt *"Explain the difference
between TCP and UDP in two sentences."* Command:

```
/Users/yaliandrona/Projects/Chuzom/.venv/bin/python /private/tmp/.../scratchpad/auto_route_hook_harness.py
```

All 15 cells (9 mode combinations + 6 skip-pattern probes) completed with `rc=0`, output
persisted to `auto_route_hook_results.json`.

### 2.3 Direct-Execution truth table (executed evidence)

| Cell (enforce mode / direct-exec / zero-claude) | `decision` field | Real external model actually called? | What Claude sees |
|---|---|---|---|
| `shadow`, direct=1, normal | **absent** (no `decision` key at all) | **No** — shadow mode gates off Direct Execution entirely (`_enforce_mode not in ("shadow","off")` fails); the `additionalContext` is a static routing *prediction* ("would route to llm_query → ollama/qwen3.5:latest"), with no latency/token numbers — no live call evidence | Passive 👁 OBSERVATION text only; nothing enforced, nothing executed |
| `advise`, direct=1, normal | `"approve"` | **Yes** — real Ollama (`qwen3.5:latest`) call, real on-topic TCP/UDP content captured verbatim in stdout, with real elapsed-time/token-count numbers (~1.3–2.1s, 264–302 tokens) | The real draft is injected as `additionalContext`, explicitly labeled **"UNVERIFIED DRAFT"**, with instructions telling Claude it may use it, correct it, or **"IGNORE the draft entirely and answer normally"**. Claude's turn is NOT blocked. |
| `hard`, direct=1, normal | `"approve"` | **Yes** — identical real-Ollama-draft behavior to `advise` | Same as `advise`: advisory-only, `decision: "approve"`, Claude free to ignore the draft |
| `suggest`, direct=1, normal | `"approve"` | **Yes** — same real-Ollama-draft mechanism | Same as `advise` |
| `advise`, direct=0, normal | (Directive Injection, no live call) | **No** | Text banner: *"Suggestion only — nothing is blocked... Never fabricate a routed answer — call the tool or handle it directly."* |
| `hard`, direct=0, normal | (Directive Injection, no live call) | **No** | Boxed "⚡ ROUTE DIRECTIVE — HARD ENFORCEMENT" banner claiming enforcement is delegated to the separate PreToolUse hook (`enforce-route.py`) — see §4 for whether that claim holds up |
| `advise`, direct=1, **zero-claude** | `"block"` | **Yes** — real Ollama call | Claude's turn genuinely replaced; the real Ollama content becomes the visible block reason/output. Claude never processes the prompt this turn. |
| `advise`, direct=0, **zero-claude** | `"block"` | **No** (direct execution administratively disabled) | Fail-closed with a bare notice: *"ZERO_CLAUDE BLOCKED (query/simple): direct external execution is disabled... Claude was not invoked... resubmit prefixed with `claude:`"* — **neither Claude nor a real model answers** in this cell |
| `hard`, direct=1, **zero-claude** | `"block"` | **Yes** — real Ollama call | Same as `advise`/direct=1/zero-claude: genuine turn replacement with real external content |

### 2.4 Verdict (task item #2)

**In the default configuration (`zero_claude=False`, which is the out-of-the-box default),
Chuzom's push hook never guarantees Claude is bypassed — not even when it successfully
executes a real external model.** Advise, hard, and suggest modes are all execution-proven to
behave identically in this respect: a genuine Ollama call happens, genuine content comes back,
and it is delivered as unverified advisory context (`decision: "approve"`) that Claude may
accept, correct, or discard outright. **Claude still produces the final answer by default.**

Only under the non-default `CHUZOM_ZERO_CLAUDE=1` configuration does a successful Direct
Execution genuinely replace Claude's turn (`decision: "block"`, real external content becomes
the actual output, Claude never runs for that turn). If direct execution is disabled or fails
under zero-claude, the result is a fail-closed block notice — **not** a real answer from
anyone.

This directly confirms the adversarial framing in the task brief: **in advise mode (and, this
execution proves, also in "hard" mode at the push-hook layer specifically), Chuzom only
SUGGESTS — Claude still answers.** Any claim that Chuzom "always executes another model" for
the push-hook path must be qualified: it is true that a real model is *called* whenever
Direct Execution fires, but it is false that this call is *guaranteed to determine the
turn's final output* unless zero-Claude is explicitly enabled.

---

## 3. Observability truthfulness — does telemetry count successful external executions, or
   merely routing decisions?

(Full detail already established via direct source reading of `router.py` and
`execution_ledger.py`, plus the executed `failure_ledger_probe.py`. Reproduced here as the
observability half of the routing-guarantee question.)

### 3.1 Executed failure-injection probe

`/private/tmp/.../scratchpad/failure_ledger_probe.py` patches `litellm.acompletion` to raise
`RuntimeError` on the first 2 dispatch attempts and succeed on the 3rd, then calls
`router.route_and_call(...)` for real and inspects the real SQLite `execution_events` table
written by `execution_ledger.py`.

Command actually run:
```
/Users/yaliandrona/Projects/Chuzom/.venv/bin/python /private/tmp/.../scratchpad/failure_ledger_probe.py
```

Result: `route_and_call` returned successfully (3rd attempt), `CALLS` shows 3 model dispatch
attempts were made, but the `execution_events` table contains **only 1 `attempt_completed` row
and 1 `route_completed` row** — i.e. the 2 injected failures produced **zero** ledger rows.

### 3.2 Root cause (source-confirmed)

- `execution_ledger.py` defines an `attempt_failed` event type in its own schema/
  `_BILLABLE_EVENTS` constant.
- `grep -n "attempt_failed" src/chuzom/router.py` returns **zero matches**. Both
  exception-handling blocks in the dispatch loop (`router.py:2645-2692` and `:2799-2806`) catch
  the provider exception, log it, and move to the next model in the chain — **neither ever
  calls `_emit_ledger_attempt(..., event_type="attempt_failed", ...)` or any equivalent.**

**Finding:** telemetry does **not** falsely credit a failed provider with having produced the
answer (there is no misattribution) — but it **silently omits failed attempts from the ledger
entirely**, which undercounts against the ledger schema's own "every attempt" framing and
would understate true attempt/retry volume in any reporting built on `execution_events`.

### 3.3 `agent_session_id` / session accounting trap (source-confirmed)

`route_and_call(agent_session_id=...)` is **never** threaded into the ledger's `session_id`
column — that field is populated from `CHUZOM_SESSION_ID` env or an auto-generated
`correlation_id` instead. `agent_session_id` is used solely for agent-specific routing-policy
lookup. Consequence, confirmed in the probe run: `ledger.get_session_accounting("audit-a-failure-probe-session")`
(the exact string passed as `agent_session_id`) returns an **empty** accounting object, even
though real, billable activity happened under that logical session — a silent API-contract
trap for any caller who assumes `agent_session_id` is the accounting key.

---

## 4. "Every eligible prompt is intercepted" — skip/bypass enumeration

Enumerated from `auto-route.py` source, in the exact order checked inside `main()`, and
cross-verified by the same execution harness (§2.2) using representative bypass prompts.

| # | Mechanism | Source location | Fail-open (normal mode) | Fail-closed under zero-Claude? | Execution-confirmed |
|---|---|---|---|---|---|
| 1 | Malformed/unparseable stdin JSON | `main()` ~2661-2665 | Immediate `sys.exit(0)`, **before** `_zero_claude_enabled()` can even be evaluated | **No** — this check happens ahead of the zero-claude gate; strict mode cannot help | **Yes** — even with `CHUZOM_ZERO_CLAUDE=1` set, malformed stdin produced completely empty stdout, rc=0 |
| 2 | Empty/whitespace-only prompt | `main()` ~2669-2676 | Silent no-op | Yes — `_block_zero_claude(...)` fires | **Yes** — normal mode: empty stdout; zero-claude mode: `decision:"block"`, reason "empty prompt — nothing to route under zero-Claude" |
| 3 | Self-reference bypass (`_SELF_REFERENCE_RE`) | ~2678-2693 | `sys.exit(0)`, unless `_is_enterprise_profile()` (checks `CHUZOM_DEPLOYMENT_PROFILE`/`CHUZOM_PROFILE` ∈ {enterprise, prod, production}) | Refused under enterprise profile (routing proceeds instead) | **Yes** — prompt mentioning "CHUZOM_ENFORCE"/"enforcement.log" produced completely empty stdout |
| 4 | Explicit native-prefix escape hatch | `_EXPLICIT_CLAUDE_PREFIX_RE` ~2721-2725 | n/a | Intentional escape even under strict mode | Not separately probed this session (source-confirmed only) |
| 5 | Sidecar pre-execution fast path | opt-in `CHUZOM_SIDECAR_PREFETCH=1`, non-zero-claude only, ~2730-2779 | Deterministic read-only prompts answered directly by the hook's own allowlisted handler (no external LLM call); `sys.exit(0)` | n/a (non-zero-claude only) | Not separately probed this session (source-confirmed only) |
| 6 | Continuation bypass (`_CONTINUATION_RE`) | ~2781-2800 | Short "strict-ack" continuations (yes/ok/do it) skip straight to Claude, `sys.exit(0)`, only when `not zero_claude and session_id`; kill-switchable via `CHUZOM_DISABLE_CONTINUATION_BYPASS=1` | n/a (normal-mode only by construction) | Not separately probed this session (source-confirmed only) |
| 7 | MCP capability match | `_match_mcp_server` ~2804-2833 | Prompts targeting an available non-chuzom MCP server (Obsidian/GitHub/Calendar) skip LLM routing | **No silent bypass** — `_block_zero_claude(...)` fires instead | Not separately probed this session (source-confirmed only) |
| 8 | Classifier-level skip | `classify_prompt()` ~1422-1429: `len(stripped) < 8` and `SKIP_PATTERNS.search(stripped)` (`^/(?:help\|clear\|login\|doctor\|config\|permissions\|status\|mcp\|bug\|claw\|loop\|checkpoint\|save-session\|resume-session\|sessions\|skill)\b`) | classifier returns `None` | n/a — feeds into main()'s downstream handling, both `hi` (2 chars) and `/status` produced empty stdout in hard/direct=1/normal | **Yes** — both `"hi"` and `"/status"` produced completely empty stdout |

**Highest-severity item: #1.** A malformed/corrupted stdin payload bypasses the hook entirely
— silently, with `rc=0` and zero output — **even when the operator has explicitly configured
zero-Claude/strict enforcement.** This is a genuine, execution-proven gap in the "every
eligible prompt is intercepted" / "guaranteed interception" claim: the very first line of
defense (JSON parsing) sits *ahead of* the zero-Claude gate, so a malformed payload cannot be
caught by strict mode no matter how it's configured.

Direct-Execution-specific gating (already covered in §2.1 — context-dependent prompts,
conversational context-inheritance, `task_type == "coordinate"`) only affects whether a *real
model* is called, not whether the hook fires at all; a Directive Injection (text-only
suggestion) still occurs in those cases.

---

## 5. The separate enforcement layer (`enforce-route.py`, PreToolUse hook) — reconciling the
   hard-mode banner text against the actual blocklist

The hard-mode Directive Injection banner (§2.3, `hard`/direct=0/normal cell) states, verbatim:

> "File reads and implementation tools (Edit/Write/Bash) stay allowed — only the route-first
> step is enforced, and only for the blocklisted tools for query."

Reading `enforce-route.py`'s actual dispatch logic (lines 1092-1330) resolves this precisely:

```python
_BASE_BLOCK_TOOLS   = frozenset({"Bash", "Edit", "MultiEdit", "Write", "NotebookEdit"})
_QA_TASK_TYPES       = frozenset({"query", "research", "generate", "analyze"})
_QA_ONLY_BLOCK_TOOLS = frozenset()   # deliberately emptied — INV-ROUTE-001/002/003

def _block_tools_for(task_type):
    if task_type in _QA_TASK_TYPES:
        return _BASE_BLOCK_TOOLS | _QA_ONLY_BLOCK_TOOLS   # == _BASE_BLOCK_TOOLS (empty union)
    return _BASE_BLOCK_TOOLS
```

For `enforce == "hard"` (lines 1170-1177):
```python
if tool_name in (_BASE_BLOCK_TOOLS | _QA_ONLY_BLOCK_TOOLS | {"Edit", "Write", "MultiEdit"}):
    pass  # falls through to BLOCK
```
i.e. for **any** task type including Q&A, `Bash`/`Edit`/`MultiEdit`/`Write`/`NotebookEdit` fall
straight into the violation/block path. Additionally, the read-only-Bash escape valve at
lines 1146-1165 is explicitly gated `if not _strict and task_type not in _QA_TASK_TYPES:` —
meaning for a `query`/`research`/`generate`/`analyze` task, **even read-only Bash commands
(`ls`, `cat`, `git status`) are NOT exempted** and fall into the same block path.

`Read`/`Glob`/`Grep`/`LS` are never members of `_BASE_BLOCK_TOOLS` in the first place, so they
are the only tools genuinely, unconditionally allowed (matching the "file reads... stay
allowed" half of the banner).

**Conclusion: the banner's claim about Edit/Write/Bash is false.** `enforce-route.py` in hard
mode blocks Bash/Edit/Write/MultiEdit/NotebookEdit outright pending routing compliance — it
does **not** let them "stay allowed." The only tools that stay allowed are the read-only
inspection tools (Read/Glob/Grep/LS). This is a **self-description accuracy bug**: the text
Claude is shown (and would reasonably act on) materially misstates what the paired PreToolUse
hook will actually do. Note this makes real enforcement *stricter* than advertised, not
weaker — so it is not a routing-guarantee hole by itself, but it is a genuine trust/accuracy
defect in the operator/agent-facing self-description. See `findings-A.json` CHZ-AUD-A-06.

Separately — and this **is** a routing-guarantee hole — because `enforce-route.py` is a
**PreToolUse** hook, it only ever fires when a tool is actually called. **A plain-text answer
that touches no tool at all (Claude simply typing a response to a Q&A prompt) never triggers
any PreToolUse hook, at any enforcement level, including "hard."** Structurally, "hard
enforcement" can force a *choice* between calling `llm_query` first or being blocked on
Bash/Edit/Write — but it cannot force Claude to route before answering a question in prose,
because answering in prose requires no blockable tool call in the first place. See
`findings-A.json` CHZ-AUD-A-07.

---

## 6. Summary of executed artifacts

| Artifact | Purpose | Location |
|---|---|---|
| `canary_harness.py` / `canary_results.json` | Task #1 — provider-attribution proof across 48 prompts | `/private/tmp/claude-501/-Users-yaliandrona-ai-job-search/07b9d5d1-cd6c-4aa8-a4db-b3cbb522c19a/scratchpad/` |
| `failure_ledger_probe.py` | Task #3 — real failure injection + real SQLite ledger inspection | same dir |
| `auto_route_hook_harness.py` / `auto_route_hook_results.json` | Task #2/#4 — real subprocess execution of `auto-route.py` across 9 mode cells + 6 skip-pattern cells | same dir |

All commands were run against `/Users/yaliandrona/Projects/Chuzom/.venv/bin/python`, with
hermetic per-run `HOME`/`CHUZOM_HOME` tmp directories; none touched the real `~/.chuzom` or
`~/.claude`.
