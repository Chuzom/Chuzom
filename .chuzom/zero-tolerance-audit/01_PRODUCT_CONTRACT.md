# 01 — PRODUCT CONTRACT

Target: `c2c2882` / `v1.1.1`. Sources: `README.md` (421 lines), `Docs/planning/NORTH_STAR.md`,
`Docs/correctness-reset/*`, `pyproject.toml`.

**These are the promises Chuzom makes to a user. They are hypotheses to be proven, not conclusions.**
Status column is filled by executable evidence only. `NOT YET PROVEN` is the default state.

---

## A. Contract table

| # | Promise (as stated to users) | User expectation | Code responsible | Status |
|---|---|---|---|---|
| 1 | "routes each prompt to the cheapest capable model" | Cheapest *capable* — not merely cheapest | `router.py`, `classifier.py`, `chain_builder.py`, `profiles.py` | NOT YET PROVEN (RED-1/8) |
| 2 | "Quality preserved — premium only when needed, **measured, not assumed**" | Quality is empirically protected | `judge*.py`, `scorer.py`, `gates.py` | CONTESTED — see §B.2 |
| 3 | "a hook sees **every prompt**" / "every request, no bypass" | Universal interception | `hooks/auto-route.py`, `hooks/enforce-route.py` | NOT YET PROVEN (RED-1) |
| 4 | "spends Claude quota only on work that truly needs it" | Quota preservation | `quota_*.py`, `claude_usage.py` | NOT YET PROVEN |
| 5 | "Context-dependent prompts … fall back to Claude **by design**" | Fallback is intentional, not failure | `context_signal.py`, `router.py` | NOT YET PROVEN |
| 6 | "falls back automatically when needed" | Provider failover works | `providers.py`, `health.py` | NOT YET PROVEN |
| 7 | "any model … the same execution surface" (tool-capable) | Routed models can do real work | `agentic/`, `llm_act` | NOT YET PROVEN (RED-3) |
| 8 | "bash / read / write / git scoped to the working directory" | Scoped, bounded file ops | `agentic/`, `safe_subprocess.py`, `edit.py` | NOT YET PROVEN (RED-6) |
| 9 | "delegate a whole task … and verify the result" | Agentic delegation works | `orchestrator.py`, `agentic/` | NOT YET PROVEN (RED-3) |
| 10 | "'Done' means the check passed, **not a self-report**" | Objective verification | `gates.py`, `contract.py` | **PRIMARY ATTACK TARGET** (RED-3) |
| 11 | "escalates to a stronger tier, carrying already-passed milestones forward" | Escalation without rework | `orchestrator.py` | NOT YET PROVEN |
| 12 | "escalation is bounded" | Hard spend/attempt bound exists | `orchestrator.py`, `budget*.py` | NOT YET PROVEN (RED-3 §6) |
| 13 | "**Net cash savings +$0.027/run**" | Reproducible measured savings | `benchmark/`, `cost.py` | CONTESTED — see §B.1 |
| 14 | "baseline counterfactual from recorded tokens, **not a latency guess**" | Tokens measured, not estimated | `cost.py`, `summary.py` | NOT YET PROVEN (RED-2) |
| 15 | Dashboard `Saved` column arithmetic | Numbers reconstructable | `ui/session_summary.py`, `dashboard/` | NOT YET PROVEN (RED-2) |
| 16 | "On a Claude Pro/Max subscription the value is **quota runway, not cash**" | Quota ≠ cash, kept distinct | `quota_savings.py` | Honest framing — verify code matches |
| 17 | "Session Summary Dashboard" truthfulness | Panels reflect reality | `ui/`, `dashboard/` | NOT YET PROVEN |
| 18 | "**Local-first, no Chuzom telemetry**" / "phones home to no Chuzom servers" | No outbound to vendor | `telemetry.py`, `observability.py` | NOT YET PROVEN (RED-6) |
| 19 | FAQ: "What data does Chuzom collect? **None. Everything stays on your machine**" | Total local containment | — | **INTERNALLY CONTRADICTED** — see §B.3 |
| 20 | "With only a local provider (Ollama) configured, prompt text stays on your machine" | Local-only mode is truly local | `classifier.py`, `semantic_classify.py` | NOT YET PROVEN (RED-6) |
| 21 | "keys … stored in `~/.chuzom/.env`, never committed" | Secrets at rest are safe | `secrets_vault.py`, `config.py` | NOT YET PROVEN (RED-6) |
| 22 | `pip install chuzom-router && chuzom install` works | Clean install succeeds | `commands/install.py` | NOT YET PROVEN (RED-4) |
| 23 | 7 hosts supported, 4 "Production" / 3 "Beta" | Each listed host works | `hosts/`, `integrations/` | NOT YET PROVEN (RED-1/4) |
| 24 | "Drop-in, **zero workflow change**" | Non-invasive | `install_hooks.py` | NOT YET PROVEN (RED-4) |
| 25 | Uninstall / disable (`CHUZOM_ENFORCE=off`) | Clean, reversible removal | `commands/`, `enforce_config.py` | NOT YET PROVEN (RED-4) |
| 26 | "Python 3.11–3.14" | All four versions work | CI matrix | NOT YET PROVEN (RED-7) |
| 27 | "Can I use it on Windows? **Yes**" | Windows supported | cross-platform paths | **NOT TESTABLE HERE** (RED-4) |
| 28 | "18 providers … plus 13 auto-detected local servers" | Provider breadth real | `providers.py`, `local_platforms.py` | NOT YET PROVEN |
| 29 | Six routing policies tune cost/quality | Policies have real effect | `policies/`, `policy.py` | NOT YET PROVEN |
| 30 | **Leaderboard-driven capability ordering** (NORTH_STAR) | Live external ranking drives ladder | `benchmark_fetcher.py`, `model_registry.py` | **PRIMARY ATTACK TARGET** (RED-8) |
| 31 | "Auto-downgrade near limits, so no hard rate-limit wall" | Budget enforcement | `budget_envelope.py`, `quota_envelope_routing.py` | NOT YET PROVEN |
| 32 | Enforcement ladder `smart/soft/hard/strict/advise/off` | Each mode behaves as documented | `enforce_config.py`, `hooks/enforce-route.py` | NOT YET PROVEN (RED-1) |
| 33 | Failure visibility — user can see what happened | No silent failure | `ui/`, `routing_quality.py` | NOT YET PROVEN |
| 34 | "Reproduce them yourself with `python -m chuzom benchmark`" | Benchmarks reproducible | `benchmark/` | CONTESTED — see §B.1 |
| 35 | Badge: **"audit — RELEASE QUALIFIED"** on `main` | Current code is qualified | `Docs/correctness-reset/` | **DISPROVEN** — see §B.4 |
| 36 | "**independently audited**" | Third-party audit | `11_AUDIT_RUNBOOK.md` | **MISLEADING** — see §B.5 |

