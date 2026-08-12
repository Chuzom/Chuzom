# RED-8 — Historical Defect Pattern Mining

Auditor: RED-8 (adversarial architectural audit)
Target: worktree `AUDIT-c2c2882`, tag v1.1.1, SHA `c2c28821f690f7cbda42b46da06fc36ef77d816e` (clean, detached HEAD)
Interpreter: `<WORKTREE>/.venv-audit/bin/python` 3.11.15 exclusively
Method: `git log --all --grep` keyword sweep + targeted `git show`/`git log -p` on incident commits, cross-referenced against live source at HEAD.

## 0. Sweep counts (evidence: `evidence/red8/historical_keyword_counts.txt`)

| keyword | commits | keyword | commits |
|---|---|---|---|
| routing | 285 | fallback | 98 |
| savings | 154 | bypass | 41 |
| regression | 125 | drift | 43 |
| silent | 65 | stale | 51 |
| locked | 65 | race | 37 |
| fabricat | 26 | wrong | 25 |
| double-count | 9 | mislead | 7 |
| denominator | 4 | `fix(` total | 236 |

The volume of `routing`/`savings`/`fallback`/`stale`/`drift` commits (285/154/98/51/43) is itself a signal: the savings/routing-accounting subsystem has been in a state of continuous, incident-driven local patching for the project's lifetime, not a small number of one-off bugs.

## 1. The anchor incident: "$15/$75 stale Opus baseline, ~3x inflated savings"

This exact defect class recurs **at least four separate times** in git history as an explicitly-named, explicitly-fixed incident, and is independently rediscovered under different names/IDs each time — strong evidence the fixes were LOCAL (one file at a time) rather than SYSTEMIC (one canonical source enforced everywhere):

| Commit | Date | File(s) touched | What it claims to fix |
|---|---|---|---|
| `2f0b730` | fix(cost): calc_savings honors the task-aware baseline, not hardcoded Opus (AC-7, INV-COST-004) | cost.py | Opus-only baseline hardcode in `calc_savings` |
| `50043e5` | fix(digest): price the baseline from cost.py's canonical host rate, not a hardcoded 15/75 (AC-4) | digest.py | independent `15/75` copy in digest.py |
| `d03b4d7` | 2026-07-26 | **`fix(dashboard): canonical host price + drop stale $15/$75 3x-inflated baseline (AC-3, AC-4) (#169)`** | `src/chuzom/tools/dashboard.py`, `tests/test_dashboard.py` only | independent `HOST_INPUT_PER_M/HOST_OUTPUT_PER_M = 15/75` copy in `tools/dashboard.py` |
| cost.py `_OPUS_PRICING` docstring | (in-tree, undated in git-blame terms but present at HEAD) | cost.py | states "the old $15/$75 was stale... Every historical `saved_usd` was therefore ~3x inflated" |
| `hooks/savings_logger.py` comment | "Updated 2026-07-10... the prior table (opus $15/$75, o3 $15/$60) was badly stale and INFLATED reported savings on complex tasks by ~3x" | savings_logger.py | independent `_PRICING_PER_MTOK` copy |

**`d03b4d7`'s own commit message is the single best piece of self-diagnosis in the repository.** Quoting it directly:

> "tools/dashboard.py hardcoded HOST_INPUT_PER_M/HOST_OUTPUT_PER_M = 15/75 (Opus 4.6) — ~3x the current $5/$25 list price (AC-3 inflation) and **an independent copy of the host rate (AC-4)**... One canonical price source (INV-COST-004)."

The team correctly identified the *architectural* defect ("an independent copy of the host rate") and named an invariant to prevent recurrence (`INV-COST-004`). But the fix was scoped to the one file that triggered the incident report (`tools/dashboard.py`), verified by one new unit test pinned to that one function (`test_host_baseline_tracks_canonical_price`), and `INV-COST-004` was never turned into a repo-wide lint/CI check.

**Consequence, confirmed live at HEAD by direct code execution (not grep) in the mandated `.venv-audit` interpreter:**

```
BASELINE_PRICING['opus']            = {'input': 15.0, 'output': 75.0}   # STILL STALE
_OPUS_PRICING['claude-opus-4-8']    = (5.0, 25.0)                        # corrected
baseline model for research/complex = "opus"
_get_baseline_cost(3000, 1200, "opus")  → $0.135000   (via stale BASELINE_PRICING)
correct cost via _OPUS_PRICING          → $0.045000
inflation factor: 3.000x
```

and, separately, `src/chuzom/dashboard_data.py` (a *sibling* of the fixed `tools/dashboard.py`, never touched by `d03b4d7`) hardcodes the identical `_OPUS_IN_PER_M = 15.0` / `_OPUS_OUT_PER_M = 75.0` **twice**, at lines 182–183 and 286–287, inside `query_window()` — the core aggregation function that `saved_usd` figures across ~28 downstream consumer files (session-end.py, dashboard/tui.py, statusline_hud.py, commands/gain.py, commands/explain_dashboard.py, commands/replay.py, team.py, quota_savings.py, routing_quality.py, etc.) ultimately derive from.

**Answering the five required sub-questions for this incident:**

