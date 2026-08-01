# Chuzom — Claims Verification (Phase 15)

**Auditor:** AUDIT-D · **Scope:** README.md, pyproject.toml description, `src/chuzom/rules/chuzom.md`
(installed globally, byte-identical diff confirmed), SessionStart banner (`hooks/session-start.py`),
`Docs/configuration.md`, `tests/test_chz_aud_012_028.py` (existing regression coverage for a subset
of these claims). Commit: `f5bf55c` (2026-07-30 20:40:57 +0100). Local checkout only, no GitHub clone.

Taxonomy: **PROVEN** / **PARTIALLY-PROVEN** / **UNSUPPORTED** / **MISLEADING** / **FALSE** / **NOT-TESTABLE**

Where a claim was not independently re-verified this pass due to time constraints across four
compaction interruptions, it is marked **NOT-TESTABLE (this pass)** rather than silently omitted or
guessed at, per the audit's evidence-based mandate.

---

## 1. "advise mode: route everywhere, never block" (rules/chuzom.md) / "never a block" (SessionStart banner)

> **Claim (verbatim, `src/chuzom/rules/chuzom.md`):** "Global Routing Rules (advise mode: route
> everywhere, never block)" ... "They are a **default recommendation, not a constraint** — you
> always keep the final call, and **no tool is ever blocked**." ... "There is no 'blocked' state in
> advise mode."
>
> **Claim (verbatim, SessionStart banner, `hooks/session-start.py`):** "advise mode — a ROUTE hint
> is a suggestion, never a block."

**Classification: FALSE**