---

## B. Contract-level contradictions found at this SHA

### B.1 — The measured savings baseline does not match the advertised use case

The headline is **quota preservation on a Claude Pro/Max subscription** (README opening, The
Problem, the whole pitch). But the one **measured** number is:

> Chuzom ≈ $0.0036 vs **always-GPT-4o** ≈ $0.030 → +$0.027/run net cash

The counterfactual is **always-GPT-4o pay-per-token**, which is *not* the workload the product
is sold for. README does disclose this ("the money column applies only if you'd otherwise pay
per-token at GPT-4o rates") — that disclosure is honest and materially mitigates the issue.

Residual problems:
- The **only** measured, audited figure benchmarks a use case most target users do not have.
- Sample: 33 prompts (moderate+hard), 4 runs. A **−0.21** quality delta on a 0–5 scale from
  n=33 is very unlikely to be statistically distinguishable from a larger regression.
- ~~The 0.5 margin may have been chosen post hoc.~~ **SUSPICION WITHDRAWN — DISPROVEN in the
  project's favour.** The margin was pre-registered and *actually rejected a release*: Gate 16
  first measured **−0.58**, failed the 0.5 margin, and the verdict was recorded as **NOT
  QUALIFIED** (`3923098`). `03_RELEASE_GATES.md:102`: *"the audit did its job and halted rather
  than certify a non-robust pass."* This is genuine methodological rigor and is credited as such.
  Evidence: `evidence/benchmark_methodology.md` §A.
- **New issue raised in its place — the *fix* was tuned on the evaluation corpus.** The −0.58
  failure was root-caused to two specific prompts (`mod-07`/`mod-12`); fix `#220` was built to
  remove exactly those misses, then re-measured on the same 33-prompt corpus, whereupon
  *"variance collapsed"*. The four "independent runs" are repeated measurements of a corpus the
  fix was designed against, not independent samples. No held-out corpus. → `evidence/…` §B.
- **The quality gate was partly bought with money.** Fix `#220` moves exact-answer prompts from
  **free local** to **metered `gpt-4o-mini`**. Gate 16 (quality) and Gate 15 (savings) are
  therefore coupled, but are reported as independently passing. → §C.
- Run 4 delta of exactly **+0.00** across a judged corpus warrants inspection.
- README states quality is "measured, not assumed", but a judge-scored delta is only as
  independent as the judge. If the judge shares a model family with a routed candidate, this
  is partly self-grading. → RED-3.

**Status: CONTESTED — the disclosure is fair; the evidential strength is not yet established.**

### B.2 — "Quality preserved" is a stronger claim than the evidence supports

Feature table asserts *"Premium models only when the task needs it — measured, not assumed."*
The supporting measurement is a **−0.21 quality delta**, i.e. measured quality **decreased**.
"Preserved" and "non-inferior within a chosen margin" are different claims. → RED-2/RED-3.

### B.3 — README contradicts itself on data egress

Two statements, both in `README.md`:

1. *"if you configure cloud providers … the classifier and the routing chain **send prompt text
   to those providers' APIs**"* — accurate and commendably explicit.
2. FAQ: *"What data does Chuzom collect? **None. Everything stays on your machine** — no
   telemetry, no cloud calls to Chuzom."*

Statement 2 is defensible only under the narrow reading "no data reaches *Chuzom-operated*
servers". The sentence "Everything stays on your machine" is **false** whenever a cloud provider
is configured — which the Get Started section actively instructs users to do. A privacy-sensitive
user reading only the FAQ is misinformed. → **Claim defect; RED-6 verifies actual egress.**

### B.4 — The `RELEASE QUALIFIED` badge does not apply to this release — *by the project's own rule*

`PROVEN`. Evidence: `evidence/qualification_drift.txt`.

| Fact | Value |
|---|---|
| Qualified (frozen) SHA | `7c6fdaa` — 2026-07-28 |
| Audited SHA | `c2c2882` (`v1.1.1`) |
| Commits since qualification | **125** |
| Total drift | **488 files, +217,260 / −6,188** |
| Core routing/cost/telemetry drift | **2,824 insertions / 612 deletions across 20 files** |

Core churn since the qualified commit:

| File | Change | Note |
|---|---|---|
| `router.py` | **+1,094** | ~22% of a 4,967-line orchestrator |
| `tool_surface.py` | **+480** | effectively **new** post-qualification |
| `hooks/auto-route.py` | **+441** | primary interception path |
| `hooks/enforce-route.py` | **+306** | enforcement gating |
| `hooks/session-start.py` | +235 | |
| `cost.py` | **+99** | the savings engine |

Decisively, `11_AUDIT_RUNBOOK.md` states the project's **own** binding rule:

> *"If any step finds a new P0/P1 or cannot be completed, the pass **fails**: fix the finding,
> **re-freeze at a new commit, and restart the count at zero** (a partial pass never carries over)."*

Qualification is explicitly **pinned to a frozen commit**. `v1.1.1` is 125 commits past it, with
the interception, enforcement, tool-surface and cost paths all substantially rewritten — including
a **tool-surface correctness fix in HEAD's own commit** (`CHZ-SURF-01`), proving routing defects
were still being discovered after qualification.

This is not an external standard being imposed. **The repository is failing its own documented
release contract while displaying the badge that contract issues.**

### B.5 — "independently audited" is likely to mislead

`README.md` says **"independently audited"** beside a `RELEASE_QUALIFIED` badge. The runbook says
the audit is *"performed by the reviewer using ordinary tools + the mechanical check script"*.

In fairness, the runbook's own sense of "independent" is clearly **independent of Chuzom's own
routing** — *"Chuzom must not audit itself … never via Chuzom's own `llm_*` routing"* — which is
a genuinely sound principle, and the same one this audit adopted independently.

But in product copy beside a certification badge, "independently audited" conventionally denotes
a **third party**. No third-party auditor is identified anywhere. The claim should be scoped
(e.g. "audited under a documented runbook, not self-routed") or substantiated. → **P2 claim defect.**

---

## C. Structural observation: two different products are described

`README.md` sells **Claude-quota preservation** (Claude is the expensive thing to avoid).
`NORTH_STAR.md` mandates **vendor-neutral, leaderboard-driven** capability ordering, and states:

> *"Pinning 'Claude = top' is a North-Star violation the moment another model leads."*

Meanwhile README's own "Routing at a Glance" table hardcodes a vendor ladder
(Haiku → Sonnet → Claude Opus → Gemini 2.5 Pro …). Whether the live leaderboard actually drives
routing **by default**, or is optional/disabled/stale-cached, determines whether the North Star is
**implemented or aspirational**. Presenting aspirational behaviour as current is an explicit
North-Star anti-goal ("claims a guarantee that isn't measured"). → RED-8, primary target.

---

## D. What must be proven for `RELEASE QUALIFIED` at this SHA

1. Promise 3 (no bypass) — proven, with telemetry that can *detect* bypass.
2. Promise 10 (objective verification) — survives adversarial attack on the checks themselves.
3. Promises 13/14/15 — every user-facing number independently reconstructable.
4. Promises 18/19/20 — actual egress matches stated privacy behaviour.
5. Promise 30 — leaderboard genuinely drives the ladder by default, or copy is corrected.
6. Promise 35 — re-qualification performed **at `c2c2882`**, per the project's own restart rule.