- **(a) Architectural property that allowed it:** no single canonical pricing source is *mechanically enforced*; "canonical" is a documentation convention (`cost._HOST_INPUT_PER_M`/`_OPUS_PRICING`) that other modules are trusted, but not required, to import. At least 6 modules instead hold their own hand-maintained numeric copy with a comment promising to "keep in sync."
- **(b) Local or systemic fix:** **Local**, every time. Each of the 4+ incidents above fixed one file. None added a lint rule, a cross-module consistency test, or refactored the duplicate copies to import from `cost.py`.
- **(c) Can the same defect class recur elsewhere:** **Yes — and it already has**, provably, in `dashboard_data.py` (never fixed) and in `cost.py`'s own `BASELINE_PRICING` dict (fixed in the sibling `_OPUS_PRICING` table, not in `BASELINE_PRICING` itself, in the *same file*, by the *same commit's author's own later work*).
- **(d) Did the regression test check the architecture or one example:** **One example.** `test_host_baseline_tracks_canonical_price` (added in `d03b4d7`) asserts that `tools/dashboard.py::_host_baseline` derives from `cost.py`'s canonical constants. It does not assert that *no other module* hardcodes an Opus/haiku/sonnet rate, and `tests/test_savings.py`'s only assertion touching `BASELINE_PRICING` checks key-presence only (`"haiku" in BASELINE_PRICING`), not value-correctness or cross-table equality.
- **(e) Sibling implementations that still have the flaw:** `src/chuzom/dashboard_data.py` (both `query_window` and a second aggregation block, lines 182-183 & 286-287 — stale, unfixed); `src/chuzom/cost.py::BASELINE_PRICING["opus"]` (stale, unfixed, live on router.py's hot ledger path); `src/chuzom/calibration.py::_PRICING_PER_M["claude-opus-4-6"]` (stale, unfixed).

## 2. The o3 sibling incident (same class, different model)

`hooks/savings_logger.py` line 72: `("openai", "o3"): (2.00, 8.00), # repriced from stale $15/$60`, with a header comment dated "Updated 2026-07-10." This claims the $15/$60 o3 rate was already fixed.

**Live at HEAD, unfixed:**
- `cost.py` line 1387: `"o3": {"input": 15.00, "output": 60.00, "cache_read": 3.75, "cache_write": 18.75}`
- `calibration.py` line 97: `"o3": {"input": 15.0, "output": 60.0}`

Both siblings still contain the exact value savings_logger.py's own comment calls "stale." This is the identical defect-recurrence pattern as §1, independently confirmed for a second model family — evidence this is a *pattern*, not an isolated slip.

## 3. `INV-COST-004` — a named invariant that was never made enforceable

`grep -rl "INV-COST-004" src/` finds exactly 5 files: `digest.py`, `retrospective.py`, `cost.py`, `execution_ledger.py`, `tools/dashboard.py`. It does **not** appear in `dashboard_data.py`, `receipt_store.py`, `savings_logger.py`, or `calibration.py` — the four files that independently hardcode Opus/haiku/o3 pricing today. The invariant exists as a *comment convention* referenced only by the files whose authors happened to be aware of the prior incident when they wrote them; there is no CI/lint job (analogous to `scripts/lint_tool_surface.py` for tool names — see below) that greps for hardcoded per-M pricing literals and fails the build.

**Contrast with the CHZ-SURF-01 fix (tool-name resolution):** that incident *did* produce a systemic fix — `chuzom.tool_surface` as a single mandatory import point, plus `scripts/lint_tool_surface.py` (CI lint) and `scripts/trace_northstar.py` (end-to-end trace against the live MCP server). The pricing-table incidents never received the equivalent treatment: no `chuzom.pricing` single-source module, no `scripts/lint_pricing_literals.py`. The team has already demonstrated, in-repo, that it knows how to fix this defect *class* systemically — it just didn't apply that playbook to money math, only to tool names.

## 4. Two structurally different "what would Opus/baseline have cost" policies coexist unreconciled

- `cost.py::_get_baseline_for_task(task_type, complexity)` — baseline model *varies*: `"haiku"` for query tasks, `"opus"` for research/complex tasks, `"sonnet"` otherwise. Feeds `router.py`'s `_emit_ledger_attempt(..., baseline_equivalent_cost_usd=...)` → `execution_ledger` → `saved_usd` in ~28 consumers.
- `receipt_store.compute_receipt()` — baseline model is *unconditionally Opus* ($5/$25, hardcoded, correct value but re-typed rather than imported), for **every** task type/complexity. Feeds `~/.chuzom/receipts.db`, read by `hooks/session-start.py` and `hooks/session-end.py`.
- `hooks/savings_logger.py::_BASELINE_MODEL_BY_COMPLEXITY` — also unconditionally Opus for all three complexity tiers, per an explicit "2026-07-12 (user decision)" comment.

**Router.py calls both mechanisms back-to-back for the identical accepted response** (confirmed at `router.py:2687-2712`): first computing `_baseline_equivalent_cost_usd` via the task-varying, partly-stale `cost._get_baseline_cost()`, then immediately calling `compute_receipt()` which recomputes an *always-Opus, always-correct-rate* savings figure for the same `response.input_tokens`/`response.output_tokens`. For a query task, the ledger number is based on a cheap haiku baseline while the receipt number is based on an Opus baseline — structurally guaranteed to disagree by design, not by drift. For a research/complex task, both use an Opus baseline, but the ledger number is *also* 3x-inflated by the stale `BASELINE_PRICING` table. Two numbers, from the same event, in two different persisted stores, with no reconciliation step anywhere in the codebase.

## 5. Other recurring incident classes visible in the sweep (not the pricing family)

Skimming `git log --grep` results for `race`/`locked` (65+37 hits) and `silent` (65 hits) shows a similar shape of "found via audit → fixed narrowly → possible siblings unchecked" commits (e.g. `0a87dd4 fix(hardening): cluster 6 — C-01 fix session_store concurrent-write data loss via cross-process file locking`, `582b62e fix(session): make record_step atomic — kill lost-update & cancel-clobber races`). A full per-incident write-up of these was out of scope given time budget, but the pattern-density strongly suggests the same "narrow fix, no systemic invariant enforcement" shape recurs outside the cost subsystem too — flagged here as a follow-up area, not independently proven to the same evidentiary standard as §1–4.
