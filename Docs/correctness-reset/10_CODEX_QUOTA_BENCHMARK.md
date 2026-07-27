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

## Second run — moderate + hard corpus (2026-07-27, real Codex quota + local judge)

Ran `moderate + hard` (33 prompts, 16 subjective) through the same lineup, with a **local
Ollama judge** (`qwen3.5:latest`) for the subjective prompts (free, no quota — but see the
judge caveat below).

| arm | Codex frontier calls | mean quality (0–5) |
|---|---|---|
| `always-codex` (control) | **33 / 33** | 3.06 |
| `chuzom` | **9 / 33** (24 non-Codex) | 2.88 |

- **Codex frontier calls freed: 24 / 33 = 73%** — down from easy's 100%, exactly the expected
  curve: harder prompts pull Chuzom to the frontier more (9 escalations vs 0 on easy).
- **Chuzom's 24 "non-Codex" calls are not all local:** on 2 hard prompts (hard-10, hard-16) it
  escalated to the **Claude-Opus subscription host** (`anthropic/claude-opus-4-8`) via the
  subscription path — a different frontier, not Codex. The 73% is specifically *Codex-quota*
  freed; Chuzom still used a (host) frontier ~2× on hard prompts. Honest, not hidden.

### ⚠️ The quality numbers here are LOW-CONFIDENCE — the judge is the confound
Both arms scored ~3/5, and the local Ollama judge gave **q=1 to several genuine frontier
responses** — Codex on mod-01/04/11/14 and hard-09/11, and even Claude-Opus on hard-10/16
(17 `q=1` rows total). A frontier model scoring 1/5 on these prompts is implausible; it means
`qwen3.5` is a **harsh/noisy subjective judge**, so the `delta=−0.18` "non-inferiority" is **not
trustworthy**. What IS trustworthy is the **frontier-calls-freed** figure (73%) — it's counted
objectively from `model_chosen`, independent of the judge. **To draw any quality conclusion, the
run must be repeated with a reliable frontier-grade judge** (needs a metered/subscription judge
model with real capability), which we did not have.

**Verdict impact: none.** This is still the quota metric, not cash; Gates 15/16/17 remain FAIL,
and the quality axis is inconclusive pending a real judge. Release verdict unchanged: **RELEASE
NOT QUALIFIED**.

## Third + fourth runs — the CASH benchmark (metered GPT-4o, 2026-07-27)

With a billing-active `OPENAI_API_KEY`, ran the real cash A/B: **Chuzom vs always-GPT-4o**
(`FixedModelRouter openai/gpt-4o`, metered). This is the Gate-15 test — positive net *cash*
savings — and (for moderate/hard) a **reliable GPT-4o judge** replaces the weak Ollama judge.

### Easy corpus (20 prompts, objective grading — reliable, no judge)

| arm | cost | quality |
|---|---|---|
| always-GPT-4o | $0.00242 | 5.00 |
| chuzom | **$0.00000** (100% local Ollama) | 4.80 |

Net cash **+$0.00242**; delta −0.20 (objective, trustworthy). **Gates 15 / 16 / 17 all PASS** —
a **clean** cash win: Chuzom answered every easy prompt on free local models at near-parity.
Small in absolute terms (short prompts), but real and un-confounded.

### Moderate + hard corpus (33 prompts, GPT-4o judge)

| arm | cost | quality (GPT-4o judge) |
|---|---|---|
| always-GPT-4o | $0.03030 | 4.94 |
| chuzom | **$0.00000** | 4.61 |

- Net cash **+$0.03030** (Gate 15 net>0 = True); quality delta **−0.33**, within the 0.5 margin,
  now **reliably judged** (Gate 16 = True). Every prompt Chuzom escalated scored q=5.
- **Gate 17 = FALSE — and this is the key honesty catch.** On 11/33 prompts Chuzom escalated to
  **other subscriptions** — `codex/gpt-5.5` (9) and `anthropic/claude-opus` (2) — recorded at
  $0 cash. Gate 17 correctly flags all 11 as **unclassified spend**: a non-local model at $0
  means its true (quota) cost was not captured. So Chuzom did **not** do the hard prompts for
  free — it **offloaded them to other paid subscriptions** whose cost is real but unpriced here.

### Honest conclusion (Gates 15/16/17)

- ✅ **Chuzom genuinely saves cash when it stays fully local** — easy corpus is a **clean** pass
  of all three gates (chuzom $0 vs GPT-4o $0.0024, reliable objective quality).
- ✅ **Quality holds when it escalates** — moderate/hard, reliably GPT-4o-judged: −0.33, within
  margin, escalated prompts all q=5.
- ❌ **It does NOT cleanly demonstrate blanket cash savings across difficulty.** On hard prompts
  the apparent "$0" is **subscription-offload** (Codex/Claude-Opus quota), not free work —
  **Gate 17 fails**, so the +$0.03 overstates the real resource saving. The benchmark correctly
  refuses to certify it.

**Gate impact:** the easy-corpus run is the first clean Gate 15/16/17 pass, but a *single small
easy corpus* is not the release bar, and the moderate/hard run shows the savings claim is
**confounded once Chuzom must escalate** (subscription-offload). A defensible Gate-15 PASS needs
a run where the escalation tier is **also metered** (so the offload cost is captured and the
comparison is apples-to-apples), across a larger corpus, then the two-consecutive-audit rule
(#6). Until then the verdict is unchanged — **RELEASE NOT QUALIFIED** — now for a precise,
evidence-based reason rather than an un-run gate.

## To extend

- Run the **moderate/hard** corpora for a fuller quota curve (more escalations; needs an
  LLM judge for the subjective prompts — a judge model + its own quota).
- For the **cash** proof (Gate 15), set a metered key and run `control_group_routers()` (the
  `always-claude-host` / GPT-4o arm) → `evaluate_savings`.
