# Chuzom v-next — "Advisor, not Warden" + the path to honest claims

> Status: design sketch / discussion doc. Not a commitment. Authored as a reviewable
> artifact for the maintainer to accept, reject, or reshape.

## 0. Why this doc exists

Chuzom's `NORTH_STAR.md` is sound. The problem is that the **current implementation
contradicts its own North Star in the two exact ways the North Star names as negative**:

> A change is North-Star-negative if it: *blocks a tool-needing task behind a no-tools
> tool* … or *claims a guarantee that isn't measured.*

Both were observed directly during the v1.0.1 hardening work:

- The enforcement hook **blocked a `git push` behind `llm_query`** (a no-tools completion
  tool) — a literal instance of "blocks a tool-needing task behind a no-tools tool."
- A large batch of **unmeasured claims** had to be deleted this cycle: "never blocks",
  "60–90% savings", `recorded cost: $0.0000` shown next to routing activity, plus
  injected drafts framed as answers.

So v-next is not a pivot. It is: **make the implementation obey the North Star it already
has, and only claim what is measured.**

---

## Part A — The design: "Advisor, not Warden"

### A.1 Goals / non-goals

- **Goal:** route to the cheapest *capable* tier, keep the agent's agency, never block real
  work, and make every user-facing number a *measured fact*.
- **Non-goal:** coercion as the default. Hard-blocking survives only as an explicit,
  clearly-labeled spend guard.

### A.2 Collapse 8 enforce modes → 3

| Mode | Behavior | For |
|---|---|---|
| **advise** (default) | classify → suggest → rich telemetry; never blocks; the agent decides | everyone |
| **budget-cap** (opt-in) | hard-block **only** when a real spend ceiling is crossed; labeled a spend guard, never a productivity gate | shared keys / CI cost control |
| **off** | no hook activity | — |

Delete `smart/hard/strict/soft/shadow/suggest`, the pending-directive lock, auto-pivot,
loop-detection, and the escape valves. That machinery exists **because** the default is
adversarial. Remove the adversary and the complexity is unnecessary.

### A.3 Route *executions*, not *completions* (the North Star's core reframe)

- The unit of routing is **`llm_act`** (tool-capable harness: cwd + read/write/bash/git +
  repo state + verification), never `llm_query` for anything that touches files/shell.
- A task classified as needing tools is **never** offered a no-tools tool. On uncertainty,
  **fail open to the agent** — never gate.
- Classification hardening: `git`, file edits, deploys, and meta/introspection prompts are
  structurally non-routable-as-query. (These were misclassified as `query`/`image`/
  `coordination` during authoring of this doc — that class of error is the bug to kill.)

### A.4 Honesty by construction

- **No injected drafts presented as answers.** No required `🎯 routed →` attribution line the
  agent did not earn. If a route executed, the **system stamps provenance from real execution
  data**; if it did not, nothing is stamped. This single rule prevents most honesty defects.
- **Realized savings only.** A saving is counted when the routed result **passed objective
  verification AND was adopted by the host** (not overridden). "Potential savings" is a
  separate, clearly-labeled number.
- **Never reframe hook text as instructions.** Drop rules-file framing like "ROUTING HINT =
  HARD CONSTRAINT (NOT a suggestion)" — it is prompt-injection-shaped, and the models it
  steers are built to resist exactly that.

### A.5 Capability = live leaderboard (already in the North Star)

- The escalation ceiling tracks `artificialanalysis.ai/leaderboards` per task type, not
  "Claude = top." Cache it, refresh weekly, degrade gracefully offline. This is written into
  the North Star but must actually drive the ladder.

---

## Part B — The path to *honestly* claiming "saves money · keeps quality · big leverage"

