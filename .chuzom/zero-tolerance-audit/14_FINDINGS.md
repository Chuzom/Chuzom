# 14 — CONSOLIDATED FINDINGS REGISTER

Target: **`c2c2882` / `v1.1.1`**. Every finding below has passed **adversarial adjudication** (§27):
a second agent was tasked with *disproving* it and failed, or succeeded in modifying its severity.

Detailed per-finding entries live in the track reports; adjudication reasoning in `15_ADJUDICATION.md`.

## Adjudication integrity

Adjudication demonstrably cut **both** ways — this is why the surviving findings are credible:

| Movement | Finding | Reason |
|---|---|---|
| P0 → P1 | RED3-04 (budget cosmetic) | No specific violated product claim found to support P0 framing |
| P0 → P2 | RED3-09 (no sync quality check) | README **explicitly scopes** verification to `llm_act`; no claim violated |
| P1 → P2 | RED6-04 (gateway unauth) | Requires a deliberately-chosen, undocumented non-default preset |
| P1 → P2 | RED2-05 (mis-named function) | Naming only; zero dollar impact |
| merged | RED8-02 → RED2-01 | Same defect found independently by two tracks |
| **withdrawn** | AUD (post-hoc margin) | **Disproven in the project's favour** — margin was pre-registered |
| corrected | RED5-02 "9 call sites" | Independent grep found 7 |
| corrected | RED-2 "permanently unrecoverable" | Overstated — data is re-derivable from Claude transcripts |
| **upgraded** | RED5-02 | Static proof → **live multi-process reproduction** |

---

# P0 — PRODUCT INVALIDATING (12)

| ID | Title | Confidence |
|---|---|---|
| **RED6-01** | Prompt-injection defense exists but is **never called** on the agentic delegation path | PROVEN (live) |
| **RED6-02** | Delegated `bash` tool inherits **full parent environment** (all API keys); `env`/`printenv`/`set` unblocked across 11 tested bypass variants | PROVEN (live) |
| **AUD-06** | "TOTAL saved" is a **sum of wins, not a net** — losses clamped to zero before aggregation | PROVEN |
| **RED2-01** | Stale `$15/$75` Opus pricing on the ledger **write** path (≈3× overstatement) | PROVEN |
| **RED8-01** | Stale Opus pricing on the dashboard **read** path → ~26–28 reporting surfaces | PROVEN |
| **RED5-02** | `execution_ledger.record_event()` silently drops accounting events; `False` discarded at **all 7** call sites | PROVEN (live: 66/2400, peak 29.4%) |
| **RED5-01** | `LineageStore` cold-start WAL race crashes concurrent writers, losing entire write batches | PROVEN (live: 4/12, exact 800/2400 row loss) |
| **RED3-01** | Reversibility gate **never wired** — irreversible milestones run with zero worktree isolation, contradicting README | PROVEN |
| **RED3-02** | `diff_check` accepts a fabricated `return True` stub as verified DONE | PROVEN |
| **RED3-03** | `cmd_check` test-tampering — executor rewrites the oracle it is graded against, exits 0 | PROVEN |
| **RED1-20** | All **13** host rules files installed verbatim with no resolver pass; every one teaches ≥1 unregistered tool name | PROVEN |
| **RED4-01** | `install` silently destroys a pre-existing `statusLine`; `uninstall` deletes rather than restores | PROVEN |

## The two P0 chains (compound, not independent)

**Chain A — Security.** RED6-01 → RED6-02. Demonstrated live end-to-end in unmodified production
code: hostile `session_context` → `TaskLedger`/`pack_prompt` → a real local model (`hermes3:8b`)
autonomously invoked `bash` with `env` → unsandboxed executor returned the full environment → the
model surfaced the planted secret. **Zero human involvement after the hostile context was set.**
Tier-1 `CodexAdapter` shares both gaps **and bypasses the codebase's own safe `codex_agent.run_codex()`**.
Precondition: a working Ollama/Codex backend — the default tier and the marketed core function.
`CHUZOM_DELEGATE` **defaults ON** (independently confirmed by a second track).

**Chain B — Economics.** RED8-01 × AUD-06 in the *same file* (`dashboard_data.py`): an inflated
baseline enlarges every row's apparent saving, while the clamp deletes every row that would pull the
total down. Errors that would partially cancel in an honest net instead **reinforce**.

---

# P1 — RELEASE BLOCKER (17)

