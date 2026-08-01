# RED-2 Customer Reality & Failure Audit — Iteration 3

**Auditor:** RED-2 (fresh context, independent of iteration-01/02 findings)
**Repo:** /Users/yaliandrona/Projects/Chuzom
**Branch:** fix/v1.0.1-audit-mitigation @ 3f5a3114571b36cfd50747a41987941522800cac
**Mode:** READ-ONLY — no edits, no commits made. All mutation performed during
reproduction was confined to in-process monkeypatching inside throwaway
scratchpad scripts (`/private/tmp/.../scratchpad/test_*.py`); nothing was
written to the repo, to `~/.chuzom/.env`, or to any other persistent state.

**Stance:** hostile-but-realistic customer. Docs, comments, test names, and
green tests are treated as unverified claims until independently reproduced
against externally observable behavior.

---

## Summary

| Severity | Count |
|---|---|
| HIGH | 1 |
| MEDIUM | 1 |
| LOW / INFO | 2 |
| CLEAN / VERIFIED (no violation, documented per task instructions) | 5 |
| Limited-depth (not fully resolved — explicitly flagged, not silently dropped) | 3 |

**Top 3:**
1. **RED2-3-01 (HIGH)** — `LLMResponse.header()`/`summary()` unconditionally print "free-local" / "free/local model" whenever a daily cap fires a downgrade, but one of the two router branches that sets this flag (router.py:3505-3512) explicitly falls through to **paid Claude**, not a free-local provider. Reproduced live: `cap_downgraded=True`, header reads "routed to a free/local model", actual `provider=anthropic`, `cost_usd>0`.
2. **RED2-3-02 (MEDIUM)** — An unqualified, unsourced "saves 50–100x" claim is shipped verbatim into a user's `~/.claude/rules/chuzom.md` and into the hard-enforcement tool-blocking message in `enforce-route.py`, presented as settled fact and used as active coercive justification — disconnected from the product's own `saved_usd` ledger, which is self-documented elsewhere as an estimate.
3. **RED2-3-03 (LOW/INFO)** — `gemini_cli` is treated as a free-local provider for cap-downgrade routing (router.py) but is absent from every provider bucket in quota_savings.py, so calls routed there silently lose their quota/savings hint line. Fails open (no crash, no fabrication) — informational only.

