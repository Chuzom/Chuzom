# 06 — Agentic Delegation Audit (RED-3)

**Scope:** the agentic delegation / MGEE subsystem — `chuzom.agentic.*`, `chuzom/tools/agentic.py`,
`chuzom/tools/consolidated.py::llm_act`, plus the non-agentic completion surface
(`chuzom/tools/text.py::llm_query/llm_analyze/llm_code/llm_research/llm_generate`) insofar as it bears
on mandate item 7 (unverified completions), and the quality-signal modules (`judge.py`, `judge_cascade.py`,
`streaming_judge.py`, `scorer.py`, `gates.py`, `contract.py`, `response_validation.py`).

**Audit target:** worktree `AUDIT-c2c2882`, tag `v1.1.1`, SHA `c2c2882`, clean checkout.
**Interpreter used for every reproduction:** `<worktree>/.venv-audit/bin/python` exclusively.
**No production code was modified.** All reproduction scripts live under
`.chuzom/zero-tolerance-audit/evidence/red3/` and were executed against the real, unmodified source —
only network/subprocess *boundaries* (an injected `runner`/agent callable, exactly the seam the codebase's
own tests use) were faked, never the mechanism under test itself.

**Central question this document answers:** when Chuzom says a delegated task is `DONE`/`VERIFIED`, what
does that actually mean, and how much should a user trust it?

**Short answer, stated up front:** very little, for the majority of realistic tasks. The four objective
acceptance-check types are individually gameable by construction (not by an exotic adversarial model —
by *the cheapest, laziest satisfying answer*), the two safety mechanisms explicitly documented around the
engine (reversibility gate, replan) are both structurally unreachable from the shipped code path, the
budget cap that is supposed to bound financial/compute exposure is cosmetic under default wiring, and the
overwhelming majority of Chuzom's actual tool surface (every plain `llm_query`/`llm_analyze`/`llm_code`/
`llm_research`/`llm_generate` call — i.e. everything except the narrower `llm_delegate`/`llm_act` path) has
**no objective quality gate of any kind** between model output and what the user receives.

---

## Findings

### ID: RED3-01
**Severity:** P0
**Confidence:** PROVEN
**Area:** Reversibility gate / safety isolation
**Title:** The reversibility gate and git-worktree isolation are structurally unreachable from production — every "irreversible" milestone executes with full, unisolated write access

**Claim-Invariant violated:** Docs/agentic-router.md and the engine's own design (a `gate` parameter,
`chuzom/agentic/worktree.py`'s `reversibility_gate()`/`GitWorktreeOps`) imply irreversible milestones get
isolated execution (a worktree) and/or a merge-gate check before being accepted as done.

**Observed behavior:** `chuzom/tools/agentic.py::llm_delegate()` calls `run_delegation()` →
`chuzom.agentic.service.run_delegation()` → `delegate()`, and **none of these three functions accept or
pass a `gate=` argument anywhere in the production call chain.** `MGEEEngine.__init__` defaults
`self.gate = gate or (lambda _m, _r: True)` — an always-true no-op. `chuzom/agentic/worktree.py` (98
lines) is referenced by nothing except its own test file (`tests/test_agentic_worktree.py`), confirmed by
repo-wide grep.

**Expected behavior:** a milestone marked `reversible=False` should trigger worktree isolation and/or an
explicit merge-gate check before the change is accepted into the working tree and frozen `DONE`.

**Why this matters to a real user:** "irreversible" is exactly the risk category the gate exists for
(deployments, destructive migrations, deletions, external side effects). The safety mechanism named for
that exact case never runs in production, for any milestone, ever.

**Exact reproduction:** `evidence/red3/repro_reversibility_gate_unwired.py`, run via
`.venv-audit/bin/python`; output in the paired `.out` file. A single milestone `deploy-hotfix` marked
`reversible=False`, using the real unmodified `delegate()`/`MGEEEngine`/`TaskLedger`, with a fake tier-1
agent that does zero real work and only returns a canary string in its stdout, froze `DONE` with
`outcome: Outcome.COMPLETE`, `ok: True` — worktree isolation and gate check both silently absent.

**Evidence (file:line, command, output):**
- `src/chuzom/agentic/engine.py`: `self.gate = gate or (lambda _m, _r: True)`
- `src/chuzom/agentic/service.py` (full file, 59 lines): `run_delegation()` signature has no `gate` param.
- `src/chuzom/tools/agentic.py`: `llm_delegate()`'s call to `run_delegation(...)` passes no `gate=`.
- grep: `grep -rn worktree src/chuzom --include=*.py` → only `worktree.py` itself and
  `tests/test_agentic_worktree.py`.
- `evidence/red3/repro_reversibility_gate_unwired.out`: `outcome: Outcome.COMPLETE`, `ok: True`,
  `milestone.reversible: False`.

**Root cause:** the gate/worktree isolation was built and unit-tested in isolation but never wired into
the one production call chain (`llm_delegate` → `run_delegation` → `delegate`) that actually reaches users.

**Why existing tests missed it:** `tests/test_agentic_worktree.py` tests `worktree.py` directly by
constructing a `GitWorktreeOps`/`reversibility_gate` and calling it — it never exercises the real
`llm_delegate()` entry point end-to-end, so the wiring gap is invisible to it by construction.

**Blast radius:** every milestone in every delegated task marked irreversible, in perpetuity, until
`service.py`/`tools/agentic.py` are changed to thread a real `gate=`.

**Can this defect class exist elsewhere?:** yes — see RED3-05 (replan is the same class of defect: a
documented engine capability with a parameter that is simply never supplied by the one production caller).

**Recommended systemic fix:** add an integration test that calls the actual public `llm_delegate()`
MCP tool function (not `delegate()` directly) with a `reversible=False` milestone and a fake worktree-ops
double, and asserts the worktree ops were invoked. Then wire `gate=reversibility_gate(...)` through
`service.run_delegation()` → `tools/agentic.py`.

**Regression test that would prevent recurrence:** an end-to-end test asserting that
`chuzom.tools.agentic.llm_delegate` (the literal MCP-registered coroutine), given a plan containing an
irreversible milestone, results in at least one call to an injected `WorktreeOps` fake.

**Release blocking?** YES

---

