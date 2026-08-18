# RED-8 — Formal Findings (RED8-NN template)

Auditor: RED-8 (adversarial zero-tolerance architectural audit)
Target: worktree `AUDIT-c2c2882`, tag v1.1.1, SHA `c2c28821f690f7cbda42b46da06fc36ef77d816e` (clean, detached HEAD)
Interpreter: `<WORKTREE>/.venv-audit/bin/python` 3.11.15 exclusively
Supporting evidence: `03_ARCHITECTURE_MAP.md`, `13_HISTORICAL_DEFECT_PATTERNS.md`, `ARCHITECTURE_RISK_MAP.md`, `evidence/red8/*`

---

### RED8-01

Severity: **P0** / Confidence: **PROVEN** / Area: Savings/cost reporting (`dashboard_data.py`)

Title: `dashboard_data.py::query_window()` recomputes savings from a stale, hardcoded $15/$75 Opus rate that a sibling file's identical bug was already fixed and named as an invariant violation

Claim-Invariant violated: `INV-COST-004` ("one canonical price source") — named and referenced in-tree (`cost.py`, `tools/dashboard.py`, `digest.py`, `retrospective.py`, `execution_ledger.py`) but not enforced.

Observed behavior: `src/chuzom/dashboard_data.py` lines 182-183 and again at lines 286-287 define local constants `_OPUS_IN_PER_M = 15.0`, `_OPUS_OUT_PER_M = 75.0` and use them to compute `opus_baseline` and `saved` inside `query_window()`'s two aggregation blocks. Neither block imports `cost.py`'s canonical `_OPUS_PRICING`/`_HOST_INPUT_PER_M`/`_HOST_OUTPUT_PER_M`.

Expected behavior: matches what commit `d03b4d7` (2026-07-26, "fix(dashboard): canonical host price + drop stale $15/$75 3x-inflated baseline (AC-3, AC-4) (#169)") explicitly established as the fix for the *identical* bug in the sibling file `tools/dashboard.py`: read the current price from `cost.py` at call time, never hardcode.

Why this matters to a real user: every "amount saved by routing" figure derived through `query_window()` — surfaced in session-end summaries, the TUI dashboard, the statusline HUD, `chuzom gain`, `chuzom explain-dashboard`, `chuzom replay`, and team/quota reports — is inflated by ~3x for any call whose actual baseline should be priced at the corrected $5/$25 Opus rate. A user or team making a budget/ROI decision from these numbers is working from a figure this audit can prove is wrong by a known, reproducible factor.

Exact reproduction:
```
cd <WORKTREE> && .venv-audit/bin/python -c "
from chuzom import cost
print('cost.py canonical opus:', cost._OPUS_PRICING[cost.LATEST_OPUS_MODEL])
print('dashboard_data.py hardcoded: (15.0, 75.0)  # see lines 182-183, 286-287')
in_tok, out_tok = 3000, 1200
stale = (in_tok*15.0 + out_tok*75.0)/1_000_000
correct = (in_tok*cost._OPUS_PRICING[cost.LATEST_OPUS_MODEL][0] + out_tok*cost._OPUS_PRICING[cost.LATEST_OPUS_MODEL][1])/1_000_000
print(f'stale opus_baseline=\${stale:.6f} correct=\${correct:.6f} inflation={stale/correct:.3f}x')
"
```
Expected output: inflation factor ≈ 3.000x, matching the exact factor `d03b4d7`'s commit message and `cost.py`'s own `_OPUS_PRICING` docstring both describe.

Evidence (file:line): `src/chuzom/dashboard_data.py:182-183,198-199,286-287,306-307`; contrast fix at `src/chuzom/tools/dashboard.py:43-46,93-105` (commit `d03b4d7d3d7b13a7dd720f87ea35ef1b6fe1bc15`); `cost.py::_OPUS_PRICING["claude-opus-4-8"] = (5.0, 25.0)`.

Root cause: no mechanically-enforced single source of truth for host/baseline pricing; "canonical" is a documentation convention other modules are trusted, not required, to import from. `dashboard_data.py` predates the fix (introduced at the Tessera→Chuzom rebrand, commit `cd70fd5`) and was never in scope for `d03b4d7`, which only touched the one file that had an open incident report against it.

Why existing tests missed it: `tests/test_dashboard.py`'s new assertion from `d03b4d7` (`test_host_baseline_tracks_canonical_price`) is scoped to `tools/dashboard.py::_host_baseline` only; it does not assert anything about `dashboard_data.py`. No test anywhere asserts cross-module price-table equality.

Blast radius: ~26-28 downstream consumer files (confirmed via `grep -rl "saved_usd" src/`): `hooks/session-end.py`, `dashboard/tui.py`, `dashboard/server.py`, `statusline_hud.py`, `commands/gain.py`, `commands/explain_dashboard.py`, `commands/replay.py`, `commands/team.py`, `team.py`, `quota_savings.py`, `routing_quality.py`, `routing_report.py`, `onboard.py`, `test_delta.py`, `session_spend.py`, `ui/session_summary.py`, `ui/status_premium.py`, `tools/subscription.py`, `tools/admin.py`, `tools/text.py`, `tools/routing.py`, `tui/app.py`, `agentic/service.py`, `agentic/savings.py`, `agentic/telemetry.py`, `hooks/cc-usage-track.py`, `hooks/status-bar.py` — essentially the entire user-facing savings-reporting surface.

