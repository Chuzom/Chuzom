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

## Fifth run — the CLEAN metered-escalation cash A/B (2026-07-27)

The direct answer to "point the escalation tier at OpenAI and re-run." This removes the
subscription-offload confound the fourth run flagged, by forcing every escalation onto a
**metered** tier and eliminating all cache contamination:

- **Escalation tier metered:** `CHUZOM_DISABLE_SUBPROCESS_BACKENDS=codex,gemini_cli` +
  `CHUZOM_CLAUDE_SUBSCRIPTION=false` — Codex/Gemini/Claude subscription hosts off, so
  escalations must reach a priced OpenAI model (`gpt-4o`, `gpt-4o-mini`, or `o3`).
- **Zero cache contamination:** ran against a **fresh isolated `CHUZOM_DB_PATH`** (empty
  `semantic_cache` table) and a cleared `bench/cache/`. This matters: the router's semantic
  response cache (`semantic_cache.check`, router.py:3244) is gated **only** on task_type /
  `model_override` — **not** on `prompt_cache_enabled` — so earlier reruns served stale
  `cache/…` model choices from a prior run's rows. A fresh DB is the only way to force every
  prompt to route live.

### Moderate + hard corpus (33 prompts, GPT-4o judge)

| arm | cost | quality (GPT-4o judge) |
|---|---|---|
| always-GPT-4o (control) | $0.02930 | 4.88 |
| chuzom | **$0.03941** | **3.88** |

- **NET cash −$0.01011** — Chuzom is **more expensive** than just using GPT-4o. Gate 15 = **False**.
- **Quality delta −1.00** — well beyond the 0.5 margin. Gate 16 = **False**.
- **5 unclassified** (`mod-01/04/11/14`, `hard-11`). Gate 17 = **False**.
- **All three gates FAIL.** This is the honest, un-confounded moderate/hard result.

### Why it flips negative once the offload is removed

The fourth run's apparent "+$0.03 at −0.33 quality" was **subscription-offload** — the hard
prompts answered by Codex/Claude-Opus at a fake $0. Metered, that illusion is gone:

- **5 hard prompts EXHAUSTED** (`hard-04…08`, `model_chosen=<exhausted>`, q=1). With
  subscriptions off and `openai/o3` failing its structure gate, Chuzom's premium chain ran
  out of models. Those five q=1 failures are what drives the −1.00 quality drop — i.e. the
  offload was *masking real capability gaps* on the hard tier, not saving money.
- **o3 escalations are expensive and not reliably better:** `mod-05` → o3 at **$0.015 for
  q=2** (worse than GPT-4o), `hard-10/16` → o3 at ~$0.012 each. Metered escalation on the
  hard tier costs more than the flat GPT-4o baseline it's compared against.

### Two honesty caveats — both make the negative *more* robust

1. **Codex still leaked 5× at $0.** `CHUZOM_DISABLE_SUBPROCESS_BACKENDS` suppresses the Codex
   *availability check* but does **not** remove Codex when it is already in the broker/provider
   chain (router.py:606–611: `… or "codex" in _broker_provs`). So 5 escalations still recorded
   as unpriced `codex/gpt-5.5` $0 (correctly flagged by Gate 17). Had those been metered too,
   Chuzom would be **even more** expensive → the net-negative conclusion only strengthens.
   *(Separate finding: the disable flag is incomplete against broker-sourced Codex — logged,
   not chased here.)*
2. **The 5 exhaustions are exactly what production offload hides.** In normal operation those
   hard prompts silently offload to a subscription; the benchmark makes the underlying
   "premium chain can't do this on metered-only" visible.

### Honest conclusion (supersedes the fourth run's moderate/hard read)

- ✅ Easy corpus remains a **clean** Gate 15/16/17 pass (fully local, un-confounded).
- ❌ **Moderate/hard is a clean NEGATIVE once the escalation tier is metered:** net −$0.01,
  quality −1.00, all gates fail. There is **no blanket cash win across difficulty**, and the
  earlier "+$0.03" was an artifact of pricing subscription-offload at $0.
- The benchmark harness behaved correctly throughout — Gate 17 flagged every unpriced
  escalation; the exhaustion rows are honestly recorded at q=1, not hidden.

**Gate impact:** Gates 15/16/17 read **FAIL** on this run — but the fifth run is not a verdict,
it is a **diagnosis**. It localised the loss to a specific, fixable defect (below), not a
capability ceiling. See the sixth run for the fix and the before/after.