### ID: RED3-02
**Severity:** P0
**Confidence:** PROVEN
**Area:** Acceptance checks — `diff_check`
**Title:** `diff_check`'s `symbols` check is a raw substring match with zero semantic understanding — a security-hole stub passes as verified-complete

**Claim-Invariant violated:** the product's core claim is that objective acceptance checks verify the
*work*, not the model's self-report, closing the "self-graded homework" gap that plain LLM output cannot.

**Observed behavior:** `diff_check(files=[...], symbols=[...])` (`chuzom/agentic/acceptance.py`) passes iff
the named files appear in the diff's file list and each symbol string is a substring of the diff text.
It never parses, executes, or reasons about what the code *does*.

**Expected behavior:** a check gating "implement password validation enforcing policy X" should fail if
the implementation is a no-op/wrong-op stub.

**Why this matters to a real user:** a `validate_password` that unconditionally `return True` (accepts
every password including empty) is a live security hole, and it is graded `DONE`/`VERIFIED`.

**Exact reproduction:** `evidence/red3/repro_diff_check_symbol_gaming.py`. A `FakeStubbingAgent` returns a
diff containing `def validate_password(pw): # TODO... return True  # always accepts`. Run through the real
unmodified `delegate()` with `diff_check(files=["auth.py"], symbols=["def validate_password"])`.

**Evidence (file:line, command, output):** `evidence/red3/repro_diff_check_symbol_gaming.out`:
`outcome: <success>`, `ok: True`, `milestone status: MilestoneStatus.DONE`, frozen diff contains
`return True  # always accepts -- SECURITY HOLE, not implemented`.

**Root cause:** acceptance-check vocabulary is deliberately restricted to syntactic/objective primitives
(`ALLOWED_CHECK_TYPES` in `planner.py`) with no semantic/behavioral verification tier available at all —
there is no "execute the function against test inputs and check the output" check type.

**Why existing tests missed it:** the check-type unit tests (`tests/test_agentic_acceptance.py`, inferred
from module structure) test that `diff_check` correctly matches/rejects given a diff — they do not test
whether a diff that satisfies the check can still be behaviorally wrong, because that was never in scope
for a substring-matcher's own unit tests.

**Blast radius:** every milestone plan that uses `diff_check` with `symbols` — which, per the planner's own
prompt template, is presented as a first-class, recommended check type for "implement function X."

**Can this defect class exist elsewhere?:** yes — `canary_check` and `cmd_check` (RED3-03) share the same
structural weakness: they verify a *proxy signal* the executor fully controls, not the actual requirement.

**Recommended systemic fix:** for any check type gating a *function's behavior* (not just its presence),
require at minimum a `cmd_check` running a planner-independent, pre-authored test — and even then see
RED3-03 for why that alone is insufficient. Longer-term: a check type that actually executes the produced
code against example inputs/outputs specified by the planner (or a held-out test the executor cannot see
or edit) is the only defensible objective check for "implements X correctly."

**Regression test that would prevent recurrence:** a test asserting `diff_check` rejects (or at minimum
flags low-confidence) a diff whose function body is trivially constant-returning relative to symbols named
as validators/checkers — imperfect, but a floor. The durable fix is architectural (see above), not a unit
test on the substring matcher.

**Release blocking?** YES

---

### ID: RED3-03
**Severity:** P0
**Confidence:** PROVEN
**Area:** Acceptance checks — `cmd_check`
**Title:** `cmd_check` is exit-code-only with no scope restriction — an executor can pass a test by rewriting the test itself instead of fixing the bug

**Claim-Invariant violated:** same as RED3-02 — objective checks are supposed to verify the requirement
independent of what the executor claims.

**Observed behavior:** `cmd_check` (`acceptance.py`) reports `ok=True` purely on process exit code.
Nothing in the acceptance layer, `CodexAdapter` (`sandbox_mode="workspace-write"`), or `ReActAgent`'s
`write_file` tool (scoped only to "inside cwd", not "outside files under test") prevents the executor from
editing the test file the check itself runs, instead of the source file the milestone was actually about.

**Expected behavior:** a check meant to verify "the bug in `calc.py` is fixed" should not be satisfiable by
editing `test_calc.py` to assert something trivially true.

**Why this matters to a real user:** this is the single most natural, lowest-effort "cheat" for any
model under time/capability pressure on a genuinely hard bug — weaken the assertion rather than fix the
code. It requires no adversarial intent, only ordinary laziness or incapability.

**Exact reproduction:** `evidence/red3/repro_cmd_check_test_tampering.py <repo_dir>`. Real git repo with
`calc.py::add(a,b)` returning `a - b` (real bug) and `test_calc.py` asserting `add(2,3)==5` (correctly
failing). Script simulates the executor's "fix": rewrites `test_calc.py` to `assert True`, re-runs the
identical `cmd_check` the milestone would use.

**Evidence (file:line, command, output):** `evidence/red3/repro_cmd_check_test_tampering.out`: `ok: True`,
and independently `calc.add(2, 3) == -1` (bug fully intact, correct answer is 5).

**Root cause:** exit-code-only verification with unrestricted filesystem write scope for the executor.

**Why existing tests missed it:** unit tests for `cmd_check` test the check's own exit-code interpretation
logic, not the executor's incentive/ability to rewrite the oracle it's being graded against.

**Blast radius:** every `cmd_check`-gated milestone where the command is (or includes) a test the executor
can also see and edit — i.e., essentially all of them, since the executor has full repo write access by
default (no reversibility gate — see RED3-01 — and no file-scope restriction anywhere in the adapters).

**Can this defect class exist elsewhere?:** yes, structurally identical to RED3-02; both are instances of
"the executor controls both the artifact and (indirectly) the oracle."

**Recommended systemic fix:** `cmd_check` milestones should run against a test file the executor cannot
write to (e.g. copied into an isolated worktree — which would also fix RED3-01 — with the test file
read-only, or diffed separately and rejected if the test file itself changed unexpectedly).

**Regression test that would prevent recurrence:** an acceptance-layer test that fails a `cmd_check` if
the diff touches the file(s) the command itself reads as its oracle (a "did the test file change"
tripwire) — again a floor, not a full fix; full fix is isolation (RED3-01).

**Release blocking?** YES

---