Can this defect class exist elsewhere?: Yes — proven, see RED8-02 and RED8-03 (the same class recurs within `cost.py` itself and in `calibration.py`/`o3` pricing). This is not a single isolated miss; it is the dominant recurring incident shape in the project's git history (154 "savings" + 51 "stale" + 43 "drift" commit hits).

Recommended systemic fix: collapse all per-model $/1M pricing literals into one module (`chuzom.pricing` or extend `cost.py` to be the sole holder) with every consumer importing it; add a CI lint (mirroring `scripts/lint_tool_surface.py`) that fails the build on any hardcoded `$/1M`-shaped float literal outside that one module; extend `scripts/trace_northstar.py`-style live tracing to assert that two different savings-computation call sites for the same synthetic event produce the same number.

Regression test that would prevent recurrence: a repo-wide test that imports every module under `src/chuzom/` and asserts no module-level float constant matching known stale price signatures (15.0/75.0, 15.0/60.0, etc.) exists outside the canonical pricing module; plus a property test that feeds identical (task_type, complexity, input_tokens, output_tokens) into every "compute savings" entry point (`cost.calc_savings`, `dashboard_data.query_window`, `receipt_store.compute_receipt`, `savings_logger`) and asserts they agree within a defined tolerance.

Release blocking? **YES**

---

### RED8-02

Severity: **P0** / Confidence: **PROVEN** / Area: Cost/savings computation (`cost.py`, `router.py` hot path)

Title: `cost.py::BASELINE_PRICING["opus"]` is stale ($15/$75) in the same file where `_OPUS_PRICING` was corrected ($5/$25), and it feeds `router.py`'s live accepted-attempt ledger write

Claim-Invariant violated: `INV-COST-004`.

Observed behavior: `cost.py` contains two Opus price tables. `_OPUS_PRICING["claude-opus-4-8"] = (5.0, 25.0)` is documented as canonical and corrected. `BASELINE_PRICING["opus"] = {"input": 15.0, "output": 75.0}`, in the *same file*, was not updated. `router.py`'s accepted-attempt code path (lines ~2687-2716, duplicated again at ~2960-2995) calls `cost._get_baseline_for_task(task_type, complexity)` → for `research`/`complex` tasks this selects `"opus"` → `cost._get_baseline_cost()` prices it via the stale `BASELINE_PRICING` table, and the resulting `_baseline_equivalent_cost_usd` is written into the execution ledger via `_emit_ledger_attempt`.

Expected behavior: a single canonical Opus price table, used everywhere, matching `_OPUS_PRICING`.

Why this matters to a real user: every accepted research/complex-task routing event's ledger-recorded savings is inflated ~3x, live, on the primary hot path of the product (router.py is the #1 file by both LOC, 4967, and churn, 79 commits).

Exact reproduction:
```
.venv-audit/bin/python -c "
from chuzom import cost
print('BASELINE_PRICING[opus]:', cost.BASELINE_PRICING['opus'])
print('_OPUS_PRICING[claude-opus-4-8]:', cost._OPUS_PRICING['claude-opus-4-8'])
baseline_model = cost._get_baseline_for_task('research', 'complex')
print('baseline model chosen:', baseline_model)
stale = cost._get_baseline_cost(3000, 1200, baseline_model)
print('reported baseline_equivalent_cost_usd (stale path): \${:.6f}'.format(stale))
correct = (3000*5.0 + 1200*25.0)/1_000_000
print('correct: \${:.6f}  inflation={:.3f}x'.format(correct, stale/correct))
"
```
Output confirmed this audit: `stale=$0.135000`, `correct=$0.045000`, `inflation=3.000x`.

Evidence (file:line): `src/chuzom/cost.py::BASELINE_PRICING["opus"]` vs `cost.py::_OPUS_PRICING["claude-opus-4-8"]`; `router.py:2687-2716` (`_baseline_equivalent_cost_usd = cost._get_baseline_cost(...)` inside a `try/except Exception: _baseline_equivalent_cost_usd = None` fail-open block), duplicated at `router.py:~2960-2995`.

Root cause: same as RED8-01 — no enforced single source of truth; here the drift is *within a single file*, proving the problem is not merely "which file to import from" but that even the file positioned as canonical was not internally reconciled.

Why existing tests missed it: `tests/test_savings.py`'s only assertion touching `BASELINE_PRICING` checks key presence (`"haiku" in BASELINE_PRICING`), not value correctness or cross-table equality against `_OPUS_PRICING`.

Blast radius: every accepted research/complex-task routing event, persisted permanently to the execution ledger, consumed by the same ~26-28-file fan-out as RED8-01 plus `router.py` itself.

