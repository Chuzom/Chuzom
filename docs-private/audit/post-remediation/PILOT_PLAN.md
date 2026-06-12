# Developer Pilot Plan

**Objective.** Determine whether chuzom, deployed to a controlled set of developers, materially reduces model spend without harming developer productivity. The pilot must produce evidence sufficient to take a go/no-go decision on a broader rollout.

**Status.** Pilot can run now. Broad rollout cannot. Mandatory rollout cannot.

---

## Participants

- **Developer count.** 20 developers, opted-in voluntarily.
- **Team count.** 2 teams (one backend, one frontend or data — pick teams whose workloads vary).
- **Inclusion criteria.** Daily AI-coding tool user; willing to surface their session data for the pilot; not in a regulated workload (no customer PII, no production secret handling).
- **Exclusion criteria.** Developers handling regulated data (GDPR / HIPAA / SOX scope); developers without a dev workstation under standard image (no contractor laptops); developers on a release-week / freeze period.

## Tools in scope

Each participant uses the same set during the pilot. Suggested combination:

- Claude Code (CLI) — primary
- Cursor (IDE) — primary
- One CLI tool of the developer's choice (Codex CLI or Gemini CLI)
- Optional internal coding agent (only if it has no production side effects)

## Workloads in scope

- Code generation
- Code explanation
- Test generation
- Refactoring
- SQL generation
- Documentation
- Local repo exploration

**Out of scope for the pilot.**

- Multi-file production code changes that touch live customer surfaces.
- Anything that calls `llm_fs_edit_many` unless `project_root` is pre-pinned by a wrapper.
- Anything that invokes `agoragentic_*` tools (must remain opt-out).
- Any workload requiring data classification beyond "internal — non-customer".

## Models / providers

- **Direct-provider baseline period:** developers use their tool's default chain (Claude Code → Anthropic; Cursor → vendor mix; Codex CLI → OpenAI; Gemini CLI → Google). Per-tool, per-developer.
- **Chuzom routed period:** chuzom routes between Gemini Flash, Claude Haiku/Sonnet, OpenAI mini-tier, and optionally Ollama-local, depending on configured profile.

## Duration

- **Week −2 to 0.** Setup + pre-flight (instrumentation, baseline-corpus calibration, consent, key inventory).
- **Week 1–2.** Baseline period. Direct-provider operation. Telemetry capture only — chuzom passive (uninstalled or in dry-run if a dry-run mode exists; otherwise uninstalled).
- **Week 3–6.** Routed period. Chuzom installed and routing. Same telemetry.

Total: 8 weeks including setup.

---

## Baseline corpus

A fixed task corpus is used at the start of each week to score quality independently of organic work patterns.

- **Size:** 50 fixed tasks per developer.
- **Composition:** 15 code-explanation, 15 small-code-generation, 10 test-generation, 10 refactor.
- **Scoring:** blind, double-graded by two peers from a different team using a 5-point rubric (correctness, completeness, style fit, did-not-need-iteration, would-have-merged).
- **Source of truth:** corpus prompts + reference outputs live in a private repo accessible only to the pilot team.

## Success metrics

| Metric | Target |
|---|---|
| Gross model cost per dev-week | ≥ 25% reduction routed vs. baseline |
| Net cost per dev-week (after estimated rework / re-prompts) | ≥ 15% reduction |
| Time-to-first-token p50 | ≤ +20% vs. baseline |
| Time-to-first-token p95 | ≤ +50% vs. baseline |
| Corpus-completion rate | within −2 percentage points vs. baseline |
| Developer NPS (weekly 1-q survey, 0–10) | not worse by more than 1 point vs. baseline week |
| Bypass rate (developers reverting to direct provider) | < 20% by week 4; < 10% by week 6 |
| Audit-row attribution (rows / total turns) | ≥ 99.5% |
| `verify_chain()` per developer at end of pilot | passes |

## Failure metrics (early-exit triggers)