## Root-cause diagnosis (what the fifth run actually found)

The −1.00 quality drop and net-negative cost were **not** Chuzom being incapable on hard
prompts. They trace to one defect chain in `router.py` / `gates.py`:

1. **The `STRUCTURE` gate rejected valid prose.** `_check_structure` failed any response >200
   chars with <2 Markdown markers — so a legible multi-sentence answer with no `##`/`-` was
   discarded as "no structure" (log: `structure: no structure: 0 markers in 466 chars`). The
   gate's own docstring says gates "catch garbage, not wrong answers"; requiring bullet points
   on prose is a false-positive machine.
2. **Exhaustion returned nothing.** When every model's answer was gate-rejected, the router
   raised `RuntimeError("All models failed")` — so 5 hard prompts recorded `<exhausted>` / q=1.
   A real frontier answer that failed a *heuristic* was thrown away rather than returned.

Both are **lever ①** from the improvement roadmap, and both were fixed (PR #201).

## Sixth run — the fix applied (2026-07-27, same clean conditions)

Identical setup to the fifth run (fresh isolated `CHUZOM_DB_PATH`, metered escalation,
Codex/Claude subscriptions off, GPT-4o judge) — re-run **with** the lever-① fix: a prose-aware
structure gate (prose counts as structure) plus an **exhaustion floor** (return the best
heuristic-rejected answer instead of raising).

| metric | fifth run (before) | **sixth run (after fix)** |
|---|---|---|
| control (GPT-4o) cost | $0.02930 | $0.02958 |
| chuzom cost | $0.03941 | **$0.02662** |
| net cash | **−$0.01011** | **+$0.00296** (Chuzom cheaper) |
| quality delta | **−1.00** | **−0.45** (within 0.5 margin) |
| exhausted rows (q=1) | **5** (hard-04…08) | **0** |
| Gate 15 (net savings) | ❌ | **✅ True** |
| Gate 16 (quality non-inferior) | ❌ | **✅ True** |
| Gate 17 (no unclassified spend) | ❌ | ❌ (residual Codex leak only) |

- **Gates 15 and 16 flip FAIL → PASS on moderate/hard** from lever ① alone. The exhaustion
  collapse is gone: **zero** prompts exhaust; the −1.00 quality drop becomes −0.45 (within the
  0.5 non-inferiority margin).
- **o3 answers are now accepted instead of discarded:** mod-05 went from **q=2 at $0.015** (its
  answer rejected, then a worse fallback accepted) to **q=5 at $0.004** (real answer kept). o3
  escalations are correctly metered ($0.004–0.011), all q=5.
- **Gate 17 still FAIL — but the reason narrowed** to the residual Codex-broker leak (6
  escalations still `codex/gpt-5.5` at $0 because `CHUZOM_DISABLE_SUBPROCESS_BACKENDS` doesn't
  remove broker-sourced Codex, `router.py:606–611`). That is **caveat #1 / lever ②-adjacent**,
  not the gate bug. Because those 6 calls are unpriced, the **+$0.003 net is thin** — if metered
  they could tip it slightly negative, so Gate 15 is "positive but still mildly confounded,"
  while **Gate 16's quality flip is robust** (it depends on exhaustions vanishing, independent
  of Codex pricing).
- Remaining 2 q=1 (mod-07, mod-10) are genuine **local-model** misses (not escalated) —
  candidates for **lever ②** (leaderboard-driven escalation ladder / earlier escalation).

**Gate impact:** the fix converts the moderate/hard tier from a clean negative into a
**quality-non-inferior, net-positive-but-thin** result — Gate 16 a real PASS, Gate 15 positive,
Gate 17 blocked only on the narrower Codex-broker leak. The path to a fully clean moderate/hard
Gate 15/16/17 pass is now concrete: (a) fix the broker-Codex leak so those escalations are
metered/removed (caveat #1), then (b) lever ② to lift the last local q=1 misses. Verdict remains
**RELEASE NOT QUALIFIED** — but for a shrinking, well-localised reason, with the biggest defect
now fixed and regression-locked (`test_exhaustion_floor`, `test_contract_gates` prose cases).

## To extend

- Run the **moderate/hard** corpora for a fuller quota curve (more escalations; needs an
  LLM judge for the subjective prompts — a judge model + its own quota).
- For the **cash** proof (Gate 15), set a metered key and run `control_group_routers()` (the
  `always-claude-host` / GPT-4o arm) → `evaluate_savings`.
