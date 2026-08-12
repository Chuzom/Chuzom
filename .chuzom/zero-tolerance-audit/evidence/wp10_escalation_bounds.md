# WP-10 — escalation integrity

Date: 2026-08-12. Findings RED3-04, RED3-05, RED3-06, RED3-07.

---

## The plan names a function that does not exist

WP-10 says "add `replan_fn` to `run_delegation()` or delete the dead path".
There is no `run_delegation`. The entry point is `chuzom.agentic.delegate.delegate`.
Recorded because a criterion referring to a non-existent symbol cannot be
mechanically verified, and gate G-C is supposed to detect criteria drift.

## `replan_fn` — deleted (owner decision, 2026-08-12)

It worked when called and had **no production caller**. `delegate()` accepted it
and threaded it to `MGEEEngine`; nothing in `src/` ever supplied one. Its only
caller anywhere was `tests/test_agentic_mgee.py::test_s8_replan_tail_once`, so
the behaviour that test asserted never occurred outside that file.

Third instance of this exact shape in one session, after OKF's
`find_relevant_sessions` and RED3-01's reversibility gate: a working mechanism,
tested, wired through several layers, never invoked.

Deleted rather than disabled, and deleted **completely** — `MGEEEngine.__init__`,
`delegate()`, the `ReplanFn` type alias, `TaskLedger.replanned`, the `"replan"`
member of `EVENT_KINDS`, its glyph, and three stale docstrings that still listed
`'replan'` as a reachable status. A half-deleted path is its own trap: an
unreachable status left in the event vocabulary reads as a supported capability
to anyone auditing the surface.

The S8 test now pins what production actually does when the ladder is exhausted
(blocks), plus a guard that the parameter cannot reappear in either signature.

## `budget_cap_usd` — kept and pinned as inert (owner decision: pin, never delete)

Two claims were being conflated:

1. `budget_cap_usd` stops a runaway. **False under default adapters.**
2. The engine terminates. **True.**

`CodexAdapter.cost_per_call_usd` and `ReactAdapter.cost_per_call_usd` both
default to `0.0` — correctly, because ChatGPT-subscription Codex really is
metered at zero. The engine charges the ledger with exactly that number, so
`spent_usd` never moves, `budget_left()` never falls, and the
`budget_left() <= 0` check at the top of the attempt loop can never fire.

Pinned by test: `budget_cap_usd=0.01` and `budget_cap_usd=1000` produce
**identical attempt counts**. An operator setting a budget on free tiers expecting
it to stop a runaway is relying on something that does not happen, and a test
asserting the comfortable belief would have kept that expectation alive.

**A fake price was deliberately not invented.** Giving free adapters a non-zero
`cost_per_call_usd` would make the budget check fire, at the cost of putting a
fabricated number into the same ledger that feeds savings reporting. The plan
permits the alternative — "an explicit attempt-count cap for genuinely free
tiers, documented" — and that is what is asserted instead.

## Hard bound: worst-case attempts and spend are computable and asserted

- attempts ≤ `milestones × tiers × max_attempts_per_tier`
- spend ≤ `tiers × k × price_per_call` (+1 call of overshoot)

Both asserted against a never-converging agent. The attempts test also asserts
`actual > 0`, so a harness that silently fails to run the agents cannot satisfy
the bound vacuously.

## RED3-06 — artifacts now reach the milestone that depends on them

`frozen_context()` carried `artifacts` all along. `pack_prompt()` rendered only
`- [ID] description`, so a milestone depending on an earlier one's OUTPUT was
told *that* it ran and nothing more — it could guess or redo, never build on it.

**Fixing this nearly reopened a P0.** Artifacts are agent output — untrusted by
construction — and `wrap_untrusted_context` was applied to `session_context` and
`relevant_context` but **not** to artifacts. Rendering them raw would have
reopened RED6-02, the injection→exfiltration chain WP-01 closed.

They are wrapped at the **ledger**, not at the render site, for the reason the
existing code already documents for the other two blocks: an escalated tier that
packs its own prompt cannot route around a boundary applied in
`frozen_context()`. Bounded at 2000 chars, because an unbounded artifact would
push the real task out of the context window — which presents as "the agent
ignored its instructions", not as a size error.

Three tests: the artifact arrives, it is wrapped, it is bounded.

## RED3-07 — planner milestone cap

`MAX_PLAN_MILESTONES = 50`. The plan comes from a MODEL, so its length is model
output, not a user-chosen parameter; worst-case attempts scale with milestone
count, so an unbounded plan removes the engine's bound entirely.

**Rejected, not truncated.** Silently dropping the tail would execute a different
plan than the one produced, and the tail is precisely where a plan's verification
and cleanup steps live — truncation would discard exactly the milestones that
make a plan safe.

## A near-miss in my own test, worth recording

`test_planner_rejects_an_oversized_plan` first used the acceptance marker `"ok"`,
which the planner rejects as *trivial* independently of the cap. The test passed
while proving nothing about the milestone limit. It now asserts the rejection
**reason** contains "cap".

That is the third probe-not-validated error in this session, after the equivalent
mutant (M2) and the twenty-site shotgun (M5). All three passed, all three
measured nothing, and all three read as confirmation. Assert on reasons, not on
the mere fact that an exception was raised.
