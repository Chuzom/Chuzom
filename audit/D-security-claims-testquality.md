# Chuzom Audit — Track D: Security/Privacy, Claims Verification, Test-Quality

**Auditor:** AUDIT-D (adversarial security auditor, principal engineer level)
**Checkout:** local, `/Users/yaliandrona/Projects/Chuzom`, commit `f5bf55c`
(full SHA `f5bf55c2a6e532229979ed90d376557f33698f57`), 2026-07-30 20:40:57 +0100. No GitHub clone used.
**Interpreter:** `/Users/yaliandrona/Projects/Chuzom/.venv/bin/python` for all executed tests.
**Test hygiene:** all executed tests ran under hermetic `HOME=<mktemp -d>` and `env -i PATH="$PATH"`
to avoid polluting the real `~/.chuzom`. All results below marked "executed"/"empirically proven" were
genuinely run; nothing was fabricated. Items not executed are explicitly marked **UNABLE TO VERIFY**
or **NOT-TESTABLE (this pass)**.

Companion files: `audit/findings-D.json` (5 machine-readable findings, schema-validated),
`audit/CLAIMS_VERIFICATION.md` (Phase 15 claim-by-claim table).

---

## Part 1 — Security/Privacy Findings (Phase 13)

### 1.1 CHZ-AUD-D-01 (CRITICAL) — Raw secret persistence in result/semantic caches