### ID: RED3-04
**Severity:** P0
**Confidence:** PROVEN
**Area:** Budget / retry-storm exposure
**Title:** `budget_usd` is cosmetic under the shipped default adapter wiring — both default adapters report `cost_per_call_usd=0.0`, so the budget-exhausted check can never fire from real execution

**Claim-Invariant violated:** the product's cost-safety pitch is that `budget_usd` bounds a caller's
financial/compute exposure per delegated task.

**Observed behavior:** `CodexAdapter.cost_per_call_usd: float = 0.0` and `ReActAgent.cost_per_call_usd:
float = 0.0` are both defaults, and `chuzom/tools/agentic.py::_default_adapters()` — the function that
actually builds the adapters `llm_delegate()` uses — constructs both with no override:
`return {0: ReActAgent(tier=0), 1: CodexAdapter(tier=1)}`. `TaskLedger.charge(cost_usd)` does
`self.spent_usd += max(0.0, cost_usd)`, and `engine.py`'s only budget check is `ledger.budget_left() <= 0`
i.e. `budget_cap_usd - spent_usd <= 0`. If `spent_usd` never moves off `0.0`, this can never trip.

**Expected behavior:** `budget_usd=0.0001` should stop an impossible/miscalibrated task almost
immediately, as the tool's own docstring implies ("budget-aware" execution).

**Why this matters to a real user:** the *actual* brake on how much real work/spend a single delegated
call can trigger is the hardcoded structural ladder (tier count × `max_attempts_per_tier` × up to 2× flaky
non-deterministic-retry doubling in `engine.py::_run_and_verify`) — not the number the caller explicitly
passed believing it caps their exposure. Worse, `tools/agents.py::chuzom_agent_start_session` DOES clamp
`budget_usd` to `[0, profile.hard_max_usd]` for its own separate session subsystem — proving the codebase
has this capability and simply never applied it here; `tools/agentic.py`/`tools/consolidated.py::llm_act`
have no such clamp at all.

**Exact reproduction:** `evidence/red3/repro_budget_cap_is_cosmetic.py`. Scenario A: real
`delegate()`/`MGEEEngine`/`TaskLedger`, `AlwaysFailingAgent(cost_per_call_usd=0.0)` (matching production
defaults) at both tiers, `budget_cap_usd=$0.0001`. Scenario B: identical except
`cost_per_call_usd=$0.01`.

**Evidence (file:line, command, output):** `evidence/red3/repro_budget_cap_is_cosmetic.out`:
Scenario A — `outcome: Outcome.SURFACED`, `ledger.spent_usd: 0.0`, 4 total real `.run()` invocations (full
2-tier × 2-attempt ladder ran to exhaustion; budget never stopped anything). Scenario B — `outcome:
Outcome.BUDGET_EXHAUSTED`, `ledger.spent_usd: 0.01`, only 1 invocation before stopping.
- `src/chuzom/agentic/adapters.py`: `cost_per_call_usd: float = 0.0` (CodexAdapter default).
- `src/chuzom/agentic/react.py`: `cost_per_call_usd: float = 0.0` (ReActAgent default).
- `src/chuzom/tools/agentic.py`: `_default_adapters()`.
- `src/chuzom/agentic/ledger.py`: `charge()`/`budget_left()`.
- `src/chuzom/tools/agents.py` (grep-confirmed): `chuzom_agent_start_session` clamps `budget_usd` to
  `[0, profile.hard_max_usd]` — the contrasting case proving the capability exists elsewhere.

**Root cause:** cost accounting was made adapter-pluggable (reasonable design) but the two adapters that
ship as the actual defaults never opted into honest non-zero cost reporting, and nothing enforces that
they must.

**Why existing tests missed it:** adapter unit tests construct adapters directly and don't need to care
about their cost defaults; engine/ledger tests presumably inject non-zero costs (as any sane test would)
so they never exercise the "$0-cost adapter" combination that is, in fact, the production default.

**Blast radius:** every `llm_delegate`/`llm_act` call through the default (unconfigured) adapter path —
i.e., the entire product surface for agentic execution as shipped.

**Can this defect class exist elsewhere?:** yes — any place a "safety cap" parameter is plumbed through to
a mechanism (`charge()`) that depends on a *voluntary, unenforced* honesty contract from a pluggable
component is the same defect shape.

**Recommended systemic fix:** either (a) give `CodexAdapter`/`ReActAgent` realistic non-zero
`cost_per_call_usd` defaults reflecting actual subprocess/API cost, or (b) make the *structural* ladder
bound (tier count × k × flaky-doubling) the thing `budget_usd` is honestly documented as approximating,
or (c) add an independent, adapter-agnostic hard cap on total real invocations per delegated task that
does not depend on any adapter's self-reported cost.

**Regression test that would prevent recurrence:** a test that runs `_default_adapters()` (the actual
production factory, not a fake) against an always-failing milestone with `budget_cap_usd` set very low and
asserts the outcome is `BUDGET_EXHAUSTED`, not `SURFACED` after the full ladder — this test would fail
today and should be added as a documented-broken/xfail until fixed, then flipped once real cost accounting
lands.

**Release blocking?** YES

---

### ID: RED3-05
**Severity:** P1
**Confidence:** PROVEN
**Area:** Escalation ladder — replan
**Title:** Replanning is dead code in production — `service.run_delegation()` has no `replan_fn` parameter and never passes one, so a milestone that exhausts both tiers always goes straight to blocked/surfaced

**Claim-Invariant violated:** the ladder is documented/framed (orchestrator naming, `MGEEEngine`'s own
`if self.replan_fn and not ledger.replanned:` branch existing at all) as including a replan step between
tier exhaustion and giving up.

**Observed behavior:** `chuzom/agentic/service.py::run_delegation()`'s full signature is:
```python
def run_delegation(goal, milestones, adapters_by_tier, *, baseline_cost_per_milestone,
                    budget_cap_usd=1.0, max_attempts_per_tier=2, event_sink=None,
                    session_context="") -> dict[str, Any]:
```
— no `replan_fn` anywhere. It calls `delegate(...)` also without `replan_fn=`, whose own default is
`replan_fn=None`. `MGEEEngine._work_milestone()`'s replan branch is therefore provably unreachable via the
one production call chain (`tools/agentic.py::llm_delegate` → `run_delegation` → `delegate`).