**Evidence:**
- `diff src/chuzom/rules/chuzom.md ~/.claude/rules/chuzom.md` → byte-identical. This is the literal
  file installed globally and read by the LLM as operating instructions every session (confirmed by
  its verbatim appearance in this very audit session's own context, three separate times).
- `src/chuzom/enforce_config.py:36`: `DEFAULT_ENFORCE = "smart"` — the single source of truth the
  module docstring says both the banner and the PreToolUse enforcer resolve through "so they can
  never disagree."
- `src/chuzom/hooks/enforce-route.py:1178-1199` (the real "smart"-mode branch, i.e. the default):
  `if tool_name in {"Edit", "Write", "MultiEdit"}: pass  # Fall through to violation handling` — this
  falls through to genuine violation-tracking/blocking logic (lines ~1201-1280), not a no-op. The
  same file's own module docstring (lines 37-41) states: "hard — Bash/Edit/Write are blocked for ALL
  task types until an llm_* tool is called."
- **`Docs/configuration.md:35-48`** — this project's own linked reference doc, independently verified
  accurate by the passing test `tests/test_chz_aud_012_028.py`, states correctly: `smart` (**default**)
  "Hard-blocks direct answers for Q&A tasks... Allows file tools for code tasks"; `hard` "Blocks
  Bash/Edit/Write for **all** task types until an `llm_*` tool is called." Only `soft`/`advise`/`off`
  are described there as never-blocking. **This means the contradiction is not merely "auditor
  reading vs. code" — it is two documents in the same repository describing the identical subsystem
  and reaching opposite conclusions.**
- Empirically executed this audit pass: `env -i PATH="$PATH" HOME=<hermetic tmp dir>
  .venv/bin/python -m pytest tests/test_enforce_default_consistency.py -v` → **5 passed**, proving
  via real execution (not just static reading) that a fresh install with no `CHUZOM_ENFORCE` env var
  and no config files resolves to `"smart"`, and that "smart" genuinely blocks.
- Full detail: finding **CHZ-AUD-D-05** in `audit/findings-D.json`.

**Existing test coverage:** `tests/test_chz_aud_012_028.py::test_readme_enforcement_modes_note_advisory_nature`
is properly scoped — it only asserts that `soft`/`advise`/`suggest` are described as never-blocking.
It does **not** assert anything about `smart`/`hard`, and does not read `rules/chuzom.md` or
`session-start.py`'s `_enforce_label()` output at all. **No existing test catches this contradiction.**

**Verdict:** The blanket "never block" / "advise mode" framing in the globally-installed rules file
and in the SessionStart banner directly contradicts the shipped default enforcement behavior of the
same product, and contradicts this project's own correct, test-verified `Docs/configuration.md`.
Classified FALSE rather than MISLEADING because the contradiction is direct, unqualified, and
concerns the single most safety-relevant dimension of the claim (whether tool calls can be denied).

---

## 2. `session-start.py::_enforce_label()` — "(honest — no hardcoding)"

> **Claim (verbatim, function docstring):** "Human description of the RESOLVED enforcement mode
> (honest — no hardcoding)... After P0, no mode blocks file/shell tools — the differences are only
> in logging."
>
> **Claim (verbatim, description dict):** `"smart"` and `"hard"` both labeled "file/shell tools never
> blocked"; `"soft"` labeled "— default".

**Classification: FALSE**

**Evidence:** Same as claim 1 above. Two independently falsifiable errors in one dict:
(a) `smart`/`hard` are labeled never-blocking when `enforce-route.py`'s own code and docstring say
otherwise; (b) `soft` is labeled the default when `enforce_config.DEFAULT_ENFORCE = "smart"` (also
empirically confirmed via the passing `test_enforce_default_consistency.py` run). The function's own
self-description ("honest — no hardcoding") is itself falsified by its output not matching the
enforcer it claims to describe.

**Verdict:** FALSE. This function actively misinforms the user via the SessionStart banner about the
one behavior (blocking) most relevant to deciding whether to trust "advise mode" framing.

---

## 3. `tools/setup.py` install-completion message

> **Claim (verbatim):** "Work that skips a required route is blocked by default
> (`CHUZOM_ENFORCE=hard`)."

**Classification: FALSE**

**Evidence:** Wrong on two independent counts: (a) `hard` is not the default — `smart` is
(`enforce_config.py:36`, empirically confirmed); (b) the phrasing implies blocking is exclusive to
opting into `hard` mode, when the actual default (`smart`) already blocks `Edit`/`Write`/`MultiEdit`
unconditionally for all task types per `enforce-route.py:1178-1199`.

**Verdict:** FALSE — this is the inverse error of claims 1-2 (those under-state blocking; this one
mislabels which mode name does the blocking), but all three trace back to the same root cause: the
mode-NAME was synchronized to "smart" across modules by a prior fix (see `test_enforce_default_consistency.py`'s
documented "F01" bug), but every human-readable description of what "smart" *does* was never
correspondingly updated.

---

## 4. README FAQ — "Push routing ... routing is automatic and guaranteed"

> **Claim area:** distinction between PUSH-hook (Claude Code UserPromptSubmit hook, automatic
> interception) and PULL-tool (explicitly-invoked MCP tools) routing, and whether either is
> "guaranteed."

**Classification: PROVEN (positive finding)**

**Evidence:** `tests/test_chz_aud_012_028.py::test_push_routing_guarantee_claim_is_qualified` asserts
the unqualified phrase "Push routing ... routing is automatic and guaranteed" does **not** appear in
the doc corpus (README + `Docs/configuration.md` + `Docs/ide-setup.md`), and a companion test
(`test_readme_clarifies_advisory_vs_direct`) asserts clarifying language ("advisory", "hint-only",
"additionalContext", "not guaranteed", etc.) IS present somewhere in that corpus. This test suite
documents that this exact claim was previously false ("The original false claim") and was corrected;
the regression test now guards against recurrence.

**Verdict:** This is a genuine positive: the PUSH vs. PULL distinction, and the advisory-vs-guaranteed
framing for the *routing-hint* mechanism specifically, is accurately described and has regression-test
coverage. This is a different subsystem from claims 1-3 above (which concern *tool-call blocking*, a
separate enforcement layer downstream of the routing hint) — the codebase gets the routing-hint
honesty right while getting the enforcement-mode-description honesty wrong. Both concern "is
something guaranteed/blocked," which is why this audit's brief specifically called out this
distinction as a scrutiny point; the audit confirms one half is handled well and the other is not.

---

## 5. "Direct execution mode" — zero-Claude / block-mode bypass

> **Claim area (`Docs/configuration.md`, self-annotated):** self-contained prompts under
> `CHUZOM_DIRECT_EXECUTION=true` are "rendered in block mode — the turn is answered entirely from the
> hook, Claude is never invoked, and zero subscription tokens are consumed," with an inline comment
> `<!-- claim-ok: block / zero-Claude preventing a Claude turn is verified by
> tests/test_zero_claude_bypass.py + test_zero_claude_sidecar_bypass.py (CHZ-AUD-005) -->`.

**Classification: NOT-TESTABLE (this pass) — self-annotated PROVEN, not independently re-verified**

**Evidence:** `tests/test_chz_aud_012_028.py::test_readme_direct_execution_section_exists_and_qualifies_block_guarantee`
confirms a "Direct execution mode" section exists and clarifies that context-dependent prompts still
go through Claude (i.e., the claim is correctly scoped to self-contained prompts only, not "every
prompt"). The stronger claim — that `test_zero_claude_bypass.py` / `test_zero_claude_sidecar_bypass.py`
actually prove zero-Claude-invocation — was **not independently read/executed** in this audit pass due
to time constraints. Good practice noted: the doc self-cites its own regression tests inline, which
is a positive documentation pattern regardless of this audit's ability to re-verify it this pass.

**Recommendation for a follow-up pass:** read and execute `tests/test_zero_claude_bypass.py` and
`tests/test_zero_claude_sidecar_bypass.py` directly to convert this from NOT-TESTABLE to PROVEN or
otherwise.

---

## 6. "Audited" / RELEASE_QUALIFIED badge

> **Claim (verbatim, README.md:26 badge):** "audit: RELEASE_QUALIFIED". **Claim (README.md:46):**
> "and now independently audited." **Claim (README.md:169-183, "Measured Results" section):** scoped
> explicitly to a cost/quality control-group benchmark.

**Classification: MISLEADING (by omission), not FALSE**

**Evidence:** See finding **CHZ-AUD-D-03** in `audit/findings-D.json`. The body text at
README.md:169-183 is itself honest and correctly scoped ("Chuzom v1.0.0 is the first release where
the savings claim is backed by a real, reproducible control-group benchmark") — this is a cost/quality
audit, not a security audit, and the text says so once a reader reaches it. No explicit
"security-audited" or "no known vulnerabilities" claim was found anywhere in README.md, pyproject.toml,
or CLI help text during this pass. However, the bare word "audit" in a badge and headline, with no
scope qualifier at the point of first mention, is likely to be over-read by a skimming user as
"reviewed for safety" — particularly ironic given this same audit pass independently discovered a live,
by-default-active, zero-test-coverage secret-persistence gap (CHZ-AUD-D-01) in the very release this
badge describes.

**Verdict:** MISLEADING-BY-OMISSION. Not FALSE, because the underlying claim (cost/quality benchmark
passed release gates) is itself well-evidenced and the body text is honest; the risk is purely at the
badge/headline level, before a reader reaches the scoping text.

---

## 7. "Enforcement Modes" section (`Docs/configuration.md`, general accuracy)

**Classification: PROVEN**

**Evidence:** Independently read (`Docs/configuration.md:35-48`) and confirmed to match
`enforce-route.py`'s actual branch logic exactly for `smart`/`hard`, and matches `enforce_config.py`'s
actual `DEFAULT_ENFORCE = "smart"` for the "(default)" annotation. This is the one place in the docs
corpus that gets the enforcement-mode description entirely right. It is the ground truth against
which claims 1-3 above were shown to be FALSE.

---

## 8. Claims not independently verified this pass (time/scope constraints)

The following claim areas, flagged in the original audit brief as requiring scrutiny, were **not**
independently re-extracted/re-verified in this specific pass, due to four consecutive compaction
interruptions consuming the majority of available turns on Phase 13 (security) work. They are listed
here rather than silently dropped, each marked **NOT-TESTABLE (this pass)**:

- README.md content past line ~320 (Routing at a Glance, Agentic Router, `/council` skill, Session
  Summary Dashboard, "works out of the box" claim at line 411, Benchmarks, FAQ beyond the two tests
  already covering it, Contributing, License).
- CLI `--help` output (not extracted this pass).
- Any "N% token savings" / "Nx" magnitude claims beyond the already-scoped, test-guarded "Measured
  Results (audited)" section (claim 6 above) — a full enumeration of every numeric savings claim
  site (README, pyproject description, install messages) was not completed.
- The other 13 host-specific rules files under `src/chuzom/rules/` (`codex-rules.md`,
  `cursor-rules.md`, `gemini-cli-rules.md`, etc.) — not checked for whether any of them ALSO carry the
  "never blocked" claim shown FALSE for `chuzom.md` in claim 1. Given `chuzom.md` (the Claude
  Code / global rules file) has this defect, and the enforcement-mode subsystem it describes is
  shared infrastructure, it is **likely but not confirmed** that some of these carry the same or a
  related defect — flagged as a priority for a follow-up pass.
  "**pyproject.toml** description text for the Cursor/Copilot/Windsurf 'best-effort, not guaranteed'
  framing (referenced in the carried-over technical-concepts context from earlier in this audit) was
  read in an earlier turn and found to correctly differentiate PUSH vs. PULL guarantee language — this
  is a positive finding consistent with claim 4 above, but was not re-verified with a fresh file read
  this pass.
- `skills/**` files — not read this pass for standalone claims.
- Zero-Claude bypass regression tests (claim 5) — not independently executed.

---

## Summary Table

| # | Claim | Source | Classification |
|---|---|---|---|
| 1 | "never block" / "advise mode" (global rules + banner) | `rules/chuzom.md`, `session-start.py` banner | **FALSE** |
| 2 | `_enforce_label()` "honest — no hardcoding" | `session-start.py` | **FALSE** |
| 3 | "blocked by default (`CHUZOM_ENFORCE=hard`)" | `tools/setup.py` | **FALSE** |
| 4 | PUSH routing "automatic and guaranteed" (qualified) | README FAQ | **PROVEN** (positive, test-guarded) |
| 5 | Zero-Claude / block-mode bypass | `Docs/configuration.md` (self-annotated) | **NOT-TESTABLE (this pass)** |
| 6 | "audited" / RELEASE_QUALIFIED badge | README.md badge | **MISLEADING** (by omission) |
| 7 | Enforcement Modes table | `Docs/configuration.md` | **PROVEN** |
| 8 | (multiple, see above) | README tail, CLI help, other rules files, skills/** | **NOT-TESTABLE (this pass)** |

**FALSE/MISLEADING claim count this pass: 3 FALSE (claims 1-3, all one connected root cause: the
enforcement-mode description was never resynchronized after the mode-NAME fix) + 1 MISLEADING
(claim 6, badge scope ambiguity). 2 claims independently PROVEN accurate (claims 4 and 7). 2 claim
areas left NOT-TESTABLE this pass for a follow-up auditor to close.**