Can this defect class exist elsewhere?: Yes — proven at RED8-01 and RED8-03; also note `cost.py::CLAUDE_RATES_PER_M["opus"] = 15.00/75.00` is a third stale copy within the same file (used for Claude Code billing-match purposes, not verified whether it feeds user-facing savings, flagged for follow-up).

Recommended systemic fix: delete `BASELINE_PRICING` and `CLAUDE_RATES_PER_M`'s independent Opus entries; derive both from `_OPUS_PRICING` at import time (a single dict comprehension), so a future price correction to `_OPUS_PRICING` cannot leave a sibling constant behind.

Regression test that would prevent recurrence: `assert cost.BASELINE_PRICING["opus"] == {"input": cost._OPUS_PRICING[cost.LATEST_OPUS_MODEL][0], "output": cost._OPUS_PRICING[cost.LATEST_OPUS_MODEL][1]}` — trivial to write, currently absent.

Release blocking? **YES**

---

### RED8-03

Severity: **P1** / Confidence: **PROVEN** / Area: Cost computation (`cost.py`, `calibration.py`)

Title: OpenAI o3 pricing ($15/$60) is stale in two of three sibling tables, contradicting `savings_logger.py`'s own comment claiming the value was already "repriced" on 2026-07-10

Claim-Invariant violated: `INV-COST-004` (same class as RED8-01/02, different model).

Observed behavior: `hooks/savings_logger.py:72` — `("openai", "o3"): (2.00, 8.00), # repriced from stale $15/$60`. Live at HEAD: `cost.py:1387` — `"o3": {"input": 15.00, "output": 60.00, ...}` (unchanged); `calibration.py:97` — `"o3": {"input": 15.0, "output": 60.0}` (unchanged).

Expected behavior: all three o3 price tables agree, matching whichever value is currently correct.

Why this matters to a real user: any savings computation for OpenAI o3 delegations that flows through `cost.py::OPENAI_RATES_PER_M` or `calibration.py::_PRICING_PER_M` (rather than `savings_logger.py`) uses a rate 7.5x/7.5x too high on input and output respectively (15/2 = 7.5x, 60/8 = 7.5x), producing a large savings overstatement for o3-routed complex tasks.

Exact reproduction:
```
.venv-audit/bin/python -c "
from chuzom import cost, calibration
print('cost.py o3:', cost.OPENAI_RATES_PER_M['o3'])
print('calibration.py o3:', calibration._PRICING_PER_M['o3'])
"
```
Confirmed this audit: both report `{'input': 15.0, 'output': 60.0}` (or equivalent), while `savings_logger.py` uses `(2.00, 8.00)`.

Evidence (file:line): `src/chuzom/cost.py:1387`; `src/chuzom/calibration.py:97`; `src/chuzom/hooks/savings_logger.py:54-57,72`.

Root cause: same systemic gap as RED8-01/02 — `calibration.py` explicitly documents a *deliberate* choice not to import `cost.py` ("Kept local... so this module stays free of cross-module dependencies and remains pure"), trading correctness-under-drift for import-graph purity with no compensating check.

Why existing tests missed it: no cross-table equality test exists for any provider's pricing, o3 included.

Blast radius: any code path pricing OpenAI o3 delegations via `cost.py` or `calibration.py` rather than `savings_logger.py` — narrower than RED8-01/02 (o3 usage volume presumably smaller than Opus) but demonstrates the defect class generalizes across providers, not just Anthropic models.

Can this defect class exist elsewhere?: Yes, and plausibly does — `calibration.py::_PRICING_PER_M["o3-mini"]` and the Gemini rate tables were flagged but not exhaustively cross-checked this pass (see `ARCHITECTURE_RISK_MAP.md` §5, Pending).

Recommended systemic fix: same as RED8-01/02 — one canonical multi-provider pricing module, CI-enforced.

Regression test that would prevent recurrence: parametrized test iterating every (provider, model) key present in any of `cost.OPENAI_RATES_PER_M`, `calibration._PRICING_PER_M`, `savings_logger._PRICING_PER_MTOK` and asserting the three agree wherever the same key exists in more than one table.

Release blocking? **NO** (narrower blast radius than RED8-01/02; recommend fixing in the same PR as those, not blocking independently)

---

### RED8-04

Severity: **P2** / Confidence: **PROVEN** / Area: Cost computation (`calibration.py`)

Title: `calibration.py::_PRICING_PER_M` prices the same physical Haiku model at two different rates (3.2x apart) depending on whether the caller uses the bare alias or the dated snapshot name, and a fourth, still-different Haiku rate exists in `savings_logger.py`

Claim-Invariant violated: `INV-COST-004`; also an implicit "one model, one price" assumption nowhere stated but clearly intended.