| ID | Title |
|---|---|
| RED1-22 | `scripts/lint_tool_surface.py` — the CI gate for this exact bug class — reports **clean on a proven-broken tree** (never scans `.md`; trusts anything passed to `localize()`) |
| RED1-21 | `llm_reason` absent from `DEPRECATED_TOOLS`/`KNOWN_TOOLS`/`EMITTABLE_TOOLS` simultaneously → survives `localize()` untouched |
| RED4-02 | `doctor` cannot detect a live routing regression — **byte-for-byte identical output** with a real fault injected |
| RED8-07 | `INV-COST-004` named but never made enforceable — root cause of the entire pricing cluster |
| RED8-08 | North Star's "continuously-updated, **live**" leaderboard is a static offline snapshot, `generated_at: 2026-03-30` (**4.4 months stale**), no runtime fetch, no staleness check |
| RED8-05 | Two unreconciled savings figures per accepted event (task-varying ledger baseline vs always-Opus receipt baseline), rendered **on the same screen** in `session-end.py` |
| RED8-03 | OpenAI o3 pricing stale in 2 of 3 sibling tables, contradicting a comment claiming it was fixed |
| RED2-03 | User-facing "saved X pp/week" rests on a hardcoded `$50/week` constant justified by the disproven `$15/$75` rate |
| RED2-04 | 5 differently-gated "savings" fields; the one labeled "Realized" isn't subscription-gated like its honest sibling |
| RED2-02 | `get_savings_summary()` — query failure and genuine zero return an **identical dict** |
| RED3-04 | `budget_usd` provides zero protection under both shipped default adapters (`cost_per_call_usd=0.0`) |
| RED3-05 | Replan is dead code — `run_delegation()` has no `replan_fn` parameter |
| RED3-06 | No cap on planner-generated milestone count |
| RED3-07 | `pack_prompt()` drops `artifacts` — cross-milestone semantic dependencies silently don't survive |
| RED3-08 | `diff_check` structurally unusable by default (`cwd` never wired to Codex adapter) |
| RED5-03 | `exclusive_lock()`'s documented "degrade on timeout" escape hatch is **structurally unreachable** — both call sites discard the yielded boolean |
| RED5-05 / RED5-04 / RED5-06 / RED5-07 | Hash chain forks under legitimate concurrency (false tamper alerts); `budgets.json` unlocked read-modify-write; `idempotency.py` single-process by own admission; `state.py` globals bleed across tenants in `main_sse_secured()` |
| RED6-03 | `error_sanitization.py` misses `sk-`/`sk-ant-`/`ghp_`/Bearer formats that `secret_scrubber` catches — wired into `admin_api.py`'s public exception handler |
| **AUD-01** | `RELEASE QUALIFIED` badge does not apply to `v1.1.1` **by the project's own restart-at-zero rule** |

---

# P2 / P3 — selected

| ID | Sev | Title |
|---|---|---|
| **AUD-02** | P2 | README self-contradicts on egress: *"Everything stays on your machine"* vs documented cloud egress |
| **AUD-03** | P2 | Benchmark fix `#220` tuned on the 33-prompt evaluation corpus; "4 independent runs" are repeated measures, not independent samples; no held-out set |
| **AUD-04** | P2 | Quality gate partly bought by moving prompts free-local → metered `gpt-4o-mini`; Gates 15/16 coupled but reported as independent |
| **AUD-05** | P2 | "independently audited" implies a third party; runbook says "the reviewer" |
| RED8-09 | P2 | **810** bare `except Exception:`, ~234+ fail-open, no policy distinguishing deliberate from defect-masking |
| RED8-06 | P2 | Three independent classifiers/tool-maps with two different fallback tools |
| RED8-04 | P2 | Haiku priced 4 different ways (3.2× spread) |
| RED6-04 | P2 | `gateway`/`route_server` unauthenticated, `0.0.0.0`-capable (downgraded: non-default) |
| RED1-24 | P2 | ≥6 `sys.exit(0)` bypass paths logged only to an unaggregated debug file, invisible to the dashboard |
| RED8-10 | P3 | 186 env vars, no central schema/registry |

---

# The three invariants, settled

| Invariant | Verdict | Decisive evidence |
|---|---|---|
| **I-1** — can distinguish *observed success* from *unobserved outcome* | **FALSE** | Chuzom's own `enforce-route.py` docstring: *"a run where **97.7% of directives were bypassed** looked identical in telemetry to a perfect one."* The fix for that routes through `record_event()`, now proven to drop rows silently. |
| **I-2** — unknown/adverse never becomes favourable | **FALSE** | AUD-06 clamp; RED2-02 (failure ≡ zero); 5 stale pricing copies |
| **I-3** — verification not authored by the verified party | **FALSE** | RED3-02/03 — planner authors the check, executor games it, both reproduced |
| **I-6** — repo content cannot influence verification | **FALSE** | RED6-01/02 chain, demonstrated live |
| **I-7** — install non-destructive and reversible | **FALSE** | RED4-01 |
| **I-8** — every user-facing number reconstructable | **FALSE** | AUD-06 + pricing cluster |

**Prediction scored.** `02_FAILURE_MODEL.md` registered *before results arrived* that the
highest-yield findings would cluster on **I-1, I-2, I-3** rather than ordinary code bugs. All three
are now disproven, by independent tracks that never saw the prediction. The failure model was
predictive, not retrospective — which matters, because it means these are **structural**
consequences of a system that grades its own homework, not a coincidental pile of bugs.

## The single root pattern

Across six tracks the same architecture recurs: **the right control exists somewhere in the codebase
and works where it is wired — it simply isn't wired to every path that needs it, and no integration
test covers the gap.**

- Injection detector exists → not called on the agentic path (RED6-01)
- Env-scrubbing subprocess wrapper exists → not used by the delegated bash tool (RED6-02)
- Public-bind refusal gate exists → not applied to gateway/route_server (RED6-04)
- Corrected pricing table exists → stale copy read instead (RED2-01, RED8-01)
- Backup-before-overwrite exists → not applied to `statusLine` (RED4-01)
- Tool-name resolver exists → not applied to the 13 rules files (RED1-20)
- Lock-failure escape hatch exists → return value discarded (RED5-03)
- Ledger failure signal exists → `False` discarded at all 7 call sites (RED5-02)

This is **not** a "nobody thought about it" codebase. It is a codebase where good controls are
written once and then not systematically propagated — and where 810 bare `except Exception` blocks
ensure the gaps stay invisible. The team has already proven it can fix this class *systemically*
(the `tool_surface.py` / CHZ-SURF-01 resolver + CI lint). That playbook simply has not been applied
to money, secrets, or telemetry.