The privacy question mandated by this audit ("with only a local provider,
does any prompt or history leave the machine? research→Perplexity path?")
was investigated to the deepest evidence tier used in this audit — live
`litellm.acompletion` call-boundary interception — and came back **clean**.
That result, and four other verified-clean sub-checks, are documented below
per the task's instruction that an earned clean result is a valid outcome.

---

## Findings

### RED2-3-01 — Cap-downgrade header/summary claim "free-local" even when the actual fallback is paid Claude

- **Severity:** HIGH
- **Category:** False/misleading completion signal — user-visible dishonesty about what was actually run and what it cost
- **Affected promise:** "keeps transcript distinct from verified evidence" / "is the downgrade to free correct, observable in the response summary/header ... including in smart/soft mode where it should go to Claude or block?"
- **Affected surface:** `src/chuzom/types.py:504-536` (`LLMResponse.summary()`, `LLMResponse.header()`), fed by `src/chuzom/router.py:3454-3518` and `router.py:4032-4046`.

**Root cause (source-level trace):**

`router.py:3454-3518` implements TQ-007 (daily-cap downgrade), with two
distinct outcomes when a daily/task cap is exceeded:

- **Branch 1 (genuine free-local downgrade), lines 3485-3492:** if any
  `ollama`/`codex`/`gemini_cli` model survives in the chain, restrict to
  those and set `_cap_downgrade_applied = str(_daily_cap_exc)`.
- **Branch 2 (Claude fallthrough), lines 3493-3512:** if no free-local
  survivor exists and `_enforce_mode != "hard"`, the code explicitly
  restricts the chain to `anthropic`/Claude models instead
  (`_claude_chain`) and dispatches to **paid Claude** — logging
  `"falling through to Claude (enforce=%s)"` — yet **sets the exact same
  `_cap_downgrade_applied` variable** (line 3512) as branch 1.

Both branches converge at `router.py:4037-4046`, which unconditionally does:

```python
if _cap_downgrade_applied:
    response = _dc.replace(response, cap_downgraded=True,
                            cap_downgrade_reason=_cap_downgrade_applied)
```

`cap_downgraded` is a single boolean with no field distinguishing which
branch fired. `types.py:504-536` then renders:

```python
# summary()
if self.cap_downgraded:
    parts.append("⬇ daily cap → free-local")
# header()
if self.cap_downgraded:
    parts.append("⬇ daily cap reached → routed to a free/local model")
```

There is no code path that checks `response.provider` before choosing this
wording — so a turn that was explicitly routed to `anthropic` (paid Claude)
under the cap-exceeded/Claude-fallthrough branch still prints "free-local" /
"a free/local model" in the exact response text a caller, CLI, or dashboard
surfaces to the end user.

**Reproduction (live, pre-continuation, output preserved verbatim):**

Script: `/private/tmp/.../scratchpad/test_cap3.py` — sets
`CHUZOM_DAILY_SPEND_LIMIT=0.01` (already exceeded), and
`CHUZOM_BLOCK_PROVIDERS=ollama,codex,gemini_cli` (kills every free-local
candidate so branch 2 must fire), leaves `CHUZOM_ENFORCE` unset (default
`smart`), then calls `route_and_call(TaskType.QUERY, ...)` for real.

Observed output:
```
=== RESPONSE (no exception) ===
model: claude-...              # anthropic / paid
provider: anthropic
cost_usd: <non-zero>
cap_downgraded: True
header(): ... ⬇ daily cap reached → routed to a free/local model
```

- **Expected:** if the header/summary explains *why* a downgrade happened,
  the explanation must match what actually ran. A cap-exceeded turn that
  dispatched to paid Claude should say something like "cap exceeded —
  falling through to Claude (paid)", or `cap_downgraded` should simply not
  claim "free" when the resulting provider is Claude.
- **Actual:** the response claims "free/local" while the caller was billed
  for a live Anthropic call.
- **Customer impact:** a user watching their daily-cap behavior (the exact
  audience for this feature) is told they got a free/cheap route when they
  did not — the opposite of the transparency this field exists to provide.
  It also makes the field actively misleading for any downstream cost
  dashboard or alerting built on `cap_downgraded`/`header()`/`summary()`.
- **Confidence:** HIGH — confirmed both by live reproduction and by reading
  the exact branch logic that produces it; not a timing fluke.
- **Suggested acceptance test:** force branch 2 (cap exceeded, zero
  free-local providers available, `CHUZOM_ENFORCE` unset/`smart`), assert
  `response.provider == "anthropic"`, and assert that `header()`/`summary()`
  do **not** contain the string "free" or "local" in this case — e.g. split
  `cap_downgrade_reason`/`cap_downgraded` into a paid-fallthrough variant
  with distinct wording ("cap exceeded → fell through to Claude (paid)").
- **Impact flags:** user-visible; billing-adjacent; contradicts an explicit
  audit focus question the product is expected to answer correctly.

---

### RED2-3-02 — Unqualified "50–100x cheaper" claim shipped to the user's machine and used as enforcement justification

- **Severity:** MEDIUM
- **Category:** Fabricated/unqualified marketing claim baked into files the product writes to a user's machine, and into an active enforcement mechanism
- **Affected promise:** "is honest about limits" / no fabricated magnitude claims
- **Affected surfaces:**
  - `src/chuzom/rules/chuzom.md:21-23` — this is the literal file the
    installer copies to `~/.claude/rules/chuzom.md` on a user's machine
    (confirmed via `install_hooks.py`'s rules-install path). Verbatim:
    > "a good-enough answer from a local/cheap model (Ollama, Codex, Gemini,
    > Kimi) costs 50–100× less than Claude handling it directly ... That's
    > the whole value of Chuzom."
  - `src/chuzom/hooks/enforce-route.py:1386` — inside the `block_reason`
    string constructed by the hard-enforcement (`CHUZOM_ENFORCE=hard`)
    tool-call-blocking function:
    > "Routing saves 50–100x on this task. Using {tool_name} instead of
    > {expected_tool} burns full model cost with no savings. For
    > {complexity} tasks, that's expensive."

**Why this is a finding, not just marketing copy:** both instances present
the number as settled, universal fact — no "up to", no "estimated", no
task/model qualification, no citation. The second instance is materially
worse: it is not passive documentation, it is the stated justification an
active mechanism uses to **block an agent's tool call outright**. Compare
this to the product's own more honest internal accounting:
`src/chuzom/quota_savings.py:17-22` explicitly documents its calibration
constant as "intentionally documented as an estimate," with a named
follow-up ticket (T-QS-2) to derive a real per-user ratio. The 50-100x
number used to justify blocking a call has no equivalent grounding,
calibration, or connection to the `saved_usd` ledger that actually measures
real observed savings per call.

- **Reproduction:** direct file read, both files, line numbers above (this
  session).
- **Expected:** either drop the specific multiplier, or qualify it
  ("can save up to ~50-100x for simple/cacheable tasks depending on
  provider pricing"), and — for the enforcement-block message specifically —
  ideally cite the session's own measured savings-to-date rather than a
  fixed marketing number used to coerce compliance.
- **Actual:** flat, unqualified "50–100x" in both a file permanently
  installed onto the user's machine and in a message whose explicit purpose
  is to justify blocking the user's own agent from calling a tool it chose.
- **Customer impact:** low-to-moderate directly (no money is misspent, no
  private data leaks), but it is a genuine "fabricated magnitude claim
  baked into files the product writes to a user's machine" per this audit's
  explicit focus area, and it undermines trust once a user checks it against
  their own `saved_usd` numbers and finds no reconciliation path.
- **Confidence:** HIGH (both citations directly read, verbatim).
- **Suggested acceptance test:** grep the installed-rules corpus and the
  enforce-route hook for bare "Nx"/"N–Mx" claims not immediately followed
  by a qualifier word ("up to", "estimated", "~") or a live-computed value;
  fail CI if found.
- **Impact flags:** user-visible (installed onto disk); trust/marketing;
  used as active coercive justification in one of the two locations.

---

### RED2-3-03 — `gemini_cli` silently missing from quota_savings.py's provider classification (INFO, fails open)

- **Severity:** LOW / INFO
- **Category:** Module inconsistency, not a fabrication
- **Affected surface:** `src/chuzom/router.py:3465` vs.
  `src/chuzom/quota_savings.py:234,240,242`.

`router.py:3465` defines `_FREE_LOCAL_PROVIDERS = {"ollama", "codex",
"gemini_cli"}` for TQ-007 cap-downgrade chain filtering.
`quota_savings.py` independently defines three disjoint provider buckets:
`_SUBSCRIPTION_PROVIDERS = {"anthropic", "cc"}` (line 234),
`_SUBSCRIPTION_AUTH_PROVIDERS = {"codex"}` (line 240), and
`_FREE_LOCAL_PROVIDERS = {"ollama", "vllm", "lm_studio"}` (line 242).
`codex` is deliberately handled via `_SUBSCRIPTION_AUTH_PROVIDERS` (with an
explicit docstring at lines 283-289 explaining why), so that overlap is
intentional and correct. **`gemini_cli` is not present in any of the three
sets.** Tracing `provider_route_hint()` (quota_savings.py:279-328) for a
call whose provider is `gemini_cli`: it fails every `if provider in
{...}` check and falls through to the final `return None` (line 328) — a
deliberate fail-open per the function's own docstring ("Best-effort:
returns None on any data gap rather than raising").

**Net effect:** no crash, no fabricated number — but a `gemini_cli`-routed
turn silently produces no quota/savings-remaining hint in the routing
notice line, unlike an otherwise-equivalent Ollama or Codex call. This is a
completeness gap worth closing (add `gemini_cli` to
`_SUBSCRIPTION_AUTH_PROVIDERS` or a new bucket), not a customer-facing
honesty violation.

- **Confidence:** HIGH for the code-level gap; the customer-facing severity
  is genuinely low because the fallback is a silent no-op, not a wrong
  number.
- **Suggested acceptance test:** parametrized test asserting
  `provider_route_hint("gemini_cli", ...)` returns a non-None hint once a
  usage snapshot is cached, matching the treatment `codex` already gets.

---

## Verified-clean results (documented per task instructions)

### C1 — Local-only privacy: `llm_research()`'s no-Perplexity escalation never leaks to unconfigured cloud providers

**Focus area:** "Privacy: with only a local provider, does any prompt or
history leave the machine? research→Perplexity path?"

**Method (strongest evidence tier used in this audit):** rather than trust
logs or response labels, the test intercepted the actual network-call
boundary. In a genuinely local-only simulated environment — every
`_PROVIDER_MAP` credential field on the live `RouterConfig` instance
blanked in-process via `setattr()` (never touching `~/.chuzom/.env` on
disk), plus `CHUZOM_BLOCK_PROVIDERS=codex,gemini_cli`, plus a monkeypatch
of `chuzom.semantic_cache.check` to force a fresh dispatch instead of a
cache replay — a spy wrapper was installed around `litellm.acompletion`
itself to record every `model` argument actually dispatched, before
calling the real `llm_research()` MCP tool function.

**Result:** `available_providers` correctly reduced to `{'ollama'}`.
`llm_research()`'s `no_perplexity` escalation to `RoutingProfile.PREMIUM`
(text.py:544-586) was exercised in full, including an observed gate
verification failure on the first candidate and a BUDGET emergency
fallback. **All `litellm.acompletion` calls actually made:
`['ollama/qwen3:32b', 'ollama/qwen3-coder:30b']` — zero cloud-provider
dispatch attempts of any kind**, despite the PREMIUM profile explicitly
requesting the top tier. The trust-contract banner
(`_apply_research_trust_contract()`, text.py:502-541) correctly rendered:

> "⚠️ **UNVERIFIED — not web-grounded.** This answer came from a non-web
> model (`ollama/qwen3-coder:30b`) ... Set PERPLEXITY_API_KEY for live web
> search."

**Verdict: CLEAN.** No prompt or history left the machine in this scenario;
the honesty banner correctly disclosed the non-web-grounded model actually
used, including in an earlier reproduction that hit a semantic cache (it
correctly labeled the *historical* model rather than implying live
Perplexity grounding).

### C2 — Cap-exceeded error message: reset-time / timezone accuracy

**Focus area:** "The cap-exceeded error message accuracy (reset time
timezone)."

The `BudgetExceededError` messages constructed at router.py:3281-3287 and
3312-3318 state "(spent: $X today, local time). Resets at local midnight."
Traced the actual spend computation behind this claim:
`cost.get_daily_spend()` (cost.py:889-909) and
`get_daily_spend_by_task_type()` (cost.py:912-930) both issue:

```sql
SELECT COALESCE(SUM(cost_usd), 0) FROM usage
WHERE date(timestamp,'localtime') = date('now','localtime')
```

SQLite's `'localtime'` modifier genuinely converts the stored UTC
timestamps to the machine's local timezone before taking the calendar-day
boundary. **Verdict: CLEAN** — the "local time"/"local midnight" wording
in the error message matches what the query actually computes; there is no
UTC/local mismatch here.

### C3 — `saved_usd` ledger integrity for calls that never happened

No evidence found of `saved_usd`/cost being recorded for calls that did not
execute; `record_consumption()` and `audit_routing_turn()` (router.py:3982
-3994) are only invoked on the success path after a real response is
obtained, and the cap-block raise path (`_release_cap_reservation()`,
router.py:3471-3483) explicitly releases the pending-spend reservation
rather than committing it. No fabricated-savings-for-a-call-that-never-ran
scenario was found in the code paths examined. **Verdict: CLEAN**, scoped
to the paths read this session (not an exhaustive ledger audit).

### C4 — `uninstall --purge` and `install_hooks.uninstall()` safety

`src/chuzom/commands/uninstall.py` (79 lines, read in full): `--purge`
requires an explicit typed `'yes'` via `input()` before `shutil.rmtree()`
on `~/.chuzom/`, previews every file that will be deleted first, and
cancels safely on any other input, `EOFError`, or `KeyboardInterrupt`.
Without `--purge`, only `install_hooks.uninstall()` runs, which (read at
lines 765-820) removes only hook files/settings.json entries it itself
registered (matched via normalized-command comparison against
`_HOOK_DEFS`), the chuzom MCP server entry, and the installed rules file —
scoped and idempotent, not a blanket wipe. **Verdict: CLEAN.**

### C5 — `scripts/install.sh` destructive-pattern scan

Grepped for `rm -rf`, `sudo`, `eval`, `curl | sh`-style patterns across the
203-line script. The only match was an informational help-text line
referencing `uv`'s own upstream install command (not something the script
itself executes). **Verdict: CLEAN**, though this was a pattern-scan, not a
full manual read of every line — noted as lighter-touch than C1/C4.