Observed behavior: within the same dict, `"claude-haiku-4-5"` → `{"input": 0.25, "output": 1.25}` and `"claude-haiku-4-5-20251001"` → `{"input": 0.80, "output": 4.0}`. `_normalize_model_name()` strips only a `provider/` prefix, not the dated-vs-bare distinction, so both keys remain independently reachable depending on caller input. `savings_logger.py::_PRICING_PER_MTOK[("claude","claude-haiku-4-5")] = (1.00, 5.00)` — a fourth value matching neither of the two `calibration.py` entries nor any value found in `cost.py`.

Expected behavior: one price per physical model, with alias resolution normalizing to a single canonical key before lookup.

Why this matters to a real user: whether a Haiku-routed call is reported as cheap or "still fairly cheap" depends on which of four hardcoded tables happened to compute the figure and whether the caller passed the bare or dated model string — an internally inconsistent product surface, independent of which value is actually correct.

Exact reproduction:
```
.venv-audit/bin/python -c "
from chuzom import calibration
print('bare:', calibration._PRICING_PER_M['claude-haiku-4-5'])
print('dated:', calibration._PRICING_PER_M['claude-haiku-4-5-20251001'])
"
```

Evidence (file:line): `src/chuzom/calibration.py` (`_PRICING_PER_M` dict, haiku entries); `src/chuzom/hooks/savings_logger.py` (`_PRICING_PER_MTOK[("claude","claude-haiku-4-5")]`).

Root cause: no canonical alias-resolution layer for model names shared across the pricing tables; each table's author independently decided which literal string keys to support.

Why existing tests missed it: no test asserts alias/dated-name price equivalence.

Blast radius: any Haiku-routed savings computation through `calibration.py` or `savings_logger.py`; narrower than RED8-01/02 but demonstrates the underlying architectural defect (unenforced duplication) generalizes to alias-resolution correctness, not just staleness.

Can this defect class exist elsewhere?: Likely — any other model family with both a bare and dated snapshot name (Sonnet, GPT, Gemini variants) is a plausible candidate; not exhaustively checked this pass.

Recommended systemic fix: canonicalize model names to one form before any pricing lookup, at the same layer as the pricing-table consolidation recommended in RED8-01/02/03.

Regression test that would prevent recurrence: for each known alias/dated-name pair, assert identical price lookup result.

Release blocking? **NO**

---

### RED8-05

Severity: **P1** / Confidence: **PROVEN** / Area: Router hot path / savings accounting architecture (`router.py`, `receipt_store.py`, `execution_ledger.py`)

Title: `router.py` computes and persists two structurally different, unreconciled "savings" numbers for the identical accepted response event

Claim-Invariant violated: implicit — no invariant currently states "the ledger and the receipt store must agree for the same event," but the absence of one is itself the defect.

Observed behavior: for a single accepted routed response, `router.py` (lines ~2687-2716, duplicated at ~2960-2995) calls (1) `cost._get_baseline_for_task(task_type, complexity)` → `cost._get_baseline_cost(...)`, a policy where the baseline model *varies* by task type (haiku for query, opus for research/complex, sonnet otherwise; partly stale per RED8-02) feeding `_emit_ledger_attempt(baseline_equivalent_cost_usd=...)` → the execution ledger; then (2) `receipt_store.compute_receipt(...)`, a policy that is *unconditionally Opus* (hardcoded $5/$25, correct value) regardless of task type, feeding `~/.chuzom/receipts.db`. For a query task, ledger uses a haiku baseline while the receipt uses an Opus baseline — a structural disagreement by design, not drift. For a research/complex task, both nominally target Opus, but the ledger figure is additionally 3x-inflated per RED8-02.

Expected behavior: one baseline-selection policy, one savings figure per event, or an explicit, documented reason the two stores intentionally measure different things — currently neither exists; no code path reconciles or even cross-logs a discrepancy.

