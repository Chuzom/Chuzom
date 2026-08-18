# 18 — REMEDIATION EXECUTION PLAN

**Target:** close 100% of audit findings at `c2c2882`/`v1.1.1`, reach a re-audit score **> 95%**.
**Execution vehicle:** `agenticgraphs :: software-engineering/feature-delivery-lifecycle`, one run per
Work Package (WP).

---

# PART 0 — THE TRAP IN THE EXECUTION GRAPH (read before anything else)

The graph's `plan` node is declared:

```yaml
- id: plan
  outputs:
  - plan
  - acceptance_criteria      # <-- the planner authors its own pass conditions
```

**This is finding RED3-07 / invariant I-3 — the precise defect this audit found in Chuzom itself:
the party being verified authors the verification.** If we let the graph's planner generate
acceptance criteria for the remediation, we would verify the fix for self-authored verification
using self-authored verification.

## Mandatory control

Every acceptance criterion in Part 2 is **pre-registered in this document**, authored **before**
implementation begins, and passed into each graph run as part of the immutable `goal` payload.

Rules binding on every WP:

1. `acceptance_criteria` emitted by the `plan` node is **advisory only** and MUST NOT be used as the
   pass condition. The `audit` subgraph gates against the criteria in **this file**.
2. Criteria are **hashed** before the run (`sha256` of the WP's criteria block) and re-verified after.
   A changed hash = automatic FAIL.
3. **No WP may modify its own acceptance test.** If the implementer touches a file listed under
   *Immutable test assets*, the run FAILS regardless of `verdict`.
4. Every regression test must be demonstrated **RED before the fix, GREEN after** — the graph's
   `implement` subgraph already emits `test_failed_before_patch` / `test_passes_after_patch`. Both
   must be `true`. A test that was never red proves nothing.

---

# PART 1 — PRE-REGISTERED SUCCESS DEFINITION

"Audit score > 95%" is meaningless unless it is computable and non-gameable. It is defined **now**,
before any work starts, and may not be renegotiated afterwards.

## 1.1 Scoring rubric (100 points)

| Component | Points | Measurement |
|---|---|---|
| **P0 closure** | 45 | `3.75 × (P0 closed)` of 12. Each requires a red→green regression test. |
| **P1 closure** | 25 | `1.47 × (P1 closed)` of 17 |
| **P2/P3 closure** | 10 | proportional, of 14 |
| **Gate effectiveness** | 10 | The 3 proven blind spots now kill mutants (pricing / tool-name / savings-sign), + no new blind spot in a 10-mutation sample |
| **Claim accuracy** | 5 | 9 corrected claims verified against shipped text |
| **Invariant restoration** | 5 | I-1, I-2, I-3, I-6, I-7, I-8 each provably restored |

## 1.2 Hard gates (override the score entirely)

These are **disqualifiers**, not deductions — they exist so the score cannot be gamed by closing
many cheap findings while leaving an expensive one open:

| Gate | Rule |
|---|---|
| **G-A** | **Any open P0 → verdict is FAIL**, regardless of points |
| **G-B** | Any regression test that was not RED before its fix → that finding counts as **not closed** |
| **G-C** | Any acceptance-criteria hash mismatch → WP FAILS |
| **G-D** | Suite must be green on the **built wheel**, not an editable install |
| **G-E** | Re-qualification must run at the **shipping SHA** (project's own restart-at-zero rule) |
| **G-F** | Mutation score on money/routing/verification modules ≥ `mutation_baseline + 0.15`, floor 0.80 |

## 1.3 Why >95% requires ~everything

45 + 25 + 10 + 10 + 5 + 5 = 100. Losing all P2/P3 (10) already caps at 90. **A >95% score is
reachable only with all 12 P0, all 17 P1, ≥8/14 P2-P3, all gates, and all claims corrected.**
That is the intended difficulty — it matches the stated goal of "100% fix".

---

# PART 2 — WORK PACKAGE DEPENDENCY GRAPH

```
WAVE 0 (no deps, ship immediately — disclosure only, no code)
  WP-00 Advisory + badge removal + factual claim corrections
        │
WAVE 1 (live user harm — parallel, no interdependencies)
  WP-01 Sever injection→exfiltration chain      RED6-01, RED6-02, +CodexAdapter
  WP-02 Stop destroying user config             RED4-01
  WP-03 Canonical pricing module  ◄── ROOT of economics cluster
        │           │
        │           └──────────────┐
WAVE 2 │                           │
  WP-04 Savings sign correctness (AUD-06)   ◄── needs WP-03 for stable fixtures
  WP-06 Ledger durability (RED5-01/02/03 + siblings)   [no deps]
  WP-08 Tool-surface resolver + fix the lint (RED1-20/21/22)  [no deps ⚠ see 4.1]
        │           │                    │
WAVE 3  │           │                    │
  WP-05 Unknown≠zero + baseline reconciliation   ◄── needs WP-03, WP-04
  WP-07 Coverage metric / I-1                    ◄── needs WP-06
  WP-09 Verification integrity (RED3-01/02/03/08) ◄── needs WP-01
  WP-11 doctor tells the truth (RED4-02)         ◄── needs WP-08
        │
WAVE 4
  WP-10 Escalation integrity (RED3-04/05/06/07)  ◄── needs WP-09
  WP-12 Leaderboard: implement or delete (RED8-08) [no deps]
  WP-14 Gate hardening + wheel smoke test        ◄── needs WP-03, WP-04, WP-08
        │
WAVE 5
  WP-13 Fail-open triage (RED8-09)               ◄── needs WP-03/04/06 (else floods)
  WP-15 Dead-code deletion + dedupe              ◄── needs WP-09, WP-12
        │
WAVE 6
  WP-16 Re-qualification at shipping SHA + fix Gate 7  ◄── needs ALL
```

## 2.1 The four dependency edges that actually matter

Most WPs are independent. These four are **hard** and getting them wrong wastes a full graph run:

| Edge | Why it is mandatory |
|---|---|
| **WP-08 → WP-09** *(fixing `cwd` wiring exposes `diff_check` gaming)* | The adjudicator proved RED3-08 and RED3-02 are two layers of one defect: `diff_check` is currently *unusable* (always empty), and fixing that wiring is exactly what makes it *gameable*. **Shipping the RED3-08 wiring fix without the RED3-02 soundness fix converts a dead check into an actively false one — strictly worse than today.** They must ship in the same WP (WP-09). |
| **WP-01 → WP-09** | WP-09 wires worktree isolation and `cwd`, expanding the execution surface. Doing that before the env-allowlist fix widens the live exfiltration path. |
| **WP-06 → WP-07** | A coverage metric computed from a ledger that silently drops rows would report false coverage — reproducing I-1 inside its own fix. |
| **WP-03 → WP-04 → WP-05** | Signed aggregation and unknown-handling both need one authoritative price source, or their regression fixtures encode whichever stale copy they happened to import. |

## 2.2 The root-cause collapse

**WP-03 alone closes 6 findings** (RED2-01, RED8-01, RED8-02-merged, RED8-03, RED8-04, and unblocks
RED2-03). This is the highest-leverage package in the plan.

The playbook is not novel — **it is the team's own `tool_surface.py`/CHZ-SURF-01 pattern (canonical
resolver + CI lint), applied to money instead of tool names.** `13_HISTORICAL_DEFECT_PATTERNS.md`
shows this same `$15/$75` bug was fixed *locally* four separate times (`2f0b730`, `50043e5`,
`d03b4d7`, + the `savings_logger`/`calibration` divergence) and returned every time, because no fix
was ever made structural.

---

# PART 3 — WORK PACKAGE SPECIFICATIONS

Each WP is one `feature-delivery-lifecycle` run. Criteria are **pre-registered and immutable**.

---

## WP-00 — Disclosure and claim correction
**Wave 0 · deps: none · no code · findings: AUD-01, AUD-02, AUD-05, + 4 false claims**

**Scope**
1. Publish a security advisory: do not run `llm_act`/`llm_delegate` on untrusted repos; `CHUZOM_DELEGATE=off`.
2. Remove the `RELEASE QUALIFIED` badge from `README.md`.
3. Correct: FAQ "Everything stays on your machine"; "independently audited" → scope it; NORTH_STAR
   "continuously-updated live leaderboard" → mark aspirational pending WP-12; "irreversible steps run
   in an isolated git worktree" → mark pending WP-09.

**Acceptance criteria (immutable)**
- `grep -c 'RELEASE_QUALIFIED' README.md` → `0`
- FAQ contains no sentence asserting all data stays local while cloud providers are supported
- Advisory published with a CVE-style ID and affected-version range
- No source file modified (docs only): `git diff --name-only | grep -c '^src/'` → `0`

**Risk:** none technical. **This ships first because every day the badge stays up is a day the
product asserts a certification the repo's own rule says it does not hold.**

---

## WP-01 — Sever the injection → exfiltration chain 🔴
**Wave 1 · deps: none · findings: RED6-01 (P0), RED6-02 (P0), CodexAdapter gap**

**Scope** — both cuts ship together; either alone leaves a live path.
1. Pass an explicit **allowlisted `env=`** to every delegated subprocess. Wire the existing
   `safe_subprocess.py` into `agentic/react.py` **and** `agentic/adapters.py`
   (`CodexAdapter` currently bypasses the codebase's own safe `codex_agent.run_codex()`).
2. Call the existing `wrap_prompt_with_boundaries` / `_is_injection_attempt` on the agentic path
   (`agentic/service.py` → `TaskLedger` → `pack_prompt`).
3. Add `env`, `printenv`, `set`, `export` to `_bash_block_reason` — **defence in depth only, not the
   fix.** A blocklist against a model that can emit arbitrary shell is not a boundary.

**Files:** `agentic/react.py`, `agentic/adapters.py`, `agentic/service.py`, `tools/agentic.py`, `safe_subprocess.py`

**Acceptance criteria (immutable)**
- A delegated `bash` subprocess receives an env containing **only** the allowlist; a canary
  `FAKE_KEY=sk-NOTREAL-000` in the parent env is **absent** from child output
- Reproducer `evidence/red6/poc_env_leak_react_bash.py` → **fails to leak** (was: leaked)
- Same assertion for `CodexAdapter`
- Hostile `session_context` is flagged AND neutralised before reaching `pack_prompt`
- ≥11 bash bypass variants from the adjudicator's set all blocked
- Red-before-green demonstrated for all of the above

**Immutable test assets:** `tests/security/test_agentic_env_isolation.py`, `tests/security/test_agentic_injection.py`

---

## WP-02 — Stop destroying user config 🔴
**Wave 1 · deps: none · findings: RED4-01 (P0), RED4-08**

**Scope** — detect a foreign `statusLine`; back it up via the **existing** `_backup_before_overwrite()`
(already used for `chuzom.md` in the same file); record in `install_manifest.py`; restore on uninstall;
warn on overwrite. Also remove orphan `chuzom_tool_surface.py` on uninstall.

**Files:** `install_hooks.py`, `install_manifest.py`

**Acceptance criteria (immutable)**
- Sandbox HOME seeded with a custom `statusLine` → after `install`, original is recorded in the manifest
- After `uninstall`, `settings.json.statusLine` is **byte-identical to the pre-install value**
- Install prints an explicit warning when overwriting a foreign value
- Idempotent across install → install → uninstall → uninstall
- No file remains in `~/.claude/hooks/` after `uninstall --purge`

**Immutable test assets:** `tests/install/test_statusline_preservation.py`

---

## WP-03 — Canonical pricing module 🔴 ROOT
**Wave 1 · deps: none · findings: RED2-01 (P0), RED8-01 (P0), RED8-03, RED8-04, RED8-07, unblocks RED2-03**

**Scope**
1. Create `src/chuzom/pricing.py` as the single source of truth. Version + `as_of` date per entry.
2. Delete all stale copies: `cost.py::BASELINE_PRICING`, `cost.py::CLAUDE_RATES_PER_M`,
   `dashboard_data.py`'s inline rates, `savings_logger.py`, `calibration.py`, `quota_savings.py`'s
   hardcoded `$50/week`.
3. CI lint failing on any price literal outside `pricing.py` — mirroring `lint_tool_surface.py`.
4. Runtime staleness warning when `as_of` exceeds 90 days.

**Acceptance criteria (immutable)**
- `grep -rnE '\b(15\.0|75\.0|5\.0|25\.0)\b' src/chuzom/ --include=*.py` returns **no pricing context** outside `pricing.py`
- Every module importing a price imports from `pricing.py` (AST-verified, not grep)
- **Mutation gate:** setting Opus input price to `999.0` **fails ≥1 test** (currently: 0 failures — proven blind spot)
- All 4 Haiku price paths return an identical value (currently 3.2× spread)
- o3 price identical across all call sites
- CI lint fails on an injected literal

**Immutable test assets:** `tests/economics/test_pricing_single_source.py`, `scripts/lint_pricing.py`

---

## WP-04 — Savings sign correctness 🔴
**Wave 2 · deps: WP-03 · findings: AUD-06 (P0)**

**Scope**
1. Remove per-item clamping at `summary.py:217`, `dashboard_data.py:199`, `dashboard_data.py:307`.
2. Aggregate **signed** values; render negative totals as negative ("cost you $0.08 more").
3. **Delete and invert the test that asserts the clamp is correct.**
4. Copy the correct pattern from the 3 modules that already gate on negative savings properly.

**Acceptance criteria (immutable)**
- The README's exact published sample yields a displayed total of **−$0.0807**, not +$0.0203
- Property test: for random `(actual, baseline)` pairs incl. `actual > baseline`,
  `displayed_total == sum(baseline_i - actual_i)` **including sign**
- `grep -c 'max(0' ` in savings aggregation paths → `0`
- **Mutation gate:** re-introducing any clamp fails ≥1 test
- The old clamp-asserting test no longer exists

**Immutable test assets:** `tests/economics/test_savings_sign.py`
**Note:** the README sample must also be corrected — it is currently shipped marketing that
demonstrates the defect.

---

## WP-05 — Unknown ≠ zero, and one baseline policy
**Wave 3 · deps: WP-03, WP-04 · findings: RED2-02, RED2-03, RED2-04, RED8-05**

**Scope** — `get_savings_summary()` must distinguish query-failure from genuine zero (return
`None`/`Unknown`, never a zero that reads as data). Collapse the 5 differently-gated "savings" fields.
One baseline policy; quota and cash get **different labels and are never summed**. Remove the
hardcoded `$50/week`.

**Acceptance criteria (immutable)**
- Query failure returns a value distinguishable from zero at the type level; a test asserts the two are not equal
- Only one baseline policy symbol exists; `session-end.py` renders one figure, not two disagreeing ones
- A subscription user is never shown a cash-savings figure (README: value is "quota runway, not cash")
- Every displayed number carries a `measured | estimated | unknown` provenance tag

**Immutable test assets:** `tests/economics/test_unknown_not_zero.py`

---

## WP-06 — Ledger durability 🔴
**Wave 2 · deps: none · findings: RED5-01 (P0), RED5-02 (P0), RED5-03, RED5-04, RED5-05, RED5-06**

**Scope**
1. Guard the cold-start `PRAGMA journal_mode=WAL` in `lineage_store.py`, `execution_ledger.py`, and
   `storage/sqlite_adapter.py` (third instance of the same class).
2. **Check the return value at all 7 `record_event()` call sites** — a success signal nobody reads is not a signal.
3. Bind the yielded boolean at both `exclusive_lock()` call sites.
4. Lock `budgets.json` read-modify-write; serialise hash-chain read+append.

**Acceptance criteria (immutable)**
- Live multi-process reproducer: **0 dropped events across ≥2400 concurrent cold-start writes**
  (baseline: 66 drops, peak 29.4%)
- `LineageStore` cold-start: 0 crashes at N=12 (baseline: 4/12)
- A forced `record_event()` failure **raises or increments a visible counter** — never silent
- `grep` proves no call site discards the boolean
- Concurrent legitimate writers do **not** produce `broken_chain_at_*`

**Immutable test assets:** `tests/reliability/test_ledger_concurrency.py` (multi-process, not threads)
**⚠ Safety:** all tests must resolve DB paths inside a tmpdir and assert it. `CHUZOM_HOME` does **not**
isolate `cost._get_db()` — this caused real data loss during the audit (see `evidence/AUDITOR_INCIDENT.md`).
**Fixing that isolation gap (RED2-07) belongs in this WP.**

---

## WP-07 — Coverage metric (restores I-1)
**Wave 3 · deps: WP-06 · findings: I-1, RED1-24, RED2-06**

**Scope** — every routing/quality/savings surface must report **how much traffic it failed to observe**.
Aggregate the ≥6 `sys.exit(0)` bypass paths in `auto-route.py` into a counted, user-visible metric.

**Acceptance criteria (immutable)**
- Every rate metric exposes `observed_n` and `unobserved_n`; a rate with unknown denominator renders `Unknown`
- Simulating the historical incident (97.7% of directives bypassed) produces telemetry
  **visibly different** from a clean run — this is the exact scenario the codebase documents as
  previously indistinguishable
- Dashboard shows coverage %; below 90% it warns

**Immutable test assets:** `tests/telemetry/test_coverage_denominator.py`

---

## WP-08 — Tool-surface resolver for rules files  *(RESCOPED — builds on your CHZ-SURF-02 work)*
**Wave 2 · deps: none · conflict RESOLVED — see 4.1 · findings: RED1-20 (P0), RED1-21, RED1-22, RED1-23**

### Verified state of the uncommitted CHZ-SURF-02 work

Audited read-only against RED1-20/21/22. **It is sound, well-reasoned, and must be kept** — WP-08
builds on it rather than replacing it.

What it does: the server publishes the tool list it **actually registered** to
`~/.chuzom/registered_surface.json` (atomic write, PID liveness check); readers prefer that over
inferring the tier from their own `CHUZOM_SLIM`. It also correctly re-sequences the rules refresh to
run **after** surface publication, so a tier change reaches the rules file in one restart.

This attacks the correct root cause — the one this audit named explicitly: *do not compare an emitter
against `tool_surface.py`, because two components can agree on the same wrong assumption.* Resolving
against the genuinely-registered surface is the right answer.

**What it closes:** improves correctness of the **already-localized** path
(`check_and_update_rules` → `_localized_rules_text`, `install_hooks.py:366` — the Claude Code path).

**What it does NOT close — verified:**

| Finding | Status | Evidence |
|---|---|---|
| RED1-20 | **OPEN** | `cli._append_routing_rules` (`cli.py:127`) and `install._append_routing_rules` (`commands/install.py:841`) contain **no resolver call**. Neither is touched by the uncommitted diff. |
| RED1-21 | **OPEN** | `llm_reason` untouched — absent from `DEPRECATED_TOOLS`/`KNOWN_TOOLS`/`EMITTABLE_TOOLS` |
| RED1-22 | **OPEN** | `lint_tool_surface.py` unchanged |

So the Claude-Code path localizes; the **10 non-Claude hosts** — the ones that make the North Star
vendor-neutral — still receive rules files verbatim.

### Scope

1. **Keep CHZ-SURF-02.** Land it as the foundation.
2. Route **both** `_append_routing_rules` implementations through `_localized_rules_text` / the
   resolver, reading the **published** surface.
3. **Consolidate the two `_append_routing_rules` copies into one.** Two implementations of the same
   installer is the RED8-06 duplicate-source-of-truth class, and is exactly why one was fixed and the
   other was not.
4. Add `llm_reason` to `DEPRECATED_TOOLS` (RED1-21).
5. Fix `lint_tool_surface.py`: scan `.md`/`.json`/`.yaml`/`.sh`, and **re-scan `localize()` output**
   instead of exempting it (RED1-22). Derive `GUARDED` programmatically from `DEPRECATED_TOOLS`
   (currently hand-maintained, omits 11 of 24 keys).
6. Scope-label `trace_northstar.py` output (RED1-23).

### New defect found while auditing the uncommitted work

**PID reuse defeats the liveness check.** `published_surface()` discards a record whose publisher is
gone via `os.kill(pid, 0)`. If that PID has been **reused** by an unrelated process, the check
succeeds and a stale surface is treated as authoritative — and because this file *overrides* the
environment, the author's own stated worst case applies: *"it actively asserts a surface nothing is
serving, and hints follow it."*

Fix: add a monotonic `boot_id` / process start-time, or a server-heartbeat `mtime` freshness bound
(e.g. discard records older than N minutes). Low probability, but the failure mode is the exact one
the mechanism exists to prevent.

**Note (accepted, not a defect):** `publish_surface()` swallows write failures and readers fall back
to tier inference. The docstring is explicit that this is best-effort. That is defensible — but it
means CHZ-SURF-02 is a **best-effort** improvement, not a deterministic guarantee, and the acceptance
criteria below are written against the deterministic path accordingly.

**Acceptance criteria (immutable)**

**Acceptance criteria (immutable)**
- Every tool name in every installed artifact resolves against the **live registered MCP surface**
  enumerated from `server.py` — not against `tool_surface.py` (two components agreeing on the same
  wrong assumption is how this shipped)
- **Mutation gate:** injecting `llm_bogus_xyz` into any emittable surface fails the lint AND ≥1 test
  (currently: all green — proven blind spot)
- `GUARDED` derived programmatically from `DEPRECATED_TOOLS`, not hand-maintained
- Lint scans `.md`, `.json`, `.yaml`, `.sh`

**Immutable test assets:** `tests/routing/test_rules_tool_resolution.py`

---

## WP-09 — Verification integrity 🔴
**Wave 3 · deps: WP-01, WP-08 · findings: RED3-01 (P0), RED3-02 (P0), RED3-03 (P0), RED3-08**

⚠ **RED3-08 and RED3-02 MUST ship together.** Fixing the `cwd` wiring is precisely what converts
`diff_check` from *useless* to *gameable*. Shipping the wiring alone makes the product worse.

**Scope** — ✅ **DECIDED: Route A (owner decision, locked).** Route B is retained below only to record
what was rejected; do not implement it.

**Route A — make verification real** ✅ **SELECTED**
1. Wire the reversibility gate: irreversible milestones run in an isolated git worktree, merged only after verification.
2. Replace substring/membership matching with semantic checks; reject stubs (`return True`, `pass`, `NotImplementedError`).
3. **Pre-register and hash the acceptance check before execution; re-verify the hash after.** The executor cannot edit the oracle it is graded against.
4. Wire `cwd` to `CodexAdapter`.

**Route B — scope the claim down**: state plainly that "verified" means "a syntactic check passed",
and remove the isolated-worktree claim from README.

Both are legitimate. **Shipping the current wording with the current behaviour is not.**

**Acceptance criteria (immutable — Route A)**
- A `return True` stub for a security-hole task is **REJECTED** (baseline: accepted)
- An executor that rewrites its own test → run FAILS on hash mismatch (baseline: passed)
- Irreversible milestone executes in a worktree; unverified work never reaches the main tree
- `diff_check` returns non-empty diffs under default config (baseline: always empty)
- Adjudicator reproducers `myadj_red302*.py`, `myadj_red303*.py` now fail to game

**Immutable test assets:** `tests/agentic/test_verification_soundness.py`

---

## WP-10 — Escalation integrity
**Wave 4 · deps: WP-09 · findings: RED3-04, RED3-05, RED3-06, RED3-07**

**Scope** — real `cost_per_call_usd` for adapters (or an explicit attempt-count cap for genuinely
free tiers, documented); add `replan_fn` to `run_delegation()` or delete the dead path; cap
planner-generated milestones; make `pack_prompt()` forward `artifacts`.

**Acceptance criteria (immutable)**
- A non-converging execution halts at a **hard bound**; worst-case attempts and spend are computable and asserted
- `budget_usd` demonstrably stops a runaway under default adapters, **or** the parameter is removed and documented as inert
- Milestone 3 depending semantically on milestone 1's artifact **succeeds** (baseline: artifacts dropped)
- Replan either functions end-to-end or is deleted — no dead safety code

---

## WP-11 — `doctor` tells the truth
**Wave 3 · deps: WP-08 · findings: RED4-02, RED1-23**

**Scope** — `doctor` must exercise the **live** hook→hint→tool-resolution path, not a parallel one.
Wire `trace_northstar.py` into `doctor` and CI, with explicit scope labelling.

**Acceptance criteria (immutable)**
- With a real tool-surface regression injected, `doctor` **exits non-zero and names the defect**
  (baseline: byte-for-byte identical healthy output)
- `doctor` output states which paths it did **not** check
- `trace_northstar.py` referenced by CI, not only a CHANGELOG line

---

## WP-12 — Leaderboard: implement or delete
**Wave 4 · deps: none · findings: RED8-08**

✅ **DECIDED: Option B (owner decision, locked).** Option A is retained only to record what was
rejected; do not implement it.

**Option A — implement.** ❌ *rejected* — runtime fetch with cache + staleness check.
**Option B — delete the claim.** ✅ **SELECTED.** Rewrite NORTH_STAR to describe a curated static
ladder with a documented manual refresh cadence + a CI check that fails when the snapshot exceeds it.

**Consequence to state plainly in NORTH_STAR:** vendor-neutrality remains a *goal*, not a claimed
*capability*. The document's clause *"'most capable' is defined by the live external model
leaderboard"* must be rewritten — it is currently the load-bearing justification for the whole
"Claude is not axiomatically the top" position, and after Option B that position rests on a
manually-curated ladder instead. That is honest and defensible; asserting it is live is not.

**Acceptance criteria (immutable)**
- *(A)* ranking refreshes at runtime; stale data raises a visible warning; offline path documented
- *(B)* no NORTH_STAR text asserts "live"/"continuously-updated"; refresh cadence documented and a CI check fails when the snapshot exceeds it
- Either way: **`grep -c 'continuously-updated' Docs/planning/NORTH_STAR.md` must be consistent with the implementation**

---

## WP-13 — Fail-open triage
**Wave 5 · deps: WP-03, WP-04, WP-06 · findings: RED8-09**

Sequenced late deliberately: doing this first would surface a flood of errors from defects not yet fixed.

**Scope** — triage 810 bare `except Exception` / ~234 fail-open into **deliberate** (documented,
counted, surfaced) vs **defect-masking** (delete). Ban silent swallowing in cost, routing, verification
and telemetry paths.

**Acceptance criteria (immutable)**
- Zero bare `except Exception: pass` in `cost.py`, `router.py`, `execution_ledger.py`, `dashboard_data.py`, `summary.py`
- Every retained broad catch logs with a stable event code and increments a counter
- CI lint prevents new bare catches in the protected module set

---

## WP-14 — Gate hardening
**Wave 4 · deps: WP-03, WP-04, WP-08 · findings: RED-7b Q3/Q5 blind spots**

**Scope** — mutation gates for the 3 proven blind spots; `smoke-test.yml` runs the **full suite
against the built wheel** in a clean HOME seeded with a realistic pre-existing host config (this is
what would have caught RED4-01).

**Acceptance criteria (immutable)**
- All 3 historical blind-spot mutations now fail ≥1 test
- 10-mutation sample on money/routing/verification: **≥8 killed**
- `smoke-test.yml` installs the built wheel; editable-install-only path removed
- CI seeds a non-empty `settings.json` before install tests

---

## WP-15 — Delete rather than fix
**Wave 5 · deps: WP-09, WP-12 · findings: RED3-10, RED6-04, RED6-07, RED8-06, RED8-10**

**Delete:** `response_validation.py` (zero importers; claims protection it does not provide — dead
safety code reads as coverage); the `gateway`/`route_server` team-server preset (undocumented,
unauthenticated, reintroduces SEC-001); `secret_scrubber.scrub_environment()` (uncalled, narrower
allowlist than the one in use); two of three duplicate classifiers.
**Add:** central env-var registry for the 186 variables.

**Acceptance criteria (immutable)**
- Deleted modules have zero importers; suite green after deletion
- One classifier remains; one tool-map remains
- Every env var read anywhere appears in the registry (AST-verified)
- No component binds `0.0.0.0` without passing the existing `_allow_public_bind` gate

---

## WP-16 — Re-qualification at the shipping SHA
**Wave 6 · deps: ALL · findings: AUD-01, AUD-03, AUD-04, Gate 7**

**Scope**
1. **Fix Gate 7** — it certified AUD-06. Gate 7 must now assert that a loss can be *represented and displayed*.
2. Re-run the full audit at the **shipping SHA** per the restart-at-zero rule.
3. Benchmark on a **held-out corpus** — the current 33-prompt set was tuned against by fix `#220`.
4. Disclose Gate 15/16 coupling (the quality gate was partly bought by moving prompts free-local → metered `gpt-4o-mini`).
5. Restore the badge **only** if score > 95% and zero P0.

**Acceptance criteria (immutable)**
- Two consecutive clean passes at one frozen SHA, zero new P0/P1, no "not reached" sections
- Held-out corpus quality delta reported separately from the tuned corpus
- Score computed by the Part 1 rubric; every input independently reconstructable
- Badge text names the exact qualified SHA

---

# PART 4 — RISKS AND CONFLICTS

## 4.1 ✅ Uncommitted work — audited and folded into WP-08 (RESOLVED)

The canonical checkout has **531 uncommitted insertions**. Audited read-only; disposition:

| Uncommitted work | Disposition |
|---|---|
| `tool_surface.py (+106)`, `server.py (+51)`, `direct_executor.py (+43)` — **CHZ-SURF-02** | **KEEP — land as WP-08's foundation.** Sound, correctly targets the root cause. |
| `tests/test_tool_surface.py (+85)` | **KEEP** — retain, extend with WP-08's criteria |
| `okf.py (+240)`, `commands/okf.py`, `cli.py (+5)`, `tests/test_okf*.py` | **UNRELATED to the audit.** Land or shelve independently; no WP depends on it. |

**Required before WP-08 starts:** commit the CHZ-SURF-02 work (or shelve it to a branch WP-08 rebases
onto) so the graph's `implement` subgraph starts from a clean, known base. **Do not discard it** —
WP-08's scope now assumes it is present, and re-deriving it inside the graph would waste a run and
likely produce a weaker version.

**Ordering note:** the CHZ-SURF-02 rules-refresh re-sequencing in `server.py` and WP-08's change to
`_append_routing_rules` touch the same install path. Land CHZ-SURF-02 **first**, as a separate
commit, then run WP-08 on top — not simultaneously.

## 4.2 Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| **Graph planner overrides pre-registered criteria** | Reproduces I-3; remediation unverifiable | Hash-check criteria (Part 0, rule 2); treat `plan.acceptance_criteria` as advisory |
| **WP-08 ships without WP-09** | `diff_check` becomes actively false rather than merely dead | Same-wave gating; WP-09 blocked until both land together |
| **`audit_rounds < 2` insufficient** | Large WPs never converge | WPs sized for ≤2 rounds; split on second failure rather than raising the bound |
| **Test isolation causes another data-loss incident** | Real user data destroyed | Every DB test asserts tmpdir resolution; fix `CHUZOM_HOME` isolation in WP-06 |
| **Fixing fail-open (WP-13) floods errors** | Perceived regression | Sequenced to Wave 5, after core defects fixed |
| **Score gamed by closing cheap findings** | False "95%" | Hard gates G-A…G-F override the score |
| **Held-out corpus unavailable** | Benchmark still tuned | WP-16 blocked until a corpus is sourced; do not substitute the tuned set |

## 4.3 What this plan does NOT cover

Stated explicitly so it is not mistaken for coverage:

- **Windows / Linux execution** — the entire audit ran on macOS/arm64. Every cross-platform claim is `NOT TESTED`.
- **Live host clients** — no track drove a real Cursor/Windsurf/Copilot/Gemini CLI instance. RED1-20 is
  proven at source-generation level, not at live round-trip.
- **Adversarial classification-boundary testing** — RED-1 did not execute this mandate area at all.
- **`router.py`'s own fallback-chain bound** — ~2,600 lines never fully read; its contribution to
  worst-case spend is an open gap.

These should become WP-17+ after the P0s close.

---

# PART 5 — GRAPH INVOCATION

One run per WP, in wave order. Waves may run in parallel internally; **never** across a dependency edge.

```
goal: |
  <WP-NN scope block, verbatim from Part 3>

  PRE-REGISTERED ACCEPTANCE CRITERIA (IMMUTABLE — sha256: <hash>):
  <criteria block, verbatim>

  BINDING RULES:
  - Do NOT author new acceptance criteria; the criteria above are the sole pass condition.
  - Do NOT modify files listed under "Immutable test assets".
  - Every regression test MUST be demonstrated RED before the fix and GREEN after.
  - All DB-touching tests MUST assert their resolved path is inside a tmpdir.
repo: /Users/yaliandrona/Projects/Chuzom
```

**Per-run exit gate** (graph's own `verification` block plus ours):
`verdict == 'approve'` ∧ `docs_updated` ∧ `signed_off` ∧ `test_failed_before_patch` ∧
`test_passes_after_patch` ∧ `mutation_score ≥ baseline + 0.15` ∧ criteria-hash unchanged.

## 5.1 Suggested sequencing

| Wave | WPs | Runs | Parallel? |
|---|---|---|---|
| 0 | WP-00 | 1 | — |
| 1 | WP-01, WP-02, WP-03 | 3 | yes |
| 2 | WP-04, WP-06, WP-08 | 3 | yes |
| 3 | WP-05, WP-07, WP-09, WP-11 | 4 | yes |
| 4 | WP-10, WP-12, WP-14 | 3 | yes |
| 5 | WP-13, WP-15 | 2 | yes |
| 6 | WP-16 | 1 | — |

**17 graph runs total.** Each carries one human approval gate (`release-approval`), so **17 human
sign-offs** — deliberate: this plan touches security, money, and user config.

---

# PART 6 — TRACEABILITY

Every audit finding maps to exactly one owning WP. No finding is unassigned.

| WP | P0 | P1 | P2/P3 | Findings |
|---|---|---|---|---|
| WP-00 | — | 1 | 3 | AUD-01, AUD-02, AUD-05, 4 claims |
| WP-01 | 2 | — | 1 | RED6-01, RED6-02, CodexAdapter |
| WP-02 | 1 | — | 1 | RED4-01, RED4-08 |
| WP-03 | 2 | 3 | 1 | RED2-01, RED8-01, RED8-03, RED8-07, RED8-04 |
| WP-04 | 1 | — | — | AUD-06 |
| WP-05 | — | 4 | — | RED2-02, RED2-03, RED2-04, RED8-05 |
| WP-06 | 2 | 4 | 1 | RED5-01/02/03/04/05/06, RED2-07 |
| WP-07 | — | 1 | 2 | I-1, RED1-24, RED2-06 |
| WP-08 | 1 | 2 | 1 | RED1-20, RED1-21, RED1-22, RED1-23 |
| WP-09 | 3 | 1 | — | RED3-01, RED3-02, RED3-03, RED3-08 |
| WP-10 | — | 4 | — | RED3-04/05/06/07 |
| WP-11 | — | 1 | — | RED4-02 |
| WP-12 | — | 1 | — | RED8-08 |
| WP-13 | — | — | 1 | RED8-09 |
| WP-14 | — | 1 | 1 | RED-7b Q3/Q5, RED4-03 |
| WP-15 | — | 1 | 4 | RED3-10, RED6-04, RED6-07, RED8-06, RED8-10 |
| WP-16 | — | 1 | 2 | AUD-01, AUD-03, AUD-04, Gate 7 |
| **Σ** | **12** | **25** | **18** | **all findings assigned** |

*(P1 count exceeds 17 because several P1s decompose across WPs; the closure denominator remains the
17 distinct P1 IDs in `14_FINDINGS.md`.)*
