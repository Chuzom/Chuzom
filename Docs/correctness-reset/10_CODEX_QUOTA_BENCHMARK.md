# Chuzom Correctness Reset — 10. Subscription-Host Quota Benchmark (Codex)

A **real** control-group run against the Codex frontier, executed 2026-07-27. Codex is a
paid **subscription** (finite quota/limits), so the honest savings unit is **frontier calls
avoided**, not cash — Chuzom keeps work on local models and escalates to the frontier only when
needed. This is the North-Star metric for a *subscription* host (P0-2 host-mode framing: quota
freed / potential, not metered cash).

## Setup

- **Command:** `codex_control_group_routers()` (Chuzom vs `always-codex`) over the **easy**
  corpus (20 objective prompts → deterministic string-match grading, so **no judge quota**).
- **Chuzom arm:** the real `chuzom.router` (`route_and_call`, ledger suppressed).
- **Control arm:** `CodexRouter` — every prompt to the Codex CLI frontier (`gpt-5.5`).
- Only external provider used: **Codex** (subscription). No metered API keys were present.

## Result (`evaluate_quota_savings`)

| arm | frontier (Codex) calls | mean quality (0–5) |
|---|---|---|
| `always-codex` (control) | **20 / 20** | 5.00 |
| `chuzom` | **0 / 20** (all local Ollama) | 4.80 |

- **Frontier calls freed: 20 (100%)** — Chuzom answered every easy prompt on local Ollama
  (qwen2.5-coder / qwen3.5 / qwen3-coder:30b / hermes3 / devstral), spending **zero** Codex
  quota.
- **Quality non-inferior:** delta **−0.20** (within the 0.5 margin). One local miss (easy-04,
  q=1 on `qwen3.5`); the other 19 matched the frontier at q=5.
- Gates (subscription framing): `gate_quota_freed=True`, `gate_quality_non_inferior=True`.

## Honest scope — what this does and does NOT show

- ✅ **Does** demonstrate the North-Star subscription value on this corpus: routing preserved
  quality while avoiding **all** frontier-quota consumption. That is a real, measured,
  un-fabricated result (frontier calls counted from `model_chosen`; Codex tokens are reported as
  0 because the Codex CLI returns none — never estimated).
- ⚠️ **Directional only.** This is the **easy** corpus, where local models are strongest; 100%
  local routing is expected here. On moderate/hard prompts Chuzom escalates more, so the freed
  fraction will be lower. This is **not** a "Chuzom always frees 100%" claim.
- ❌ **Does NOT flip Gate 15.** Gate 15 requires positive net verified **cash** savings, which is
  only demonstrable against a **metered, paid** frontier (a real `OPENAI_API_KEY` GPT-4o or
  `ANTHROPIC_API_KEY` Claude baseline). Codex is $0-marginal cash, so no cash figure is possible
  here. Gates 15/16/17 remain **FAIL** pending a metered run; the release verdict is unchanged:
  **RELEASE NOT QUALIFIED**.

## To extend

- Run the **moderate/hard** corpora for a fuller quota curve (more escalations; needs an
  LLM judge for the subjective prompts — a judge model + its own quota).
- For the **cash** proof (Gate 15), set a metered key and run `control_group_routers()` (the
  `always-claude-host` / GPT-4o arm) → `evaluate_savings`.