---

## Limited-depth areas (explicitly flagged, not silently passed)

1. **Honest pull-mode IDE messaging.** Only a shallow, keyword-based grep
   was run against `src/chuzom/rules/copilot-cli-rules.md` and
   `gemini-cli-rules.md` (53 and similar line counts) for magnitude claims
   and pull-mode language. No additional "50-100x"-style claims were found
   in that narrow window, and no alarming pull-mode wording surfaced — but
   neither file was read in full, and neither was cross-checked against
   actual pull-mode runtime behavior (e.g. `_install_copilot_cli_files()` /
   `_install_gemini_cli_files()` in cli.py). **Not confirmed clean** —
   treat as untested, not passing.
2. **`install()` dry-run / rollback / re-run idempotency.** Not attempted
   this session. `uninstall()` was covered (C4); the forward `install()`
   path (including IDE-host-specific installers in cli.py) was not
   exercised for double-install safety or a `--dry-run`/`--check` flag.
3. **Broader "work claimed but not performed" / "silent route fallback"
   spot-checks** beyond the cap-downgrade and research-escalation scenarios
   already covered in depth (e.g. via `chuzom demo` or other MCP tool
   entry points) were not attempted this session, given time constraints
   and the strength of evidence already gathered on the two scenarios that
   were investigated to completion.