**Expected behavior:** a milestone that fails at both tiers should get one replan attempt (per the
engine's own conditional guard `not ledger.replanned`, clearly designed for exactly one such attempt)
before being surfaced as blocked.

**Why this matters to a real user:** a milestone whose original plan was simply wrong (bad
decomposition, missing context, wrong check type) has no self-correction path — it goes straight to
"blocked," full stop, even though the engine was built with a mechanism for exactly this case.

**Exact reproduction:** static analysis (not requiring a runtime repro — the absence of a parameter in a
59-line file is directly verifiable by reading the source): `evidence/red3/` — see `service.py` excerpt
below; combined with `evidence/red3/repro_budget_cap_is_cosmetic.out`, which independently shows the full
ladder running to `SURFACED` with no replan step appearing anywhere in its behavior.

**Evidence (file:line, command, output):**
- `src/chuzom/agentic/service.py` (full 59-line file): `run_delegation()` signature, confirmed via direct
  Read, has no `replan_fn` parameter.
- `src/chuzom/agentic/engine.py`: `self.replan_fn = replan_fn` (constructor default `None`);
  `_work_milestone()`: `if self.replan_fn and not ledger.replanned: ... else: return "blocked"`.

**Root cause:** same class as RED3-01 — a documented engine capability whose wiring parameter was never
threaded through the one production service function that calls the engine.

**Why existing tests missed it:** engine-level tests presumably construct `MGEEEngine` directly and CAN
pass `replan_fn=`, proving the mechanism works in isolation — but never exercise
`chuzom.agentic.service.run_delegation` (the actual production entry) to notice it's unreachable there.

**Blast radius:** every delegated task where a milestone exhausts its ladder — no self-correction, ever,
in production, despite the mechanism existing and being unit-testable.

**Can this defect class exist elsewhere?:** yes — this is the second confirmed instance
(after RED3-01) of the same pattern: build a safety/quality mechanism, unit-test it against the engine
directly, never wire it through the actual production service function.

**Recommended systemic fix:** thread `replan_fn=` through `run_delegation()` → `tools/agentic.py`, backed
by a real re-planning call (e.g. re-invoking the hybrid planner with the failure context).

**Regression test that would prevent recurrence:** an end-to-end test on `chuzom.tools.agentic.llm_delegate`
itself (not `delegate()` directly) with a milestone engineered to fail both tiers and a spy `replan_fn`
injected via monkeypatch, asserting the spy is called before the milestone is marked blocked.

**Release blocking?** NO (this is a missing self-correction feature, not a false-positive-verification bug
— it fails toward "reports blocked," which is honest, not silently wrong) — but should be prioritized,
since two of three named engine safety features (gate, replan) are confirmed unreachable.

---

### ID: RED3-06
**Severity:** P1
**Confidence:** PROVEN
**Area:** Retry-storm exposure / planner output bounds
**Title:** No cap on the number of milestones a plan may contain in the default (non-bounded) delegation path

**Claim-Invariant violated:** implicit expectation that a single user-facing delegated task has some
predictable, bounded worst-case cost/attempt envelope.

**Observed behavior:** `chuzom/agentic/planner.py::plan_to_milestones()` accepts any number of
planner-proposed milestones, each independently validated for `id` + valid `acceptance`, with **no upper
bound on `len(plan)`**. `MAX_BOUNDED_MILESTONES=1` exists but only applies to the separate,
default-off, SIMPLE-task-only "bounded operational" path (`bounded_operational.py`, not the default
`llm_delegate`/`llm_act` path).

**Expected behavior:** some documented, enforced ceiling on plan size for the default path, since it
directly multiplies worst-case real invocations (`num_milestones × tiers × k_attempts × up_to_2x_flaky`).

**Why this matters to a real user:** combined with RED3-04 (budget cosmetic under default adapters), a
poorly-scoped or adversarially-verbose goal string can cause the planner to emit an arbitrarily large
milestone list, each one independently burning its full structural ladder, with no budget check able to
intervene and no milestone-count ceiling to intervene either.

**Exact reproduction:** static analysis of `planner.py::plan_to_milestones()` (full 119-line file read) —
confirmed no length check against `plan` exists anywhere in the function body.

**Evidence (file:line, command, output):** `src/chuzom/agentic/planner.py`, `plan_to_milestones()` —
iterates and validates each item's `id`/`acceptance`, no `len(plan) > N` check; contrast with
`src/chuzom/bounded_operational.py`'s separate, opt-in `MAX_BOUNDED_MILESTONES=1` for a different code
path entirely.

**Root cause:** the milestone-count bound was implemented for one execution mode (bounded/simple) and
never generalized to the default mode.

**Why existing tests missed it:** planner unit tests likely test individual milestone validation
(id/acceptance shape), not aggregate plan-size limits, since no such limit was ever specified for this path.

**Blast radius:** the entire default `llm_delegate`/`llm_act` surface — any caller-supplied goal that
induces the planner to over-decompose.

**Can this defect class exist elsewhere?:** yes — any place validation is written per-item without also
validating the collection.

**Recommended systemic fix:** cap `len(plan)` in `plan_to_milestones()` for all paths (a generous but
finite number, e.g. 20), independent of the separate `MAX_BOUNDED_MILESTONES` mechanism, and reject/replan
if the planner proposes more.

**Regression test that would prevent recurrence:** a test asserting `plan_to_milestones()` raises
`PlanRejected` (or equivalent) when given a synthetic plan of, say, 500 trivially-valid milestone dicts.

**Release blocking?** NO — compounds RED3-04's severity but is not independently a false-positive bug;
should be fixed alongside RED3-04.

---

### ID: RED3-07
**Severity:** P1
**Confidence:** PROVEN
**Area:** Context propagation between milestones
**Title:** `pack_prompt()` never forwards a completed milestone's artifacts (diff/output/files) to later milestones — only its planner-authored, pre-execution description — so execution-time-decided facts do not survive into dependent milestones

**Claim-Invariant violated:** the "ALREADY COMPLETED — build on these, do NOT redo" framing in the
prompt implies the executor has enough information about prior work to build on it correctly.

**Observed behavior:** `TaskLedger.freeze()` stores each completed milestone's full `artifacts` dict, and
`TaskLedger.frozen_context()` (ledger.py) correctly includes `artifacts` per frozen milestone. But
`chuzom/agentic/adapters.py::pack_prompt()` — the single function both `CodexAdapter.run()` and
`ReActAgent.run()` use to render frozen context into the actual text sent to an executor — renders only:
```python
f"  - [{c.get('id')}] {c.get('description') or c.get('id')}"
```
per completed milestone. `c.get('artifacts')` is never read by `pack_prompt()`.

**Expected behavior:** a later milestone whose task genuinely depends on a fact only knowable after an
earlier milestone executed (e.g., an exact symbol/variable/file name an earlier executor chose among
several equally valid options — something the planner, writing the description *before* execution, cannot
possibly have specified) should have some prompt-level path to learn that fact.

**Why this matters to a real user:** any multi-milestone plan with this shape (extremely common —
"create X" then "wire X into Y" is a natural two-step decomposition) has the later milestone's executor
guessing at a fact it was never given, with no reliable recovery path (CodexAdapter's `cwd=None` — see
RED3-08 — means it often cannot even re-read the repo to rediscover the fact itself; ReAct's tier-0 agent
can in principle use its `read_file` tool, but only if it thinks to and only if `cwd` happens to be
correct).

**Exact reproduction:** `evidence/red3/repro_context_propagation_artifacts_lost.py`. Milestone 1
("create-settings-module") frozen via the real `ledger.freeze()` with artifacts whose diff names the
symbol `SETTINGS`. Milestone 3 ("wire-settings-into-main")'s description references milestone 1's output
generically (as a planner necessarily would, having written it before milestone 1 executed). Calls the
real `ledger.frozen_context()` and real `pack_prompt()`.

**Evidence (file:line, command, output):** `evidence/red3/repro_context_propagation_artifacts_lost.out`:
`completed_entry["artifacts"]["diff"]` contains `"SETTINGS"` (ledger has the fact: `artifacts keys
present: ['provider', 'output', 'diff', 'files']`); the actual rendered prompt for milestone 3 —
```
ALREADY COMPLETED — build on these, do NOT redo:
  - [create-settings-module] Create a settings module exposing the app's configuration as a dict.
```
— does not contain `"SETTINGS"` anywhere. Both script assertions passed.

**Root cause:** `pack_prompt()` was written to keep prompts short (a reasonable goal) but dropped the one
field (`artifacts`) that carries forward concrete, execution-time-discovered facts, with no fallback (e.g.
a truncated diff excerpt, or the `output` summary string) for cases where the fact matters.

**Why existing tests missed it:** `pack_prompt()` unit tests presumably check that completed-milestone IDs
and descriptions appear in the output — they would pass whether or not artifacts are included, since that
was never asserted as required.

**Blast radius:** every multi-milestone plan with a genuine "the exact name of thing 1 is used by thing
2" dependency — plausibly the majority of decompositions with more than one milestone, since planners
naturally split "build X" from "use X."

**Can this defect class exist elsewhere?:** yes — this is a specific instance of the audit's general
"context propagation" concern (mandate item 4); any place a data structure retains information that a
downstream renderer silently drops is the same shape.

**Recommended systemic fix:** include at least a bounded excerpt of `artifacts.get("diff")` and/or
`artifacts.get("output")` per completed milestone in `pack_prompt()`, truncated to a reasonable length,
rather than description-only.

**Regression test that would prevent recurrence:** a test asserting `pack_prompt()`'s output contains a
distinguishing substring present only in a completed milestone's `artifacts["output"]` (not its
`description`) — this test would fail today and should be added as documented-broken until fixed.

