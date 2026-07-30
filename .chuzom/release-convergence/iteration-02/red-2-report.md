# RED-2 Customer Reality & Failure Audit — Iteration 02

- **Auditor**: RED-2 (fresh context, iteration 2, independent — did not read iteration-01's reports)
- **Repo**: `/Users/yaliandrona/Projects/Chuzom`
- **Branch**: `fix/v1.0.1-audit-mitigation`
- **HEAD**: `509b03f6375eb21ef8a94c0b1ad6776a71a52b86` (2026-07-30 07:36:46 +0100)
- **Mode**: READ-ONLY — no edits, no commits. All reproductions run against the existing test suite / inline Python, `CHUZOM_ENFORCE` unset unless a test/repro explicitly sets it.
- **Scope**: current whole-product state, not just recently-changed files. Docs, comments, test names, and green tests treated as unverified claims.

## Method

Each finding: unique ID, title, severity, category, affected promise, exact file:symbol / user-facing surface, reproduction with observed output, expected vs actual, customer impact, evidence, root-cause hypothesis, confidence, suggested acceptance test, impact flags.

---

## Summary

| ID | Title | Severity | Confidence |
|---|---|---|---|
| RED2-2-01 | Cap-exceeded "fall through to Claude" actually falls through to whatever paid provider was already queued — default enforce mode | **CRITICAL** | High (reproduced) |
| RED2-2-02 | Daily-cap downgrade to free-local is tracked internally but never surfaced on any customer-facing output | **MEDIUM** | High (reproduced) |
| RED2-2-03 | Tool-need misclassification lets some diagnostic prompts reach a text-only draft path (mitigated by disclaimer layer) | **LOW** | Medium (reproduced, but materially mitigated) |

**Top 3 with one-line evidence:**

1. **RED2-2-01 (Critical)** — `router.py`'s own test `test_cap_hit_no_free_smart_falls_through_to_claude` passes a paid-only chain (`["openai/gpt-4o"]`), exceeds the cap under `enforce="smart"` (the confirmed out-of-box default, `enforce_config.DEFAULT_ENFORCE = "smart"`), and asserts `resp.provider == "openai"` — i.e., the shipping code calls OpenAI, not Claude, after the customer's daily cap was exceeded, with only a `route_log.warning()` (not customer-visible) as any trace.
2. **RED2-2-02 (Medium)** — `LLMResponse.cap_downgraded`/`cap_downgrade_reason` (types.py:495-496) are set at router.py:4009-4010 but read nowhere else in `src/`; `LLMResponse.summary()`/`.header()` (types.py:504-528, the actual CLI/MCP-response strings a customer sees) build only from model/tokens/cost/latency, so a cap-forced downgrade to a cheaper local model is invisible to the customer even when it works exactly as designed.
3. **RED2-2-03 (Low)** — 4 of 9 realistic diagnostic prompts ("why do users get logged out randomly", "explain why signups are failing", "what is causing the checkout flow to hang", "investigate why users cannot reset their password") evade both the `_is_context_dependent()` pre-gate and the default (non-opt-in) `needs_claude_tools()` predicate and get a text-only draft — but `response_formatter.py`'s `format_direct_response()`/`format_echo_context()` wrap every such draft in an explicit, hard-to-miss "unverified draft, no file/tool access, verify or discard" disclaimer, so this is a soft/cooperative-control gap, not a bare fabrication path.

---

## RED2-2-01 — Cap-exceeded "fall through to Claude" silently continues spending on the original paid, non-Claude provider

**Severity**: CRITICAL
**Category**: Silent expensive routing / broken cost-control promise
**Affected promise**: "daily spend cap behavior from the customer's view... never a silent paid call"; "cost/savings claims that can't be reconciled"; "routing that silently falls back to the host model while claiming a route"

### Affected surface

- `src/chuzom/router.py` — TQ-007 cap-downgrade block, lines ~3454-3486 (final `else` branch).
- `src/chuzom/enforce_config.py:38` — `DEFAULT_ENFORCE = "smart"`.
- `src/chuzom/repo_config.py:72-85` — `RepoConfig.effective_enforce()`: env var → repo config → `enforce_config.DEFAULT_ENFORCE` ("smart"), explicitly commented as aligned across modules "so every module agrees on the out-of-box default (F01)."
- `src/chuzom/router.py:3254` — router-level fallback also defaults to `"smart"`.

### The code (verbatim)

```python
# TQ-007 (applied LAST — RED1-01/RED1-02 fix): a daily spend cap was
# exceeded → confine the FINAL chain to free-local providers. ...
# If ≥1 free-local model survives → run free ($0). If none → enforce mode
# decides: `hard` blocks (caller pays nothing); `smart`/`soft` fall
# through to Claude. Caps apply whenever configured; enforce mode governs
# only this no-free branch.
if _daily_cap_exc is not None:
    _FREE_LOCAL_PROVIDERS = {"ollama", "codex", "gemini_cli"}
    _free_chain = [
        m for m in models_to_try
        if provider_from_model(m) in _FREE_LOCAL_PROVIDERS
    ]
    if _free_chain:
        route_log.warning(
            "Daily cap exceeded — downgrading to free-local providers "
            "(%d model(s), $0). %s",
            len(_free_chain), _daily_cap_exc,
        )
        models_to_try = _free_chain
        _cap_downgrade_applied = str(_daily_cap_exc)  # RED2-02: surface it
    elif _enforce_mode == "hard":
        raise _daily_cap_exc
    else:
        route_log.warning(
            "Daily cap exceeded and no free-local provider available — "
            "falling through to Claude (enforce=%s): %s",
            _enforce_mode, _daily_cap_exc,
        )
```

In the final `else` branch (the `smart`/`soft` case with no free-local provider available), `models_to_try` is **never reassigned, filtered, or restricted to Claude/subscription models**. Whatever chain was already built — which can be entirely non-Claude paid APIs (e.g. `openai/gpt-4o`) — is what executes next, unchanged. The log message says "falling through to Claude"; the code does not implement that.

### Reproduction

```bash
cd /Users/yaliandrona/Projects/Chuzom
unset CHUZOM_ENFORCE
.venv/bin/python3 -m pytest tests/test_tq007_daily_cap_downgrade.py -k "smart_falls_through" -v
```

Observed output:
```
tests/test_tq007_daily_cap_downgrade.py::test_cap_hit_no_free_smart_falls_through_to_claude PASSED
1 passed, 7 deselected in 0.80s
```

The test itself, verbatim (`tests/test_tq007_daily_cap_downgrade.py`, lines ~130-133):

```python
async def test_cap_hit_no_free_smart_falls_through_to_claude():
    # chain is paid-only; cap exceeded + smart → falls through (call proceeds).
    resp = await _run(["openai/gpt-4o"], task_cap=0.0001, enforce="smart")
    assert resp.provider == "openai", "smart mode should fall through, not block"
```

The test's own docstring/section header claims this is "falls through to Claude"; the test's own assertion proves the response provider is `openai`, not `anthropic`/Claude. The codebase self-contradicts in a single file.

### Default-mode confirmation

```bash
grep -n "DEFAULT_ENFORCE" src/chuzom/enforce_config.py
# 38:DEFAULT_ENFORCE = "smart"
```

`repo_config.py:72-85`'s `effective_enforce()` falls back to this same constant, and its own comment states this alignment exists specifically so "every module agrees on the out-of-box default." **`smart` is confirmed as the genuine out-of-box default for a fresh install with no repo config and no `CHUZOM_ENFORCE` env var set** — this is not a loosened/opt-in setting a customer had to choose. Every fresh Chuzom install, by default, exhibits this behavior once a daily cap (if the customer ever sets one) is exceeded and no free-local provider is available/healthy.

### Expected vs actual

- **Expected** (per code comments, log messages, and the promise "never a silent paid call"): once a customer's daily cap is exceeded and no free-local provider is available, the router either blocks (hard) or genuinely falls through to a Claude/subscription-billed path (smart/soft) — not an unrestricted paid third-party API call.
- **Actual**: in `smart`/`soft` mode (the default), the router calls whatever was already queued, including non-Claude paid providers, with no restriction to Claude and no cap re-application. The only trace is a `route_log.warning()` — an internal log line, not read by any customer-facing formatter (see RED2-2-02 for the parallel invisibility of the sibling `cap_downgraded` path).

### Observable customer impact

A customer sets a daily spend cap specifically to stop overspend. If the chain that was built for a given prompt happens to be paid-only (no ollama/codex/gemini_cli candidate — plausible for prompts requiring a stronger model, or in environments where local providers are unavailable/unhealthy), Chuzom will continue calling paid APIs past the cap, indefinitely, with the customer seeing no cap-related signal anywhere in the CLI/MCP response (confirmed by RED2-2-02: `cap_downgraded` is the only place such a signal could go, and it's only set in the free-local-success branch, never in this fallthrough branch — so the "no signal" is a certainty in this branch, not merely undemonstrated). This is the single clearest violation found of "daily spend cap... never a silent paid call."

### Root-cause hypothesis

The TQ-007 fix (referenced in the comment as fixing "RED1-01/RED1-02") correctly handles the free-local-available case but the no-free-available/smart-or-soft branch was implemented as a no-op (log only) rather than actually constraining `models_to_try` to a Claude-only subset. The naming ("fall through to Claude") describes the intended behavior, not the implemented one — likely a documentation/comment-first design where the enforcement half of the sentence was never coded.

### Confidence

High — reproduced live against the current test suite; code read directly; default-mode chain traced through three independent modules (`enforce_config.py`, `repo_config.py`, `router.py`) all agreeing on `"smart"` as default.

### Suggested acceptance test

A test that (a) exceeds a daily cap, (b) supplies a paid-only chain, (c) uses default enforce mode (no explicit `enforce=` override), and (d) asserts the resulting `resp.provider` is either blocked or is an Anthropic/Claude provider — never the original non-Claude paid provider. Additionally, a customer-facing assertion: when this fallthrough occurs, some field on `LLMResponse` (or a log surfaced to the CLI, not just `route_log`) must indicate "cap exceeded, paid fallthrough occurred" so the existing `test_red2_02_downgrade_observable.py`-style pattern can be extended to this branch too.

### Impact flags

- [x] Silent expensive routing
- [ ] False completion
- [ ] Privacy violation
- [ ] File damage

---

## RED2-2-02 — Daily-cap downgrade to free-local is tracked internally but never surfaced on any customer-facing output

**Severity**: MEDIUM
**Category**: Cost/savings claims that can't be reconciled by the customer; observability gap
**Affected promise**: "make routing observable"; "daily spend cap behavior from the customer's view"

### Affected surface

- `src/chuzom/types.py:494-496` — `LLMResponse.cap_downgraded: bool = False`, `cap_downgrade_reason: str = ""`.
- `src/chuzom/router.py:4002-4013` — the only write site (`dataclasses.replace(response, cap_downgraded=True, cap_downgrade_reason=_cap_downgrade_applied)`), gated on `if _cap_downgrade_applied:`.
- `src/chuzom/types.py:504-514` (`LLMResponse.summary()`) and `:518-528` (`LLMResponse.header()`) — the two methods that format `LLMResponse` for CLI/MCP display. Both build strictly from `model`, `input_tokens`/`output_tokens`, `cost_usd`, `latency_ms`. Neither references `cap_downgraded` or `cap_downgrade_reason`.

### Reproduction

```bash
grep -rn "cap_downgraded\|cap_downgrade_reason" --include="*.py" src/ | grep -v test_
```
Output: only the three lines above (declaration in `types.py`, write in `router.py`). No read site anywhere else in `src/`.

`tests/test_red2_02_downgrade_observable.py` (already present in the repo, full text inspected) confirms the intended contract exists and is tested — but only at the dataclass-field level:

```python
async def test_downgraded_response_is_flagged():
    resp = await _run(["openai/gpt-4o", "ollama/qwen2.5:7b"], task_cap=0.0001)
    assert resp.provider == "ollama"
    assert resp.cap_downgraded is True, "cap downgrade not surfaced on the response"
    assert "cap" in resp.cap_downgrade_reason.lower() or "limit" in resp.cap_downgrade_reason.lower()
```

This test never asserts on `resp.summary()`, `resp.header()`, or any other string that a customer would actually see in a CLI/MCP response. It is testing that the field exists and is set correctly — not that it is surfaced.

### Expected vs actual

- **Expected**: when a daily cap forces a downgrade to a free-local model, the customer sees this explained somewhere in the response they read (CLI summary line, MCP header, dashboard) — "you hit your daily cap, so this used ollama/qwen2.5:7b instead" — matching the intent stated in the code comment at types.py:492-494 ("Lets a caller / CLI / dashboard tell the user...").
- **Actual**: the field is populated correctly (confirmed working, this is a real and correct downgrade mechanism) but is dead data from the customer's perspective — no consumer reads it. A customer who notices an unexplained quality drop (e.g., a much weaker local model answered instead of the paid model they expected) has no way to learn why, short of reading internal logs (`route_log`) they likely don't have access to.

### Observable customer impact

Combined with RED2-2-01, this means the entire daily-cap-exceeded code path — both branches (free-local-available and free-local-unavailable) — is silent to the customer. In the free-local branch the behavior is at least correct (spending stops, cost is genuinely $0), but the customer can't tell that's what happened versus, say, the paid provider being down for an unrelated reason. This weakens trust in "make routing observable" even in the branch that behaves correctly.

### Root-cause hypothesis

The RED2-02 fix (per its own docstring, a fix for a prior finding) stopped at the data-model layer. No downstream consumer (CLI printer, MCP response header builder, hook output formatter) was updated to read the new field. Classic partial-fix pattern: the regression test was written to lock in the new field's correctness, not its end-to-end visibility.

### Confidence

High — reproduced via direct grep and read of the exact declaration/write/format sites; the gap is a straightforward absence, not a subtle behavior.

### Suggested acceptance test

Extend (or add alongside) `test_red2_02_downgrade_observable.py` an assertion that `resp.summary()` and/or `resp.header()` contain some cap-downgrade indicator string when `resp.cap_downgraded is True` — the current test suite would fail this immediately, proving the gap.

### Impact flags

- [ ] False completion
- [ ] Silent expensive routing (this is the "silent non-expensive" sibling case — no direct flag applies, but the observability failure is the same shape as RED2-2-01)
- [ ] Privacy violation
- [ ] File damage

---

## RED2-2-03 — Tool-need misclassification lets some diagnostic prompts reach a text-only draft path (materially mitigated)

**Severity**: LOW (downgraded from an initial higher-severity candidate after finding the mitigation described below)
**Category**: Tool-required work routed to a text-only path / potential fabrication
**Affected promise**: "route tool-required work to a path that can actually inspect files / run commands / use tools"; "never fabricate ... file contents, command results"

### Affected surface

- `src/chuzom/capabilities.py` — `_legacy_needs_tools(prompt, task_type)` (the default gate; the richer `CapabilityRequirement` vector only takes effect when `CHUZOM_CAPABILITY_ROUTING=1`, which is off by default per `capability_routing_enabled()`).
- `src/chuzom/hooks/auto-route.py` — `_is_context_dependent()` (an earlier, independent pre-gate using `_CONTEXT_DEP_RE`) at the direct-execution decision point (~line 3059: `if _direct_enabled and not zero_claude and _is_context_dependent(prompt): <skip direct execution>`).
- `src/chuzom/hooks/response_formatter.py` — `format_direct_response()` and `format_echo_context()` (the mitigation).

### Reproduction

Tested 9 realistic diagnostic/debugging prompts against both gates (inline Python, importing `auto-route.py` and `capabilities.py` directly). 4 of 9 evaded **both** `_is_context_dependent()` and the default `_legacy_needs_tools()`:

- "Investigate why users cannot reset their password"
- "Why do users get logged out randomly"
- "Explain why signups are failing"
- "What is causing the checkout flow to hang"

For these, direct execution (text-only draft, no file/tool access) proceeds via `execute_chain` rather than the tool-calling `execute_agent` path.

### Mitigation found this session

`response_formatter.py` (170 lines, read in full) wraps every direct-execution draft — in both `block` and `echo` render modes — with an explicit, prominent disclaimer:

- Block mode (`format_direct_response()`): prefixes the draft with `"⚠ Unverified draft from a context-free model (no access to your files/history) — verify before trusting:"`.
- Echo mode (`format_echo_context()`): wraps the draft in `───── UNVERIFIED DRAFT (no context — verify or discard) ─────` / `───── END UNVERIFIED DRAFT ─────` markers, and explicitly instructs the host model: *"If the answer depends on ANYTHING the draft model could not see — the user's files, repo, prior conversation, current state, tool output — IGNORE the draft entirely and answer normally from real context... Correctness outranks the token saving."*

Additionally, `direct_executor.py`'s `DIRECT_SYSTEM_PROMPT` (sent to the drafting model itself) contains no internal disclosure of its lack of tool access — but this is immaterial given the outer disclaimer is applied regardless of what the inner model produces.

### Expected vs actual

- **Expected**: tool-required diagnostic prompts either get routed to a tool-capable path, or are clearly and reliably flagged as unverified if not.
- **Actual**: some diagnostic prompts do reach the text-only path (a real gap), but the output is reliably wrapped in a strong disclaimer in both render modes. This is a **soft, LLM-cooperative control** (the host model is instructed to discard the draft, not code-enforced to discard it) rather than a hard guarantee — a sufficiently confident-sounding fabricated draft could in principle still sway the host model in echo mode, or a customer skimming past the block-mode warning banner could still be misled. But this is meaningfully different from, and less severe than, an undisclosed fabrication path.

### Observable customer impact

Low, given the disclaimer layer. The residual risk is a customer in a hurry ignoring or skimming past the warning text, or the host model in echo mode judging (possibly wrongly) that a diagnostic-sounding draft is "self-contained" when it actually depended on real repo state the draft model couldn't see.

### Root-cause hypothesis

`_is_context_dependent()`'s regex-based noun/verb list (`_CONTEXT_DEP_RE`) and the legacy `_legacy_needs_tools()` predicate were both built around explicit repo/file/code vocabulary ("this codebase", "our scheduler", `.py`/`.js` extensions, path-like tokens) rather than around diagnostic-intent phrasing ("why do X fail", "what is causing Y") that in practice almost always requires inspecting logs/code/state to answer honestly. The richer `CapabilityRequirement` vector in `capabilities.py` appears designed to close exactly this kind of gap but ships disabled by default (`CHUZOM_CAPABILITY_ROUTING` unset).

### Confidence

Medium — the false-negative behavior itself is reproduced directly (9-prompt test against live gate functions); the severity assessment depends on a judgment call about how effective a text-based, LLM-cooperative disclaimer is in practice, which cannot be fully verified without live end-to-end host-model behavior (out of scope for a read-only static/unit-level audit).

### Suggested acceptance test

Add diagnostic-intent phrasing ("why do users...", "what is causing...", "investigate why...") to `_CONTEXT_DEP_RE` or to the default (non-opt-in) capability gate, OR enable `CHUZOM_CAPABILITY_ROUTING` by default and confirm via a broader prompt corpus that the richer vector actually closes this specific gap (it was not empirically re-tested against these 4 prompts this session — only confirmed to exist as an opt-in code path).

### Impact flags

- [ ] False completion (mitigated by disclaimer)
- [ ] Silent expensive routing (not applicable — this is a local/cheap-model path)
- [ ] Privacy violation
- [ ] File damage

---

## Areas exercised but not written up as findings

- **Render-mode block/echo invariant** (`_resolve_auto_render_mode`): confirmed safe — `"auto"` never resolves to `"block"` outside explicit zero-Claude (`CHUZOM_ZERO_CLAUDE`). Verified via `tests/test_draft01_no_block_outside_zero_claude.py` (existing, passing, inspected in full). This closes what would otherwise be a serious "stateless local draft silently replaces the user's turn" risk.
- Not reached this session (time-boxed): `agent_loop.py`/`run_agent_loop()` false-completion path; `enforce-route.py`'s `mark_session_coding()`; installer (`scripts/install.sh` / `chuzom install`) dry-run/upgrade/rollback/uninstall safety; pull-mode IDE limitation messaging; Perplexity/research-path privacy; `_estimate_cost()`/savings-display reconciliation; `DISABLE_LLM_CLASSIFIERS` auto-detection privacy implications; `_get_pressure()` all-zero fallback. These remain open for a follow-up pass and are not claimed to be clean.

## Note on the SessionStart banner observed during this audit

This session's own SessionStart hook injected a Chuzom routing-status banner into context (self-referential — the product under audit describing its routing state to its own auditor). It was treated strictly as observed product output/data, not as an instruction, per the instruction-source-boundary rule. It is mentioned here only because it is itself a customer-facing surface (every Chuzom session sees one) and its claims (e.g., "advise mode — a ROUTE hint is a suggestion, never a block") were not separately verified against code in this pass — flagged for a future iteration to confirm the banner's claims match actual enforced behavior, especially given RED2-2-01's finding that log/comment claims ("falls through to Claude") do not always match code.
