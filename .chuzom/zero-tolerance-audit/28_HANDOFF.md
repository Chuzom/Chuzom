# Handoff — 2026-08-16, updated 2026-08-17

Written because the working task list is ephemeral and the durable record is this
directory. Everything below is either done and committed, or a decision waiting on the
owner. Nothing is "in progress".

---

## 0 · Decisions taken 2026-08-17 — §1 below is kept for its reasoning

| decision | outcome | landed |
|---|---|---|
| **D1** the 0.80 floor | **ship stating G-F NOT QUALIFIED** — not waived, not amended | doc 29, `c55316f` |
| **D2** what the dashboard is for | **two named panels**: "all routed traffic" from `usage`, "classified routing" from `routing_decisions` | `ea3c436` |
| **D3** the `usage.db` accessor | **not now** — the CHZ-SR-01 ratchet holds at 182 | still open, by choice |
| **D4** the gateway | no action — the 2×2 reproduction cleared it | recorded |

Plus, unblocked by D1/D2 and now done: **#58's actionable half** (the hook records its own
phase breakdown under `CHZ-FO-HOOK-SLOW` when it breaches 5s, so the next occurrence
diagnoses itself), and **W4** (the panel states its coverage and distinguishes *no data*
from *no activity*).

**Still open, both deliberately:** #58's root cause (unreproducible; nine hypotheses
refuted; now self-diagnosing) and #62 (the ~38-site accessor migration, D3).

One deployment fact worth knowing: `~/.claude/hooks/chuzom-auto-route.py` and
`src/chuzom/hooks/auto-route.py` are **separate files kept in sync** by
`check_and_update_hooks()`, which fires when the MCP server starts. Both of today's hook
fixes are therefore live. The source comment notes this does **not** fire on
Cursor/Windsurf/Codex, which never start the MCP server — on those hosts the version stamp
is the only staleness signal and a reinstall is required.

---

## 1 · The four decisions (as originally posed — kept for the reasoning)

### D1 — the G-F 0.80 floor  *(blocks release)*

G-F is **NOT QUALIFIED** and can no longer be qualified by the pre-registered route: the
holdout is contaminated (doc 26). Three options, none of which I can take:

| option | consequence |
|---|---|
| amend the floor (e.g. staged 0.50 with a ratchet) | recorded amendment; more defensible than a blanket waiver |
| waive it | G-F becomes advisory |
| ship stating G-F NOT QUALIFIED | honest; the train/validation figures still report real coverage |

The measured position: TRAIN **1138/1518 = 0.7497**, VALIDATION **329/468 = 0.7030**
(95% LB 0.6601), COMBINED **1467/1986 = 0.7387**. These are train/validation figures and
**must never be reported as a held-out estimate**. Doc 61's measurement suggests the true
figure is ~0.789 combined, depressed by false timeouts — an estimate from n=6, not a
substitute for the recorded number.

### D2 — what the routing dashboard is FOR  *(blocks W3/W4)*

`routing_decisions` records `llm_route` and `llm_auto` only, not the `llm(task=…)` family
(doc 27). "How does the router behave when it classifies" and "what does all traffic
actually use" are different questions; the panel answers the first while appearing to
answer the second. Decide whether to answer both and name them, or narrow the label.

**Do not** simply start writing rows from every caller: it moves every denominator in a
percentage table, silently.

### D3 — `usage.db` / `usage.json` through one accessor  *(~38 sites)*

The survey's top recommendation. `usage.db` is resolved ~23 different ways. It relocates
user data, so it needs a compatibility decision (read-old/write-new? one-time move?).
`CHZ-SR-01` holds the line at 182 meanwhile.

### D4 — the gateway

`com.chuzom.gateway.plist` restarts it within seconds of a kill. It was wrongly blamed for
a 36s hook stall (doc: task #58 — nine hypotheses refuted, 2x2 reproduction found nothing).
It is **not** currently known to cause harm. Left running.

---

## 2 · Landed this session

| commit | what |
|---|---|
| `e3688d2` | checkpoint 2: 0.6360 → 0.7387; stopping rule NOT met; 11 mutants regressed killed→not-killed |
| `0e4c8ea` | **holdout declared contaminated** (doc 26) + Group E notification shims, 32/66 TRAIN |
| `411509f` | three production defects fixed (coverage.snapshot hoisted parse, duplicate allowlist entry, `malformed_n` exposed) |
| `0aa714b` | hook emits directive **before** the accounting write; exclusion rule B reads code not prose |
| `82d574a` | CHZ-FO-02 (survivable ≠ logged) + CHZ-SR-01 state-root ratchet |

Full suite green at every commit; nine gates at the last.

---

## 3 · The findings worth remembering

**The holdout was contaminated by my own verification method** (doc 26). Per-mutant
verification enumerated mutants from generated source instead of `train.txt`, so every run
swept holdout members too — and test-writing was then adapted to those survivor lists.
Standing rule now: **every verification filters against `train.txt` first.**

**The mutation score under-reports itself.** 5 of 6 sampled timeout-marked mutants are
killed in 4–9 seconds against their own covering tests. The ⏰ marking is an artefact of 18
parallel workers, and doc 20 §4 counts timeouts as survivors. ~100 of 121 are probably real
kills. Direction is safe (deflation, never inflation).

**Two gates could not detect the defects they were named for.** `lint_fail_open` asked "is
this logged?" when the defect was "is this survivable?" — measured 0 violations on both the
fail-open and fail-closed versions of the code that leaked. The exclusion rule read a
*module docstring* as an invocation and dropped 8 tests, including the RED2-02 guard.
Fixing the second exposed a false negative underneath it: **one over-exclusion was masking
one under-exclusion.**

**`is_isolated()` over-claimed.** 182 sites resolve `~/.chuzom` themselves. The docstring
now states the limit where a reader will find it, and a ratchet stops the count growing.

---

## 4 · Method notes that earned their place

- **Measurement beat reasoning, decisively.** On the 36s hook stall: nine hypotheses from
  reading code, all refuted; one profiler call localised it. Track record this session was
  roughly 4/4 for measurement and 0/9 for source-reading on that class of question.
- **Prove the RED.** A regression test for the hook fix passed against the *reverted* code —
  the shim never took effect. Only reverting the fix exposed it. A green test proves
  nothing until you have watched it fail.
- **A control that fails invalidates everything downstream.** Two `resolve` mutants were
  briefly reported as killed; the "failure" was a source-scanning test hitting the repo's
  30s timeout rather than the harness's 300s — the exact false-kill mechanism Amendment 2
  exists to prevent, walked into while investigating it.
- **A routed model flagged its own answer as ungrounded** and its citations were fabricated
  bibliography. The guardrail worked; the answer was discarded rather than relayed.

---

## 5 · Deliberately not done

- **Group D** (~199 mutants): its justification vanished with the floor. Closed as
  deprioritised, not completed, so the choice stays visible.
- **The 3,667 historical UNKNOWN rows**: left UNKNOWN permanently by owner decision.
  `is_reportable` stays False rather than showing a number derived from contaminated
  history.
- **Raising the mutation timeout**: Amendment 2 already moved it 30s → 300s, and doc 21's
  own criterion says a third amendment is the signal to reassess the instrument.
- **Migrating the 182 state-root sites**: relocates user data. Owner's call (D3).