**Release blocking?** NO — this degrades correctness on genuinely dependent multi-milestone plans (a
real, common failure mode) but does not itself make a check falsely report PASS; it's a silent
information-loss bug that increases the *rate* at which RED3-02/03-style false-positive verifications
occur on multi-step plans, which is why it's still P1 rather than P2.

---

### ID: RED3-08
**Severity:** P1
**Confidence:** PROVEN
**Area:** Acceptance checks — `diff_check` availability / cwd wiring
**Title:** `diff_check` is structurally unusable via the production default Codex adapter — `cwd` is never set, so diff/file artifacts are unconditionally empty regardless of what the executor actually did on disk

**Claim-Invariant violated:** `diff_check` is presented in the planner's own prompt template as a
first-class, valid, objective acceptance-check type.

**Observed behavior:** `chuzom/tools/agentic.py::_default_adapters()` constructs `CodexAdapter(tier=1)`
with no `cwd=` argument anywhere in the production call chain. `CodexAdapter.run()`'s diff-capture block
is gated `if self.capture_diff and self.cwd:` — with `cwd=None`, this is always `False`, so
`artifacts["diff"]` and `artifacts["files"]` are unconditionally `""`/`[]`, regardless of what the
underlying `codex` CLI subprocess actually changed on disk.

**Expected behavior:** the adapter should capture the real diff of whatever the Codex CLI actually did, so
`diff_check`-type acceptance criteria can be evaluated against real changes.