| Trigger | Action |
|---|---|
| Corpus-completion drop > 5 pp at week 4 | Stop pilot. Diagnose model selection. |
| TTFT p95 regression > 30% sustained for one week | Stop. Tune chain or exit. |
| Any unauthorised-data event (provider chosen routes regulated data to a non-approved region) | Stop immediately. Incident review. |
| Any audit-row gap > 0.5% | Stop. Root-cause AuditLog reliability. |
| > 30% pilot opt-out at week 4 | Stop. Pilot fails. |
| `_KNOWN_BROKEN_TESTS` count grows during pilot | Investigate; do not block, but track. |

## Security / privacy controls during pilot

- Pilot participants' provider keys remain in their workstation env. No shared keys. (Pre-condition for the broader G-005 SSO work, but acceptable for a 20-dev pilot.)
- `CHUZOM_AGORAGENTIC` and `CHUZOM_FS_TOOLS` left **unset** for every participant. Verified by `chuzom doctor` script at pilot start.
- Audit data exported daily from each participant's `~/.chuzom/audit.db` to a central analyst-only S3 bucket; participants must consent in writing. **Per-participant key for the bucket.**
- No prompt content extracted from audit rows for any non-corpus task. Only metadata (model, provider, cost, latency, complexity, classifier_method).

## Cost controls during pilot

- Hard per-developer monthly cap of $200 in `chuzom_monthly_budget`. This is enforced **per-process per-machine** today (INV-011 limitation) — the pilot accepts this risk on 20 developers and validates the boundary; it does not extend it.
- Daily fleet-wide dashboard for the pilot operator. Trigger alert if total daily routed cost > $400.
- Direct-period and routed-period costs both captured (corpus + organic).

## Opt-out process

- Any participant can disable chuzom at any time via `chuzom uninstall` (must restore the pre-pilot tool chain).
- Opt-outs do not require justification; they are tracked as a metric.

## Rollback plan

- All chuzom configuration is local. Removing it is `pip uninstall chuzom-router` + revert tool wrappers (kept as backup at install time).
- Telemetry pipeline is read-only on developer side; nothing to roll back.
- Rollback for the whole pilot completes in < 60 minutes across 20 developers.

## Support process during pilot

- One pilot engineer on call during pilot working hours.
- 24h Slack channel with the pilot engineer + chuzom maintainer.
- Daily standup for pilot operator + the two team leads for the first two weeks.

## Data collection

- Per-call rows from `~/.chuzom/usage.db` and `~/.chuzom/audit.db` (metadata only).
- Per-dev weekly NPS.
- Corpus-completion scores.
- Bypass events (developer-self-reported + telemetry inference).
- All incidents logged in a shared incident doc.

## Exit criteria → expansion or termination

**Expansion-ready signals (all required):**

1. Gross cost reduction ≥ 25%.
2. Net cost reduction ≥ 15% (after estimated rework cost from corpus delta).
3. Corpus completion within tolerance.
4. NPS not worse by > 1 point.
5. No P0/P1 security or privacy incident.
6. Bypass rate trending down (week 4 → week 6).
7. Operator runbook drafted and tested (G-018).

**Termination signals (any one):**

- Any failure-metric trigger above.
- Pilot-operator capacity exceeded (one engineer cannot keep up with > 1 incident / day).
- Material change in any provider's pricing during the pilot that invalidates the comparison.

---

## Gate to broad rollout

Even if expansion-ready signals are all green, **broad rollout requires the gates listed in `DEVELOPER_ROLLOUT_ASSESSMENT.md` §5**. The pilot validates the dev-experience and pilot-scale cost case; it does **not** validate central enforcement, SSO/SCIM, reconciliation, or quality at scale. Those are engineering precondition gates that pilot success cannot substitute for.

**Suggested phased path after a successful pilot:**

| Phase | Scope | Pre-condition |
|---|---|---|
| Phase 2 | 250 devs, single org | Pilot success + G-001 (RBAC) + G-002 (per-identity budgets) + invoice reconciliation prototype + runbook v1 |
| Phase 3 | 2,000 devs, multi-region | + G-003 (tenant) + G-004 (control plane) + G-005 (SSO/SCIM) + G-010 (distributed audit) + Helm chart |
| Phase 4 | Mandatory | + Bypass-prevention (provider keys in vault) + reconciliation pipeline live + central dashboard |