Why this matters to a real user: `hooks/session-start.py` and `hooks/session-end.py` both read `receipts.db`, while the dashboard/TUI/statusline surfaces (RED8-01's ~26-file fan-out) read the execution ledger via `dashboard_data.py`. A user comparing the session-start/end receipt summary against the dashboard is comparing two numbers computed by different policies for the same underlying events, with no visible indication they are not the same metric.

Exact reproduction: static — read `router.py:2687-2716` and `receipt_store.py:70-93` side by side; confirm both are invoked in the same function body for the same `response` object, no `if`/branch separates them.

Evidence (file:line): `src/chuzom/router.py:2687-2716` (`from chuzom.receipt_store import compute_receipt, store_receipt` at line 64; both `cost._get_baseline_cost` and `compute_receipt` called in the same code block); `src/chuzom/receipt_store.py:70-93` (`compute_receipt`, always-Opus); `src/chuzom/cost.py::_get_baseline_for_task` (task-varying).

Root cause: the ledger and receipt-store subsystems were built by different work-streams (ledger = routing-quality measurement per NORTH_STAR.md step 7; receipts = "Contract-as-Infrastructure," v8.8.0, silent audit trail) without a shared savings-computation contract between them.

Why existing tests missed it: no test asserts ledger/receipt agreement for a shared synthetic event; each subsystem is tested in isolation.

Blast radius: every accepted routed response — both persisted stores, and every downstream reader of either (session-start/end summaries, dashboard/TUI, `chuzom gain`, etc.).

Can this defect class exist elsewhere?: Yes — this is the same "duplicated source of truth" root cause as RED8-01 through RED8-04, applied to *policy* (which baseline model to choose) rather than just *pricing* (what that model costs).

Recommended systemic fix: designate one subsystem as the source of the baseline-selection policy (`cost._get_baseline_for_task` is more expressive; recommend `receipt_store.compute_receipt` call into it rather than hardcoding Opus) so both stores agree by construction; alternatively, explicitly document why they intentionally diverge and label both surfaces accordingly in the UI.

Regression test that would prevent recurrence: a synthetic-event integration test that feeds one `(task_type, complexity, input_tokens, output_tokens)` tuple through both `_emit_ledger_attempt`'s baseline computation and `receipt_store.compute_receipt`, asserting the two `baseline_equivalent_cost_usd`/`opus_equivalent_cost` figures match (or, if divergence is intentional, that the divergence is bounded/documented and surfaced).

Release blocking? **NO** (architecturally significant but no single reproduction shows a released feature displaying an outright-wrong absolute number beyond what RED8-01/02 already cover; recommend fixing alongside those)

---

### RED8-06

Severity: **P2** / Confidence: **STRONG EVIDENCE** / Area: Prompt classification / tool routing (`hooks/auto-route.py`, `hooks/agent-route.py`, `service.py`)

Title: Three independently-implemented prompt classifiers feed three independently-maintained task_type→tool mapping dicts, with two different default fallback tools for an unrecognized task type

Claim-Invariant violated: no named invariant exists for classifier/mapping consistency (a gap in itself, given `tool_surface.py` demonstrates the team knows how to build a single source of truth for adjacent logic).

Observed behavior: `hooks/auto-route.py::TOOL_MAP` (8 keys) fed by a sophisticated multi-stage `classify_prompt()` (fast-path pattern match → heuristic scoring → Ollama/cheap-API escalation), default fallback `llm_route`. `hooks/agent-route.py::_TOOL_MAP` (5 keys) fed by a single-pass regex signal scorer `_classify_task_type()`, default fallback `llm_analyze`. `service.py`'s inline dict (5 keys) fed by a third independent heuristic `_heuristic_classify()` in a sidecar FastAPI `/classify` endpoint, default fallback `llm_route`. The HTTP client that would call this sidecar (`hook_client.classify_prompt`) has zero importers anywhere in `src/`, so the third classifier/mapping pair is architecturally present but appears functionally orphaned relative to the live hook chain.

Expected behavior: one classifier (or a documented, tested reason for more than one), and mapping consistency such that any task type recognized by one is recognized identically by all live consumers.

Why this matters to a real user: an ambiguous prompt can be classified as tool-needing by `auto-route.py` but default to a no-tools completion door (`llm_analyze`) by `agent-route.py`'s cruder scorer — exactly the failure mode NORTH_STAR.md's own anti-goals list names first ("Enforcing a completion tool on a task that needs to run tools — a structural dead-end").

Exact reproduction: static review — compare `hooks/auto-route.py:1731-1739` (`TOOL_MAP`) against `hooks/agent-route.py:215-220` (`_TOOL_MAP`) and `service.py:~199-208`; no shared test drives an identical prompt through all three and compares output.

Evidence (file:line): `src/chuzom/hooks/auto-route.py:1731-1739`; `src/chuzom/hooks/agent-route.py:215-220`; `src/chuzom/service.py:~199-208`; orphan check: `grep -rln "hook_client.classify_prompt" src/` → empty.

Root cause: classification logic grew independently in the push-hook path (user prompts), the agent-step path (subagent routing), and the sidecar service path (originally, presumably, for a different integration surface), without a shared classification module.

Why existing tests missed it: no cross-classifier consistency test exists; each classifier's own unit tests (where present) test it in isolation against its own expected mapping.

Blast radius: every user prompt (auto-route.py) and every Agent-tool subagent step (agent-route.py) — high-frequency, though the specific defect (disagreement) only manifests on ambiguous/edge-case prompts, not all traffic.

Can this defect class exist elsewhere?: This is the classification-side analog of the pricing-table duplication (RED8-01 through -04) — same root architectural pattern (multiple hand-maintained copies of logic that should be one), different subsystem.

Recommended systemic fix: extract one shared `classify_prompt(text) -> (task_type, complexity, needs_tools)` function importable by all three call sites (auto-route.py's is the most sophisticated and is the natural candidate), and one shared task_type→tool map (ideally sourced from `tool_surface.py`'s existing tier registry rather than a fourth new module). Remove or explicitly justify the orphaned `service.py`/`hook_client.classify_prompt` path.

Regression test that would prevent recurrence: parametrized test feeding a fixed prompt corpus through all three classifiers and asserting identical task_type output (or an explicit, tested allowlist of intentional differences).

Release blocking? **NO**

---

### RED8-07

Severity: **P1** / Confidence: **PROVEN** / Area: Process/engineering governance — the gap between CHZ-SURF-01 (fixed systemically) and the pricing-table family (fixed locally, repeatedly)

Title: `INV-COST-004`, the invariant the team itself named after the `d03b4d7` incident, was never converted into an enforceable check — unlike the directly comparable CHZ-SURF-01 tool-name-resolution incident, which received a permanent CI lint and a live trace script

Claim-Invariant violated: `INV-COST-004` itself — this finding is about the invariant's non-enforcement, i.e., a meta-finding about why RED8-01 through RED8-05 were possible/inevitable.

Observed behavior: `grep -rl "INV-COST-004" src/` returns exactly 5 files (`digest.py`, `retrospective.py`, `cost.py`, `execution_ledger.py`, `tools/dashboard.py`) — the files whose authors happened to reference the prior incident. It does not appear in `dashboard_data.py`, `receipt_store.py`, `savings_logger.py`, or `calibration.py`, the four files proven in RED8-01/02/03/04 to still violate it. No CI job or lint script analogous to `scripts/lint_tool_surface.py` greps for hardcoded per-M pricing literals.

Expected behavior: matching the CHZ-SURF-01 playbook — a stdlib-only or otherwise universally-importable single pricing module, a CI lint that fails the build on any hardcoded pricing literal outside it, and a live-trace script analogous to `scripts/trace_northstar.py` that verifies actual computed savings agree across subsystems.

Why this matters to a real user: this is the structural reason RED8-01 through RED8-05 exist and will recur again for the next model/provider price change — the team has already proven, in this exact repository, that it knows how to prevent this class of defect (CHZ-SURF-01's fix), and chose not to apply that pattern to money math.

Exact reproduction:
```
grep -rl "INV-COST-004" <WORKTREE>/src/chuzom/
grep -rl "lint_tool_surface\|trace_northstar" <WORKTREE>/scripts/
# compare: no equivalent "lint_pricing" or "trace_pricing" script exists
```

Evidence (file:line): `src/chuzom/tool_surface.py` (CHZ-SURF-01 fix, positive contrast), `scripts/lint_tool_surface.py`, `scripts/trace_northstar.py` vs. the absence of equivalents for pricing; commit `d03b4d7`'s message naming `INV-COST-004` without a corresponding enforcement commit.

Root cause: `tool_surface.py` was made stdlib-only specifically so hooks running under interpreters without the `chuzom` package installed could still import it — an external constraint that forced consolidation. No equivalent forcing constraint exists for pricing; `calibration.py` explicitly documents choosing import-graph purity over importing `cost.py`.

Why existing tests missed it: this is itself the answer to "why existing tests missed RED8-01 through -05" — there is no process, not just no individual test, that would have caught them.

Blast radius: the entire cost/savings-reporting subsystem, indefinitely into the future (every future price change is a new opportunity for the same defect class), not just the currently-live instances enumerated in RED8-01 through -04.

Can this defect class exist elsewhere?: This finding IS the "elsewhere" — it explains why RED8-01 through -06 all share one root cause and predicts the next occurrence.

Recommended systemic fix: (1) create one canonical pricing module; (2) add a CI lint modeled directly on `scripts/lint_tool_surface.py`; (3) add a live cross-subsystem savings-agreement trace modeled on `scripts/trace_northstar.py`; (4) do this as one PR that also fixes RED8-01 through -05, since they share a single root cause and a single fix.

Regression test that would prevent recurrence: the CI lint itself, plus the cross-subsystem agreement test named in RED8-01/02/05.

Release blocking? **YES** (as the root-cause finding underlying two P0s)

---

### RED8-08

Severity: **P1** / Confidence: **PROVEN** / Area: North Star coherence — model-capability leaderboard

Title: The "continuously-updated," "live" external model leaderboard that NORTH_STAR.md states routing capability decisions are read from is, in the actual runtime implementation, a static bundled JSON snapshot regenerated only by a manual/CI-triggered offline script, over 4 months stale at audit time, with no runtime staleness check or user-facing warning

Claim-Invariant violated: NORTH_STAR.md's own anti-goal #5 ("claims a guarantee that isn't measured"), applied reflexively to the document's own leaderboard-liveness claim.

Observed behavior: `Docs/planning/NORTH_STAR.md` states (verbatim): *"It is read from a continuously-updated external ranking: https://artificialanalysis.ai/leaderboards/models... Pinning 'Claude = top' is a North-Star violation the moment another model leads."* The actual implementation, `src/chuzom/benchmark_fetcher.py`, states in its own module docstring: *"Offline benchmark data fetcher — runs in GitHub Actions, never at runtime... This module requires the `scripts` optional dependency group."* It sources from Arena Hard Auto, Aider Edit Leaderboard, HuggingFace Open LLM Leaderboard v2, and LiteLLM's pricing dict — not a direct runtime fetch of artificialanalysis.ai. The bundled `src/chuzom/data/benchmarks.json` at HEAD reports `"generated_at": "2026-03-30T15:30:35Z"`.

Expected behavior: either the routing capability ranking is actually fetched live/near-live at runtime (or on a short, automatic cadence with a visible staleness indicator), or the document's language should not claim "continuously-updated" and "live" in the present tense.

Why this matters to a real user: a user reading NORTH_STAR.md (or any user-facing copy derived from it) reasonably concludes that if a new frontier model overtakes Claude on the referenced leaderboard, Chuzom's escalation ladder reflects that "the moment" it happens. In reality, the ranking Chuzom actually consults can lag reality by months with no indication to the user that it might be stale.

Exact reproduction:
```
.venv-audit/bin/python -c "
import json, pathlib
p = pathlib.Path('<WORKTREE>/src/chuzom/data/benchmarks.json')
d = json.loads(p.read_text())
print('generated_at:', d.get('generated_at'))
"
grep -n "stale" <WORKTREE>/src/chuzom/model_registry.py   # zero hits
```

Evidence (file:line): `Docs/planning/NORTH_STAR.md:16-27`; `src/chuzom/benchmark_fetcher.py:1-20` (module docstring); `src/chuzom/data/benchmarks.json` (`generated_at` field); `src/chuzom/model_registry.py` (no "stale" hits).

Root cause: a genuinely live fetch of an external leaderboard at runtime is a reasonable engineering tradeoff to avoid (latency, availability, rate limits) — but the decision to make it offline/CI-only was not reflected back into the North Star document's language, leaving an aspirational statement presented as current behavior.

Why existing tests missed it: this is a documentation/behavior coherence gap, not a code-correctness bug in the traditional sense — no test type in the current suite is designed to catch "does the document's claim match the implementation's actual data-freshness contract."

Blast radius: every routing decision that depends on the capability tier ordering (`model_registry.py`, `dynamic_routing.py`-style consumers) is silently working from up-to-4-months-old capability data; also a trust/credibility risk if a user or reviewer discovers the gap between documented and actual behavior independently.

Can this defect class exist elsewhere?: Plausibly — any other "live"/"continuously" claim in user-facing docs should be checked against its actual implementation; not exhaustively done for documents other than NORTH_STAR.md this pass.

Recommended systemic fix: either (a) implement an actual periodic/live refresh with a visible "last updated" surface and a staleness threshold that degrades gracefully (e.g., warns rather than silently using year-old data), or (b) rewrite NORTH_STAR.md's language to accurately describe the offline/periodic-refresh model it actually implements, removing "continuously-updated" and "live."

Regression test that would prevent recurrence: a CI check that fails the build if `data/benchmarks.json`'s `generated_at` is older than a defined threshold (e.g., 60 days) relative to release date.

Release blocking? **NO** (documentation/behavior-coherence gap, not a runtime correctness bug — but high-priority given it undermines the project's own stated core principle)

---

### RED8-09

Severity: **P2** / Confidence: **STRONG EVIDENCE** / Area: Structural hazards — error handling posture

Title: 810 bare `except Exception:` catches repo-wide, ~234 of them immediately fail-open (`= None`/`return None`/`pass`), making it structurally impossible to distinguish deliberate, justified fail-open behavior from silently-swallowed correctness errors

Claim-Invariant violated: none named explicitly in-repo; this is a general software-hygiene finding, included because it directly enabled/masks RED8-01 through RED8-05 (e.g., `router.py`'s `except Exception: _baseline_equivalent_cost_usd = None` and `hook_client.classify_prompt`'s silent-`None`-on-HTTP-error).

Observed behavior: `grep -rc "except Exception" src/` sums to 810 occurrences; a conservative pattern match for the line immediately following being `= None`, `return None`, or `pass` finds ~234 (undercount — multi-line handlers not matched).

Expected behavior: narrower exception handling scoped to the specific error condition being defended against, with fail-open behavior reserved for genuinely optional/non-critical paths and logged (not silent) so operators can detect when it fires.

Why this matters to a real user: at this base rate, no reviewer can audit which of the ~800+ catches are "must never break the routed turn" (defensible, as router.py's own comment states for its case) versus "swallowing a bug that should have surfaced." `hook_client.classify_prompt()` returning `None` on any HTTP error to the sidecar is a concrete example of this ambiguity — the hook falls through un-classified with no visible signal, indistinguishable from a case where classification simply wasn't needed.

Exact reproduction:
```
grep -rc "except Exception" <WORKTREE>/src | awk -F: '{sum+=$2} END{print sum}'
```

Evidence (file:line): repo-wide grep count; specific examples at `src/chuzom/router.py` (baseline-cost computation, documented fail-open), `src/chuzom/hook_client.py` (`classify_prompt`, silent-None-on-error).

Root cause: no repo-wide exception-handling policy or lint rule restricting bare `except Exception:` usage or requiring a log statement / metric increment on every fail-open branch.

Why existing tests missed it: tests generally exercise the happy path; fail-open branches by design don't raise, so they don't fail tests either — they just silently produce degraded/wrong output, which is exactly the shape of defect this audit's mandate item 4 was looking for.

Blast radius: repo-wide; magnitude of harm varies per instance from "genuinely fine" to "silently swallows a correctness signal" — not resolved at the aggregate-count level, requires per-instance triage.

Can this defect class exist elsewhere?: This IS the "elsewhere" — it is the general-purpose mechanism by which many other defects (including some of RED8-01 through -05) can remain invisible in production (no exception surfaces, no log line, no metric).

Recommended systemic fix: adopt a lint rule (e.g., via `ruff` custom rule or a repo script) requiring every bare `except Exception:` to either re-raise, log at a minimum WARNING level, or carry an inline comment justifying the specific fail-open decision (a convention already followed in a minority of instances, e.g., router.py's "Fail-open: ... must never break the routed turn" comment — good practice not yet made mandatory).

Regression test that would prevent recurrence: a lint/CI check enumerating all bare `except Exception:` blocks and failing on any without an adjacent justification comment or log call.

Release blocking? **NO**

---

### RED8-10

Severity: **P3** / Confidence: **SUSPICION** / Area: Structural hazards — configuration sprawl

Title: 186 distinct environment variable names read across `src/`, with no central schema/registry analogous to `tool_surface.py`'s tier registry

Claim-Invariant violated: none named; flagged as a structural risk, not a proven live defect.

Observed behavior: `evidence/red8/envvars.txt` enumerates 186 distinct env var names read anywhere under `src/`. No single module documents or validates the full set; several were confirmed individually during this audit (`CHUZOM_SLIM`, `CHUZOM_SAVINGS_BASELINE`, `CHUZOM_CLAUDE_SUBSCRIPTION`, `CHUZOM_AGENT_ROUTE_ALLOW`, `CHUZOM_AGENTIC_MODEL`, `CHUZOM_ENFORCE`) but the full set was not exhaustively cross-checked for undocumented or conflicting semantics given time budget.

Expected behavior: a central config schema (even a simple registry module) that enumerates every supported env var, its type, default, and owning subsystem — reducing the risk of silent typos, undocumented flags, or two subsystems reading the same-shaped variable name with different assumptions.

Why this matters to a real user: config sprawl at this scale increases the risk of silent misconfiguration (a typo'd env var name simply does nothing, with no validation error) and makes it hard for an operator or auditor to know the full behavioral surface controllable at runtime.

Exact reproduction: `grep -rhoE "os\.(environ|getenv)\(['\"][A-Z_]+" <WORKTREE>/src | sort -u | wc -l` → 186 (raw list in `evidence/red8/envvars.txt`).

Evidence (file:line): `evidence/red8/envvars.txt`.

Root cause: organic growth — env vars added ad hoc per feature without a central registry requirement, unlike `tool_surface.py`'s deliberate single-registry design for tool names.

Why existing tests missed it: not the kind of defect a functional test would catch; this is a maintainability/observability gap, not a runtime correctness bug (no live misbehavior proven this pass).

Blast radius: unknown/unbounded — could not be sized without the full manual pass this audit did not complete.

Can this defect class exist elsewhere?: This is itself a general instance of "no enforced single source of truth," continuing the pattern from RED8-01 through -07, applied to configuration rather than pricing or classification.

Recommended systemic fix: build a central env-var registry/schema module (even a simple dataclass or dict of name→spec) that all subsystems declare into, with a CI check that no `os.environ`/`os.getenv` call anywhere references a name not present in the registry.

Regression test that would prevent recurrence: the CI check described above.

Release blocking? **NO** (not proven as a live defect this pass — genuinely SUSPICION-level confidence, included for completeness per mandate item 4, not as a release blocker)

---

## Summary table

| ID | Severity | Confidence | Area | Release blocking |
|---|---|---|---|---|
| RED8-01 | P0 | PROVEN | dashboard_data.py stale $15/$75, ~26-file blast radius | YES |
| RED8-02 | P0 | PROVEN | cost.py BASELINE_PRICING internal drift, router.py hot path | YES |
| RED8-03 | P1 | PROVEN | o3 pricing stale in 2 of 3 tables | NO |
| RED8-04 | P2 | PROVEN | Haiku 4-way internal price self-contradiction | NO |
| RED8-05 | P1 | PROVEN | Two unreconciled savings numbers per event (ledger vs receipt) | NO |
| RED8-06 | P2 | STRONG EVIDENCE | Triplicated classifier/tool-map, divergent fallbacks | NO |
| RED8-07 | P1 | PROVEN | INV-COST-004 never made enforceable (root-cause finding) | YES |
| RED8-08 | P1 | PROVEN | North Star leaderboard not actually live (4+ months stale) | NO |
| RED8-09 | P2 | STRONG EVIDENCE | 810 broad excepts / ~234 fail-open | NO |
| RED8-10 | P3 | SUSPICION | 186 env vars, no central registry | NO |