**Why this matters to a real user:** every milestone plan using `{"type": "diff", ...}` acceptance —
explicitly documented as valid — is unconditionally unsatisfiable in production, regardless of whether the
underlying work was correct or not. This silently forces all real delegated work through the weaker
`canary`/`cmd` check types (RED3-02/RED3-03's structural weaknesses), removing what should be the
*strongest* available objective check from actual use. Separately (not independently reproduced but
directly implied by the same `cwd=None`): the Codex CLI subprocess itself never receives a `-C <dir>` flag
(`_codex_argv()` only adds `-C` when `self.cwd` is truthy), so nothing pins the executor's actual working
directory to the user's repository — it inherits whatever the MCP server process's ambient OS cwd happens
to be.

**Exact reproduction:** `evidence/red3/repro_diff_check_broken_without_cwd.py`. `CodexAdapter(tier=1,
runner=fake_runner)` — `cwd` left at its production default, `None`. `fake_runner` simulates Codex
reporting success AND a real, non-empty `git diff` (i.e., work that *did* happen and *would* be visible if
asked in the right directory).

**Evidence (file:line, command, output):** `evidence/red3/repro_diff_check_broken_without_cwd.out`:
`adapter.cwd: None`, `artifacts['diff']: ''`, `artifacts['files']: []`,
`artifacts['output']: 'Applied patch to auth.py successfully.'` — the adapter never even attempts to
shell out to `git diff` because the guard condition short-circuits on `cwd=None`.
- `src/chuzom/agentic/adapters.py`: `_codex_argv()`'s `if self.cwd: argv += ["-C", self.cwd]`; `run()`'s
  `if self.capture_diff and self.cwd:` diff-capture guard.
- `src/chuzom/tools/agentic.py`: `_default_adapters()`.

**Root cause:** `cwd` is a required piece of context (both for correct subprocess execution location and
for diff capture) that was made optional/pluggable at the adapter level but never actually supplied by the
one production factory that builds these adapters.

**Why existing tests missed it:** adapter tests presumably construct `CodexAdapter(cwd=some_tmpdir, ...)`
explicitly (a reasonable thing to do in a test), so they never exercise the `cwd=None` production default.

**Blast radius:** every real (non-fake-agent) `llm_delegate`/`llm_act` call using the Codex tier, for
`diff_check`-type acceptance specifically, plus the broader (unproven-but-implied) working-directory
ambiguity for all Codex-tier work regardless of check type.

**Can this defect class exist elsewhere?:** yes, this is the third confirmed instance of "wiring gap
between a documented capability and the one production factory that constructs it" (after RED3-01's gate
and RED3-05's replan).

**Recommended systemic fix:** `_default_adapters()` must accept and pass a real working directory (the
user's actual repo root, presumably available to the MCP server process) to both `CodexAdapter(cwd=...)`
and `ReActAgent`'s tool executor.

**Regression test that would prevent recurrence:** a test on the actual `_default_adapters()` factory
output asserting `adapters[1].cwd is not None` (or equivalent), which would fail today.

**Release blocking?** NO by itself — this fails *closed* (the check simply can't pass, rather than falsely
passing), which is the safer failure direction. It is flagged P1 rather than P0 because its real damage is
indirect: it silently forces 100% of real delegated work onto the weaker, more gameable check types
(RED3-02/RED3-03), compounding those P0 findings' blast radius rather than being a false-positive bug on
its own.

---

### ID: RED3-09
**Severity:** P0
**Confidence:** PROVEN
**Area:** Unverified completions — non-agentic completion surface
**Title:** The entire plain-completion tool surface (`llm_query`/`llm_analyze`/`llm_code`/`llm_research`/`llm_generate`, and their `llm()` alias) has zero synchronous quality verification; the only "judge" mechanism is fire-and-forget, silently-failing, and affects only *future* routing — never the response the user already received

**Claim-Invariant violated:** mandate item 7's framing, and the product's general "quality feedback"
narrative (`quality_feedback.py`, `judge.py`, `scorer.py`, `gates.py` all exist and imply some verification
layer sits between model output and the user).

**Observed behavior:** `chuzom/tools/text.py` (941 lines — the actual implementation behind
`llm_query`/`llm_analyze`/`llm_code`/`llm_research`/`llm_generate`, and transitively `llm()` in
`consolidated.py`) has no import of and no call into `judge.py`, `judge_cascade.py`, `scorer.py`,
`gates.py`, or `response_validation.py` anywhere (confirmed by grep across the full file — the only
"gate"/"contract"/"verify" hits are an unrelated hook-complexity-hint cache check and a static
"UNVERIFIED — not web-grounded" disclosure banner appended to research output, not an actual verification
mechanism). The *only* quality-signal code that ever runs on a live request's response is in
`chuzom/cost.py` lines 1257-1274:
```python
# Fire-and-forget judge evaluation for successful calls with response
if success and response:
    try:
        from chuzom.judge import evaluate_response_async
        ...
        await evaluate_response_async(prompt=prompt, response=response,
                                       task_type=task_type, routing_decision_id=routing_decision_id)
    except Exception:
        pass  # Silent failure — judge is optional enhancement
```
This runs as part of logging the routing decision — after the response is already being returned to the
caller — is wrapped in a bare `except Exception: pass`, and even when it succeeds, its only effect is to
write a `judge_score` onto the `routing_decisions` row, which `model_selector.py` later reads as a
*rolling average over the past 3 days* to influence which model gets picked for *future* calls
("Hard threshold enforcement: if rolling judge score < 0.6 for 5+ calls" — `model_selector.py` line 78).
It never touches, flags, retries, or corrects the specific response already delivered to the current user.

**Expected behavior:** at minimum, some documented, honestly-scoped signal to the *current* caller about
whether their specific answer was checked at all — even a "not verified" banner (which research output
does get, but query/analyze/code/generate do not).

**Why this matters to a real user:** `llm_delegate`/`llm_act` — the path with (weak, gameable) objective
checks — is one narrow slice of Chuzom's tool surface. Every other completion tool (which, per the tool
surface's own naming as the "front door," is presumably the majority of real call volume) has strictly
weaker guarantees than the delegation path: not "gameable objective checks" but "no check at all,
ever, on the response you're looking at." A user cannot tell, from the response alone, that this is the
case — nothing in `llm_query`'s returned text discloses "this was not verified."

**Exact reproduction:** static analysis — `grep -niE "judge|scorer|gate|accept|verif|contract"
src/chuzom/tools/text.py` (941 lines, full file in scope) plus an AST-based import scan
(`ast.walk` over every non-test `.py` file under `src/chuzom`) confirming `chuzom.judge` is imported only
by `model_selector.py`, `cost.py`, and `tools/admin.py` — none of which sit between a completion request
and its response in `tools/text.py`. Read `cost.py` lines 1245-1276 directly for the fire-and-forget/
silent-failure evidence quoted above.

**Evidence (file:line, command, output):**
- `src/chuzom/tools/text.py` (941 lines): no import of `judge`/`judge_cascade`/`scorer`/`gates`/
  `response_validation`.
- `src/chuzom/cost.py:1257-1274`: fire-and-forget, silent-failure judge call, quoted above.
- `src/chuzom/model_selector.py:78,89-90`: judge score used only for future-routing threshold logic
  (`get_judge_scores_for_model`, rolling 3-day average).
- AST import scan (executed via `.venv-audit/bin/python -c "..."`): only `model_selector.py`, `cost.py`,
  `tools/admin.py` import `chuzom.judge` in production; `tools/text.py` and `tools/agentic.py` do not.

**Root cause:** quality evaluation was built as a *routing-optimization signal* (feed judge scores back
into future model selection) rather than as a *per-response verification gate*, and no separate,
synchronous, response-blocking verification layer exists for the non-agentic completion surface at all.

**Why existing tests missed it:** `judge.py`'s own tests presumably test `evaluate_response_async` in
isolation (does it score correctly, given a prompt/response pair) — they would not catch that its call
site treats it as non-blocking/optional/silently-failable, because that's a property of the *caller*
(`cost.py`), not of `judge.py` itself.

**Blast radius:** the entire non-agentic completion surface — by tool-count and (presumably, though not
independently measured here) by call-volume, this is most of Chuzom.

**Can this defect class exist elsewhere?:** this is arguably the *general case* that RED3-01 through
RED3-08 are specific instances of within the narrower `llm_delegate` path — "a quality mechanism exists in
the codebase but doesn't gate what the user actually receives."

**Recommended systemic fix:** either (a) honestly document that `llm_query`/`llm_analyze`/`llm_code`/
`llm_research`/`llm_generate` carry no per-response verification (extend the existing "UNVERIFIED — not
web-grounded" banner pattern already used for research output to the others, or a general "not
independently verified" disclosure), or (b) add an optional synchronous verification tier for callers who
need it (analogous to `llm_delegate`'s acceptance checks, but for text/analysis output — e.g. a
self-consistency or judge-gated retry before returning).

**Regression test that would prevent recurrence:** N/A as a "regression" test per se, since this is a
missing-feature/missing-disclosure finding rather than a broken-existing-behavior one; the actionable test
is a *documentation* assertion (a test that greps public tool docstrings for a verification-status
disclosure) if fix (a) is adopted, or an integration test asserting a blocking judge call before response
return if fix (b) is adopted.

**Release blocking?** YES — not because the current behavior is a regression, but because it means the
audit's central question ("how much should a user trust a DONE/VERIFIED task") has a much worse answer for
the majority of the tool surface than the `llm_delegate` findings alone would suggest, and nothing today
discloses that gap to the user.

---

### ID: RED3-10
**Severity:** P2
**Confidence:** PROVEN
**Area:** Dead code / unused security control
**Title:** `response_validation.py` — the module whose own docstring claims it "prevent[s] code injection or malicious payload processing" from external LLM responses — has zero production importers

**Claim-Invariant violated:** a named, mandate-listed security-relevant module should be reachable from
the code paths it claims to protect.

**Observed behavior:** repo-wide grep for `response_validation` finds exactly one match outside the module
itself: `tests/test_response_validation.py`. No production file imports it.

**Expected behavior:** if `LLMResponse` (a strict pydantic schema with length/type validation) is meant to
validate responses from external LLM providers, something in the provider/adapter/router call path should
construct and validate against it.

**Why this matters to a real user:** whatever protection this module is meant to provide against malformed
or malicious provider responses is not actually applied to any real response in production today.

**Exact reproduction:** `grep -rln "response_validation" . --include="*.py"` at the repo root → only
`tests/test_response_validation.py`.

**Evidence (file:line, command, output):**
- `src/chuzom/response_validation.py:1-4`: `"""Response validation for external LLM APIs. Validates
  responses from external LLM providers to ensure they match expected schemas and prevent code injection
  or malicious payload processing."""`
- grep confirming zero non-test importers.

**Root cause:** module built, unit-tested against itself, never integrated into any live call site.

**Why existing tests missed it:** `test_response_validation.py` tests the module's own validation logic in
isolation — it has no way to notice the module is never invoked by production code, since that's outside
its own scope.

**Blast radius:** whatever the module was meant to protect against (malformed/malicious external provider
responses) is currently unprotected, repo-wide.

**Can this defect class exist elsewhere?:** yes — fourth confirmed instance of "built + unit-tested in
isolation, never wired into production" (after RED3-01 gate, RED3-05 replan, RED3-08 cwd/diff capture).

**Recommended systemic fix:** either wire `LLMResponse` validation into the actual provider response
path (`router.py` or wherever raw provider responses are first parsed), or remove the module and its
implied claim if it's genuinely superseded by something else.

**Regression test that would prevent recurrence:** an import-graph test (or the same AST-import-scan
technique used for RED3-09) asserting every module under `src/chuzom` whose docstring claims to "validate"
or "sanitize" external input has at least one production (non-test) importer.

**Release blocking?** NO — this is a defense-in-depth gap, not demonstrated to be exploited by anything
observed in this audit's scope; flagged for completeness per the mandate's explicit file list.

---

## Mandate item 3 — planner/executor shared blind spot (self-graded homework)

**Confidence: STRONG EVIDENCE** (not a fresh, separately-reproduced end-to-end scenario — built on
RED3-02/RED3-03's already-executed reproductions plus static analysis of `planner.py`).

`planner.py`'s defenses against a trivially-easy planner-chosen check (`_TRIVIAL_CMD_HEADS`,
`_GENERIC_MARKERS`, `_reject_if_trivial()`) are **entirely syntactic**: they reject checks whose *command
text* matches a denylist of trivial patterns (e.g. bare `echo`, `true`) or whose acceptance criteria use
generic placeholder-looking symbol names. They do not — and structurally cannot, without executing
candidate solutions — verify that a check's *pass condition is semantically equivalent to the milestone's
actual requirement*. RED3-02 and RED3-03 are direct proof that a check can pass every syntactic triviality
filter (a real file, a real symbol name, a real test command with a nontrivial name) while still being
satisfiable by work that does not meet the requirement. Since the planner and the tier-0 executor both
draw from the same general pool of models (the same underlying "cheapest capable" routing philosophy
applies to both roles), there is no independent, harder-to-fool party checking the planner's work — the
question "is this acceptance check actually equivalent to the task?" is never asked by anything in the
pipeline. This directly answers the mandate's question: **self-graded homework is not trustworthy here**,
and the syntactic triviality filter creates a false sense of rigor (it *looks* like anti-gaming protection,
but only catches the laziest, most obvious gaming attempts — "assert True" style triviality — not the
substantive gaming RED3-02/03 demonstrate).

## Mandate item 5 — escalation ladder against the 16 named failure types

**Confidence: PARTIAL / mostly NOT TESTED** — stated honestly per the mandate's explicit prohibition on
converting suspicion into fact.

What is PROVEN from direct source reading (`engine.py`, full file, read twice across this audit):
`MGEEEngine`'s retry/escalation logic (`_work_milestone`/`_run_and_verify`) does **not distinguish failure
type at all**. Every outcome funnels through a uniform `AgentRunResult` with `.ok`/`.deterministic`
booleans; a task that is *impossible* (wrong requirement, capability ceiling) is retried identically (same
k attempts, same tier-escalation path) to a task that failed from a *transient* cause (timeout, rate
limit) — there is no differentiated backoff, no "this looks like a transient infra failure, not a
capability failure" branch anywhere in the engine. This means: for any of the 16 named failure types that
manifest as `AgentRunResult(ok=False, ...)` at the adapter boundary, the engine's response is identical —
retry same tier up to k, then escalate tier, then (dead-code, RED3-05) attempt replan, then surface. The
engine itself provides no mechanism to recognize "this failure type means retrying is pointless" (e.g. an
invalid-credentials failure will burn through the exact same structural ladder as a genuinely-fixable
transient timeout).

What is confirmed at the *adapter* boundary (not the engine): `CodexAdapter`'s subprocess runner
(`adapters.py`) catches `FileNotFoundError` and `subprocess.TimeoutExpired` and translates them into a
failed `ProcResult` rather than propagating a raw exception; `ReActAgent`'s tool-executor
(`react.py:149`) catches `Exception` broadly per-tool-call ("a tool error is returned to the model, never
fatal") so a single tool failure doesn't crash the whole milestone attempt; `react.py:237` similarly
surfaces failure to the model rather than fabricating a fake successful answer. `router.py` (2600+ lines,
not fully read in this audit — explicitly flagged as NOT TESTED below) has its own, entirely separate
provider-fallback/rate-limit (`_extract_retry_after`) machinery for the non-agentic completion path, which
this audit did not trace in depth.

**Explicitly NOT TESTED (per-type), stated honestly rather than guessed:** malformed response handling,
empty response handling, context-window error handling, health-rejection handling, and the exact
propagation/surfacing behavior of each of the 16 named types through to what a user actually sees (event
log detail vs. opaque "blocked") were not individually constructed and reproduced in this audit segment,
due to time/effort constraints after prioritizing items 2, 4, 6, and 7. This is a real gap in this audit's
coverage, not a claim that these are fine.

## Mandate item 6 — retry storm ceiling

**Confidence: PROVEN** for the structural (adapter-agnostic) ladder math; **STRONG EVIDENCE, not fully
traced,** for the `router.py`-level fallback chain that sits above/alongside it for the non-agentic path.

Per delegated task, per milestone, the production default path's worst case is:
`tiers (2) × max_attempts_per_tier (k=2, hardcoded in tools/agentic.py::llm_delegate) × up to 2×
(flaky/non-deterministic-result re-run doubling in engine.py::_run_and_verify)` = **up to 8 real backend
invocations per milestone**, multiplied by an **unbounded milestone count** (RED3-06), multiplied by
**zero effective budget enforcement under default adapters** (RED3-04). There is no global, adapter-agnostic
hard ceiling on total real invocations for a single `llm_delegate`/`llm_act` call. `router.py`'s separate
fallback-chain logic for the non-agentic completion path (confirmed to exist via grep: `fallback_chain`,
"primary + emergency fallback chains", rate-limit `Retry-After` extraction) was not fully read in this
audit and its own worst-case multiplier is **NOT TESTED** — flagged as a gap, not asserted to be fine or
broken.

## Mandate item 7 — unverified completions, quantified

Covered in depth by RED3-09 above. Restated as a direct quantification: of the tool surface examined in
this audit —
- `llm_delegate`/`llm_act` (agentic): has objective acceptance checks, but they are individually gameable
  (RED3-02, RED3-03), the two engine-level safety mechanisms are unreachable (RED3-01, RED3-05), and the
  strongest check type (`diff_check`) is structurally broken (RED3-08) — so even the "verified" path's
  verification is weak.
- `llm_query`/`llm_analyze`/`llm_code`/`llm_research`/`llm_generate`/`llm` (non-agentic, the rest of the
  tool surface): **zero synchronous quality verification of any kind** on the response the user receives
  (RED3-09). The only quality signal (`judge.py`'s `evaluate_response_async`) is fire-and-forget,
  silent-failure, and affects only future routing statistics.

---

## Ranked findings summary

| ID | Severity | Confidence | Title |
|---|---|---|---|
| RED3-01 | P0 | PROVEN | Reversibility gate unreachable — irreversible milestones run unisolated |
| RED3-02 | P0 | PROVEN | `diff_check` symbol-substring gaming — security-hole stub verified DONE |
| RED3-03 | P0 | PROVEN | `cmd_check` test-tampering — executor rewrites the oracle it's graded on |
| RED3-04 | P0 | PROVEN | `budget_usd` cosmetic under default adapters — real brake is undocumented hardcoded ladder |
| RED3-09 | P0 | PROVEN | Non-agentic completion surface has zero per-response verification, undisclosed |
| RED3-05 | P1 | PROVEN | Replan is dead code in production |
| RED3-06 | P1 | PROVEN | No cap on planner-generated milestone count |
| RED3-07 | P1 | PROVEN | `pack_prompt()` drops artifacts — cross-milestone dependencies don't survive |
| RED3-08 | P1 | PROVEN | `diff_check` structurally unusable (cwd never wired to Codex adapter) |
| RED3-10 | P2 | PROVEN | `response_validation.py` is dead code |
| (item 3) | — | STRONG EVIDENCE | Planner's anti-gaming filter is syntactic-only; self-graded homework confirmed untrustworthy via RED3-02/03 |
| (item 5) | — | PARTIAL / mostly NOT TESTED | Escalation ladder doesn't differentiate failure type at engine level; per-type behavior for most of the 16 named types not individually reproduced |
| (item 6) | — | PROVEN (structural) / NOT TESTED (router.py fallback layer) | Up to 8 invocations/milestone × unbounded milestones × no effective budget stop |

All ten numbered findings are backed by an executed, asserting reproduction script or direct, quoted
source evidence — none are speculative. Confidence is PROVEN throughout because each was independently
verified against the real, unmodified `AUDIT-c2c2882` source with only injected test-seam callables
(never the mechanism under test) faked.