The discipline: **a claim may not appear in the README until a measurement shows it, net of
Chuzom's own costs, on a representative workload.** Until then the claim is softened or
removed (per the North Star's own "no unmeasured guarantee" rule).

Each phase below has an **exit gate** — the measurement + threshold that unlocks the claim.

### Phase 0 — Stop the North-Star violations + stand up honest measurement (foundation)

Nothing else is trustworthy until this lands.

1. **Flip the default to `advise`** (coercion off by default; `budget-cap` opt-in remains).
2. **Delete draft-injection + forced attribution** from the hooks.
3. **CI invariant:** a tool-needing task is never blocked behind a no-tools tool — asserted in
   CI, so a regression can't ship.
4. **Realized-savings ledger:** extend the route-quality ledger to record, per route:
   `chosen_tier`, `frontier_baseline_cost`, `actual_cost`, `verified` (gate passed?),
   `adopted` (host used it?), and `chuzom_overhead` (classifier + failed/re-dispatched
   attempts + escalation).

**Exit gate:** the system no longer contradicts its North Star, and a *defensible* realized-
savings number exists (even if small). Bad honest data beats good dishonest data.

### Phase 1 — Earn "saves money"

- **Net realized savings** = Σ(frontier_baseline − actual) over routes that were verified AND
  adopted, **minus** Chuzom overhead. If this is not reliably positive, the claim is not true.
- **Representative soak/benchmark:** replay a real (anonymized) session corpus, not synthetic
  prompts, and report **$/week saved with a confidence interval** for a defined workload
  ("a Claude Code user doing mostly Q&A + boilerplate").
- **Cost honesty:** the number must net out classifier calls, gate-rejected/re-dispatched
  attempts, and rework from bad routes (the double-dispatch bug this cycle is exactly the kind
  of hidden cost that must be counted).

**Exit gate:** net realized $/week > 0 with a stated CI on the reference workload → put *that
measured number* in the README (or leave the claim out).

### Phase 2 — Earn "keeps quality"

- **Quality-parity eval harness:** a labeled set spanning task types; each routed answer scored
  against the frontier answer by a rubric (model-graded + spot human audit). Report **quality
  delta per tier**.
- **Classification accuracy:** precision/recall per task type. A misroute (hard task → weak
  model) is where quality silently drops; this is the primary risk and must be tracked.
- **Verify-gate effectiveness:** the false-negative rate of the acceptance gates — do they
  actually catch bad output before it ships? A "keeps quality" claim rests on this backstop.

**Exit gate:** quality delta within a stated tolerance on the eval set AND gate false-negative
rate below a stated threshold → claim "quality parity on routed tasks, within X%," with the
method linked. Never "keeps quality" unqualified.

### Phase 3 — Earn "big leverage"

- **Quota-extension multiplier:** on real sessions, measure Claude quota consumed **with vs
  without** Chuzom → a median multiplier ("3.×" quota stretch), with the distribution, not a
  single hero number.
- **Retention as proof:** % of installs still enabled after N weeks. People keep advisors and
  disable wardens — retention is the honest proxy for "real leverage."

**Exit gate:** a measured multiplier with its spread + a non-trivial retention rate → claim
leverage as "median N× quota extension on real sessions," linked to method.

### Phase 4 — Execution-routing maturity (North Star core)

- `llm_act` as the **default** unit of routing; the leaderboard actually driving the escalation
  ceiling; escalation carrying the "done-frontier" forward so re-work isn't repeated.
- **Exit gate:** offloadable tool-work runs on cheaper tiers *with tools* (not bounced to the
  frontier), measured by the mis-route and tier-distribution metrics.

---

## Part C — Success metrics (measured, per the North Star)

| Metric | Definition | Honest claim it unlocks |
|---|---|---|
| Net realized savings $/week | Σ(baseline − actual) over verified+adopted routes − overhead | "saves money" |
| Mis-route rate | hard task → weak model that then escalated | (quality risk; must fall) |
| Quality delta per tier | routed vs frontier rubric score | "keeps quality (within X%)" |
| Gate false-negative rate | bad outputs the verify step let through | (backstop credibility) |
| Quota-extension multiplier | quota used without ÷ with, on real sessions | "big leverage (median N×)" |
| Tool-block-of-tool-task count | must be **0** (CI invariant) | North-Star compliance |
| Retention @ N weeks | installs still enabled | leverage is real, not forced |

---

## Part D — Immediate honesty step (independent of the roadmap)

Until Phases 1–3 produce measured numbers, the README should **soften or remove** the
unproven "saves money / keeps quality / big leverage" phrasing and replace it with what is
*true today*: "routes eligible prompts to local/free models; correctness independently
audited; savings/quality measurement in progress." Overstating is the exact North-Star
negative this whole effort exists to eliminate — the claims become assets the moment they're
measured, and liabilities every moment before.

---

*The most respectful version of Chuzom and the most useful version are the same version:
a sharp, honest advisor. Trust is what keeps a router switched on — and a router that is
switched on is the only one that saves anyone anything.*