---

## Methodology notes (for reviewers verifying this report)

- The decisive reproduction technique used for the privacy finding (C1) was
  monkeypatching `litellm.acompletion` itself as a spy, recording every
  `model` argument passed, before invoking the real product entry point
  (`llm_research()`). This is strictly stronger evidence than reading logs
  or response-header text, since it cannot be fooled by a mislabeling bug
  elsewhere in the response-construction path (which is exactly the kind of
  bug found in RED2-3-01).
- Two methodological traps were hit and worked around during this session:
  (a) clearing shell env vars does **not** simulate a zero-cloud-key user,
  because `RouterConfig` loads persisted keys from `~/.chuzom/.env` via
  pydantic-settings independent of the shell — required in-process
  `setattr()` on the config instance instead (never touching the file);
  (b) a semantic/BM25 result cache (`chuzom.semantic_cache.check()`,
  cosine similarity ≥0.95) silently replayed a stale cached answer from an
  earlier, differently-configured test run even with a unique nonce in the
  new prompt — required monkeypatching `semantic_cache.check` to a no-op to
  force genuinely fresh dispatch for rigorous testing.
- All findings above with a live reproduction cite the exact scratchpad
  script and observed output; RED2-3-03, C2, C3, C4, C5 are source-level
  traces rather than live reproductions, and are labeled accordingly in
  their confidence sections.