**One-line:** Every prompt/response routed through either the PUSH hook or PULL MCP tools is stored
**verbatim, unredacted** in SQLite (`result_cache.db`, `usage.db`'s `semantic_cache` table), full-text
indexed, retained indefinitely, and re-injected into future prompts — regardless of whether
`CHUZOM_REDACTION` is enabled.

**Planted-secret repro (executed this session, hermetic HOME):**

```
HOME="$TMPHOME" .venv/bin/python3 -c "
import sys; sys.path.insert(0,'src')
from chuzom import result_cache
result_cache.store_result(
    user_prompt='Here is my key sk-ant-api03-FAKEAUDITSECRETDONOTUSE1234567890ABCDEFGHIJ for testing',
    response='I see your AWS secret aws_secret_access_key=abcd1234FAKEAUDITSECRETwXYZ...',
    task_type='query', complexity='simple', model_used='test/fake-model')
"
```

**Proven outcomes:**
- `os.stat($TMPHOME/.chuzom/result_cache.db).st_mode & 0o777 == 0o644` (world-readable, not 0600).
- `sqlite3.connect(...).execute("SELECT user_prompt, response FROM results").fetchall()` returns both
  fake secrets **verbatim**.
- `grep -a 'FAKEAUDITSECRET' $TMPHOME/.chuzom/result_cache.db` (raw byte-grep, bypassing the SQLite
  API entirely) → **match**. Proves persistence at the file-bytes level, not just via the API.

**Why redaction doesn't help even if enabled:** the *only* redaction mechanism in the codebase
(`enterprise/redaction.py`, well-built: Luhn-checked cards, `sk-ant-`/`sk-`/`AIza`/`ghp_`/`AKIA`/`xox`/
JWT/private-key/email/SSN/phone patterns) is invoked *only* inside `router.py::route_and_call()`
(line 3205) — a different function from where either cache write happens (`router.py:2633`
`_dispatch_model_loop` for PUSH routing; `tools/text.py::_cache_result()` for PULL/MCP-tool routing).
It is never called from `result_cache.py` or `semantic_cache.py` at all. So even an operator who
explicitly sets `CHUZOM_REDACTION=on` gets **zero** protection for either cache.

Three independent secret-handling subsystems exist in this codebase with no shared enforcement point:
`secret_scrubber.py` (session JSONL log, always-on), `safe_subprocess.py::get_safe_env()`
(subprocess env-var blocklist, always-on, protects only the child-process environment block — not
argv, not stdout persistence), and `enterprise/redaction.py` (off by default, fail-open, wired only
into `route_and_call()`). None of the three touches either cache-write path.

**Severity rationale:** CRITICAL — this is durable, world-readable, full-text-searchable, unbounded
plaintext retention of exactly the class of content (API keys, credentials, PII) a router handling
third-party prompts is most likely to see, with a forward-propagation vector (`format_context()`
re-injects cached raw content into *future*, potentially less-trusted, model calls).

**Full detail, fix recommendation, regression test spec:** `audit/findings-D.json` → `CHZ-AUD-D-01`.

---

### 1.2 CHZ-AUD-D-02 (MEDIUM) — Inconsistent DB permission hardening

`cost.py::_get_db()` correctly hardens `usage.db` to 0600 before first connect
(`config.chuzom_db_path.touch(mode=0o600)`, explicit comment "stores sensitive cost/token data").
`result_cache.py::_ensure_db()` has no equivalent call — confirmed empirically (0o644 observed, see
1.1). The pattern exists correctly in one place in the codebase and simply wasn't reused in the other.
Widens the blast radius of D-01 on shared/multi-user machines.

---

### 1.3 SQL injection — **CLOSED, negative result**

Every `.execute(f"...")` / f-string-built-SQL call site found in the reviewed codebase was traced to
its origin and confirmed to interpolate only **hardcoded constants or a small closed enum of hardcoded
literals**, never user/model-controlled input:

| Site | Interpolated value | Origin | Verdict |
|---|---|---|---|
| `session-end.py:377-379` | `_col` | hardcoded tuple `("input_tokens", "output_tokens")` | SAFE |
| `lineage_store.py:168-179` | `col`, `ddl` | hardcoded tuple of 5 literal `(col, ddl)` pairs | SAFE |
| `dashboard_data.py:77-90` `_columns()` | `table` | only ever called with 2 hardcoded module constants (`_LEGACY_TABLE`, `_JSONL_TABLE`) — confirmed via grep of all 4 call sites (lines 185, 231, 289, 341) | SAFE |
| `identity.py:259` | (2-tuple) | hardcoded | SAFE (earlier turn) |
| `cost.py:3116` `time_filter` | SQL fragment | selected from small hardcoded dict | SAFE (earlier turn) |
| `budget_backend.py:262` | constant int | hardcoded | SAFE (earlier turn) |

**Conclusion: no exploitable SQL injection was found anywhere in the reviewed codebase.** This is a
definitive negative result (traced and ruled out), not an "unable to verify."

---

### 1.4 CHZ-AUD-D-05 (HIGH) — Enforcement-mode "never blocks" claim is FALSE relative to shipped default

Reclassified here as a **security-relevant** finding (in addition to its Phase 15 claims-accuracy
angle, see `CLAIMS_VERIFICATION.md` claim 1-3) because it directly bears on the audit brief's
instruction to flag any claim implying guaranteed non-enforcement that contradicts actual code
behavior, and because a security auditor (or an LLM agent) trusting the "no tool is ever blocked"
framing would materially misjudge the product's actual behavior.

**Summary:** `DEFAULT_ENFORCE = "smart"` (`enforce_config.py:36`) is the empirically-confirmed default
(hermetic pytest run, `test_enforce_default_consistency.py`, **5 passed**). Under "smart",
`enforce-route.py`'s real branch logic (lines 1178-1199) falls through to genuine violation-tracking
and blocking for `Edit`/`Write`/`MultiEdit`, contradicted by: the globally-installed
`rules/chuzom.md` ("no tool is ever blocked" — byte-identical `diff` confirmed against the live
`~/.claude/rules/chuzom.md`), the SessionStart banner ("never a block"), `session-start.py`'s
`_enforce_label()` (self-described as "honest — no hardcoding" yet mislabels both `smart` and `hard`
as never-blocking, and mislabels `soft` as the default), and `tools/setup.py`'s install message
(wrong on both the default-mode name and the blocking scope). **Decisively corroborated** by this
project's own correct, test-verified `Docs/configuration.md:35-48`, which accurately describes the
same subsystem — proving the contradiction is internal to the project's documentation corpus, not an
auditor misreading. Full evidence, 7-step repro, fix plan: `audit/findings-D.json` → `CHZ-AUD-D-05`.

**One gap honestly flagged:** a live PreToolUse-hook-deny repro (actually invoking Edit/Write under a
fresh session and confirming the exact deny mechanism — JSON `permissionDecision` vs. exit code 2)
was **not executed** this pass. The default-resolves-to-"smart" fact and the "smart"-blocks-by-code
fact are both proven; only the precise wire-level deny mechanism remains UNABLE TO VERIFY.

---

### 1.5 Security items scoped but NOT reached this pass (UNABLE TO VERIFY / not investigated)

Time across four compaction interruptions was concentrated on closing SQL injection and maximally
strengthening CHZ-AUD-D-05; the following originally-scoped Phase 13 items were **not completed**
and should be treated as open, not as clean:

- Full read of `config.py` (API-key/.env discovery + load order) — only grep-level excerpts reviewed.
- Full read of `claude_agent.py` and the tail of `codex_agent.py::run_codex()`.
- Individual env-filtering audit of ~26 other subprocess-calling files (`agentic_registry.py`,
  `agentic/acceptance.py`, `agentic/adapters.py`, `agentic/react.py`, `agentic/worktree.py`,
  `capabilities.py`, `cli.py`, `commands/dev_refresh.py`, `commands/doctor.py`, `commands/share.py`,
  `cost.py`, `gemini_cli_quota.py`, `hook_deadlock_detector.py`, `hooks/agent_loop.py`,
  `hooks/auto-route.py`, `hooks/library-harvest.py`, `hooks/session-end.py`, `hooks/session-start.py`,
  `hooks/usage-refresh.py`, `library/sealer.py`, `library/store.py`, `router.py`, `service_manager.py`,
  `sidecar.py`, `surface_status.py`, `team.py`, `tools/admin.py`) — only `safe_subprocess.py`'s
  blocklist mechanism itself was reviewed, not every call site's correct usage of it.
- `route_server.py`/`gateway.py` bind-address (0.0.0.0 vs localhost) and no-auth finding — carried
  over from an earlier turn as a suspected issue but **not concretely reproduced** this pass.
  **UNABLE TO VERIFY (not re-attempted this session).**
- `CHUZOM_SSE_ALLOW_PUBLIC` enforcement inside `server.py::main_sse_secured` — `server.py` not opened.
- `admin_api.py`'s "CHUZOM_METRICS_REQUIRE_AUTH=on (future slice)" comment — not investigated; the
  phrase "future slice" itself suggests the auth gate may not yet be implemented, which if true would
  be a real finding, but this was **not confirmed**.
- Other `.db` files' permissions beyond `usage.db` (confirmed 0600, good) and `result_cache.db`
  (confirmed 0644, bad, D-02) — `budget_store.py`, `lineage_store.py`,
  `storage/adapters/sqlite_adapter.py`, `control_plane/store.py` existence/permissions not checked.
- Malicious model-name handling (unsanitized use in file path/shell/SQL) — not investigated.
- Symlink/tmpfile safety (`library/sealer.py`, `library/pack.py`, cache dirs, `~/.chuzom/*` creation
  sites) — not investigated.
- Whether `sanitization.py`'s `sanitize_prompt`/`sanitize_messages` is wired into the live routing
  path or is dead code — not confirmed either way.
- Prompt-as-argv exposure (secrets visible via `ps`/`/proc` when passed as subprocess CLI args to
  codex/gemini) — not concretely reproduced.

**All items in this subsection are UNABLE TO VERIFY in this audit pass** — they are neither confirmed
vulnerable nor confirmed safe, and should not be read as "checked and clean."

---

## Part 2 — Claims Verification (Phase 15)

See `audit/CLAIMS_VERIFICATION.md` for the full claim-by-claim table. Summary:

- **3 claims classified FALSE**, all one connected root cause (enforcement-mode description never
  resynchronized after a prior mode-NAME fix): the global rules file / SessionStart banner
  ("never block"), `_enforce_label()`'s self-described-as-honest output, and `tools/setup.py`'s
  install-completion message.
- **1 claim classified MISLEADING** (by omission): the "audited"/RELEASE_QUALIFIED badge, which is
  scope-limited to cost/quality benchmarking in the body text but unqualified at the badge/headline
  level — ironic given this same audit found a live security gap (D-01) in the badge's own release.
- **2 claims independently PROVEN accurate**: the PUSH-routing "automatic and guaranteed" claim is
  correctly qualified and regression-tested (`test_chz_aud_012_028.py`); `Docs/configuration.md`'s
  Enforcement Modes table is itself correct and is the ground truth that exposes the 3 FALSE claims.
- **2 claim areas left NOT-TESTABLE this pass**: the self-annotated zero-Claude/block-mode bypass
  claim (tests not independently re-executed), and a long tail of README/CLI-help/other-rules-files/
  skills claims not re-extracted this pass due to time constraints.

---

## Part 3 — Test-Quality Table (Phase 3)

| Claim | Existing test | What it actually proves | Missing proof | Risk |
|---|---|---|---|---|
| Result/semantic caches don't leak secrets; DB files aren't world-readable | `tests/test_result_cache.py` (244 lines: `TestStoreResult`, `TestSearchResults`, `TestCheckDedup`, `TestFormatContext`, `TestSanitizeFtsQuery`, `TestClearCache`); `tests/test_semantic_cache.py` (306 lines: cosine-similarity math, embedding-fetch error handling, threshold config, cache-hit formatting); `tests/test_st004_semantic_cache_project_scope.py` (94 lines: cross-project-leak fix via `project_scope` column) | Functional correctness only — dedup logic, TTL query-time filtering, FTS5 ranking, ANN math, cross-*project* isolation. Grep for `secret\|redact\|scrub\|chmod\|0o600\|permission` across all three files → **zero substantive matches**. | No test asserts that a planted secret pattern (e.g. `sk-ant-...`) is absent from a raw SELECT or raw byte-grep of the DB file after `store_result()`/`store()`. No test asserts DB file mode is 0600. | **CRITICAL** — this is the exact test-quality gap that let CHZ-AUD-D-01 ship undetected: 550+ lines of active test coverage on the very functions that leak secrets, none of which looks at the dimension that matters (content sensitivity, file permissions). |
| Enforcement-mode "never blocks" banner/rules-file text accurately describes actual blocking behavior | `tests/test_enforce_default_consistency.py` (5 tests, executed hermetically this pass: **5 passed**); `tests/test_chz_aud_012_028.py::test_readme_enforcement_modes_note_advisory_nature` | `test_enforce_default_consistency.py` proves the **mode NAME** ("smart") is consistent across `enforce_config.py`/`repo_config.py`/`enforce-route.py` — i.e. no module disagrees on *which* mode is default. `test_chz_aud_012_028.py`'s test proves only that `soft`/`advise`/`suggest` are documented as never-blocking in the `Docs/configuration.md` corpus. | No test asserts that `_enforce_label()`'s human-readable **description** of `smart`/`hard` matches `enforce-route.py`'s actual branch behavior for those modes. No test cross-checks `rules/chuzom.md`'s blanket "never block" framing against `enforce-route.py`'s or `Docs/configuration.md`'s ground truth. No test checks `tools/setup.py`'s install message against the real default. | **HIGH** — three separate FALSE claims (CHZ-AUD-D-05, and claims 1-3 in `CLAIMS_VERIFICATION.md`) currently ship with zero regression coverage, despite a well-designed, actively-maintained test (`test_enforce_default_consistency.py`) already existing for the *adjacent* mode-name-consistency problem — the test author solved "do the modules agree on the NAME" but never extended it to "do the human-facing DESCRIPTIONS agree with the code." |
| SQL query construction is injection-safe | No dedicated test suite for this; verified this pass via manual source tracing of every `.execute(f"...")` site (see Part 1.3) | Nothing automated — this was a manual, one-time audit trace, not a regression-guarded property. | No test (e.g. a static-analysis lint rule, or a parametrized test that feeds adversarial `table`/`col` values into `_columns()`-style helpers) prevents a *future* refactor from introducing an unsafe interpolation into one of these currently-safe sites. | **LOW** (currently safe) but **MEDIUM** going forward — the safety of these sites depends entirely on call-site discipline (always passing hardcoded constants) that has no enforcement mechanism; a future contributor adding a new caller with dynamic input would not be caught by any existing test. |
| "Audited"/RELEASE_QUALIFIED badge scope | `README.md:169-183` body text (self-documenting, not a test) | The cost/quality benchmark methodology is described honestly in prose. | No test asserts the badge's alt-text or the heading immediately following it disambiguates "cost/quality audit" from "security audit." (Low priority — this is a documentation/wording risk, not a code-testable property in the traditional sense.) | **LOW** — wording/perception risk only; see CHZ-AUD-D-03. |

---

## Part 4 — Sibling Audit Coordination

Background audits "Audit A: routing execution proof" and "Audit C: packaging/install/concurrency"
were confirmed still running at last check and are covering non-overlapping scope (routing execution
proofs; packaging/install/concurrency) — no duplication with this Track D report, which is scoped to
security/privacy, claims verification, and test quality.

---

## Appendix — Findings Index

| ID | Severity | Title |
|---|---|---|
| CHZ-AUD-D-01 | CRITICAL | Raw secret persistence in result/semantic caches, world-readable, unbounded retention |
| CHZ-AUD-D-02 | MEDIUM | Inconsistent SQLite file-permission hardening (usage.db 0600 good; result_cache.db 0644 bad) |
| CHZ-AUD-D-03 | LOW | "Audited" badge scope ambiguity (cost/quality vs. security) |
| CHZ-AUD-D-04 | MEDIUM | Cache test suites assert only functional correctness, zero security-dimension coverage |
| CHZ-AUD-D-05 | HIGH | "Never blocks"/"advise mode" claim is FALSE relative to shipped default ("smart" blocks) |

Full machine-readable detail (evidence arrays, reproduction steps, root cause, recommended fix,
regression test spec) for each finding: `audit/findings-D.json`.
