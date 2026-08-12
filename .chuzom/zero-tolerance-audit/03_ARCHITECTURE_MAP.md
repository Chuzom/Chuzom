# RED-8 — Architecture Map: Duplicated Sources of Truth

Auditor: RED-8. Target: v1.1.1 / `c2c28821f690f7cbda42b46da06fc36ef77d816e`. Interpreter: `.venv-audit/bin/python` 3.11.15 only.

This file enumerates every duplicated-source-of-truth cluster found, with the mandatory "can these drift independently and cause a silent product failure" answer for each, and current numeric consistency where applicable.

## Cluster A — Opus/host baseline pricing (money math, live on the hot path)

| Location | Value (opus input/output $ per 1M) | Status |
|---|---|---|
| `cost.py::_OPUS_PRICING["claude-opus-4-8"]` | 5.0 / 25.0 | **corrected, documented as canonical** |
| `cost.py::BASELINE_PRICING["opus"]` | **15.0 / 75.0** | **STALE — same file as the corrected table above** |
| `cost.py::CLAUDE_RATES_PER_M["opus"]` | 15.00 / 75.00 (4-component) | stale, different purpose (Claude Code billing match) but same numbers |
| `calibration.py::_PRICING_PER_M["claude-opus-4-6"]` | 15.0 / 75.0 | **STALE**, independent copy, self-documented as "kept local... update alongside cost.py BASELINE_PRICING when provider rates change" (never updated) |
| `receipt_store.py::compute_receipt()` | 5.0 / 25.0 (hardcoded literal, not imported) | correct value, but re-typed, not sourced — comment says "keep in sync with hooks/savings_logger._PRICING_PER_MTOK" |
| `hooks/savings_logger.py::_PRICING_PER_MTOK[("claude","claude-opus-4-8")]` | 5.00 / 25.00 | correct, hardcoded, independent |
| `hooks/session-end.py::HOST_INPUT_PER_M/HOST_OUTPUT_PER_M` | imports `cost._HOST_INPUT_PER_M/_HOST_OUTPUT_PER_M`, fallback literal 5.0/25.0 | **fixed correctly** (imports canonical, fallback happens to match) |
| `tools/dashboard.py::_host_baseline()` | imports `cost._HOST_INPUT_PER_M/_HOST_OUTPUT_PER_M`, fallback literal 5.0/25.0 | **fixed correctly** (this is the file `d03b4d7` fixed) |
| `dashboard_data.py::query_window()` (line 182-183) | **`_OPUS_IN_PER_M = 15.0`, `_OPUS_OUT_PER_M = 75.0`** | **STALE, hardcoded, never imports cost.py** |
| `dashboard_data.py` second aggregator (line 286-287) | **`_OPUS_IN_PER_M = 15.0`, `_OPUS_OUT_PER_M = 75.0`** | **STALE, second independent copy within the same file** |

**Can these drift independently and cause a silent product failure?** Yes — already have. `_OPUS_PRICING` was corrected in `cost.py`; `BASELINE_PRICING` in the *same file* was not. `tools/dashboard.py` was corrected by commit `d03b4d7`; `dashboard_data.py`, a sibling in the same package, was not. See `13_HISTORICAL_DEFECT_PATTERNS.md` for the git-log proof and the live 3.000x-inflation reproduction via direct code execution.

**Live consumer fan-out of the stale `dashboard_data.py::query_window()` path** (confirmed via `grep -rl "saved_usd" src/`): `session-end.py`, `dashboard/tui.py`, `dashboard/server.py`, `statusline_hud.py`, `commands/gain.py`, `commands/explain_dashboard.py`, `commands/replay.py`, `commands/team.py`, `team.py`, `quota_savings.py`, `routing_quality.py`, `routing_report.py`, `onboard.py`, `test_delta.py`, `session_spend.py`, `ui/session_summary.py`, `ui/status_premium.py`, `tools/subscription.py`, `tools/admin.py`, `tools/text.py`, `tools/routing.py`, `tui/app.py`, `agentic/service.py`, `agentic/savings.py`, `agentic/telemetry.py`, `hooks/cc-usage-track.py`, `hooks/status-bar.py` — **~26 consumer files**, i.e. essentially the entire user-facing savings-reporting surface.

## Cluster B — o3 (OpenAI) pricing

| Location | o3 input/output $ per 1M | Status |
|---|---|---|
| `cost.py::OPENAI_RATES_PER_M["o3"]` | 15.00 / 60.00 | **STALE**, savings_logger.py's own comment calls this exact value "stale" |
| `calibration.py::_PRICING_PER_M["o3"]` | 15.0 / 60.0 | **STALE**, same value |
| `hooks/savings_logger.py::_PRICING_PER_MTOK[("openai","o3")]` | 2.00 / 8.00 | claims to be "repriced from stale $15/$60" |

**Drift is live and current**, confirmed by direct grep of HEAD source (see `13_HISTORICAL_DEFECT_PATTERNS.md` §2).

## Cluster C — Haiku pricing (internal self-contradiction, no cross-file check needed)

Within `calibration.py::_PRICING_PER_M` alone:
- `"claude-haiku-4-5"`: `{"input": 0.25, "output": 1.25}`
- `"claude-haiku-4-5-20251001"`: `{"input": 0.80, "output": 4.0}`

These are plausibly the same real model addressed by bare alias vs. dated snapshot name (the module's own `_normalize_model_name()` strips only a `provider/` prefix, not the dated-vs-bare distinction, so both keys remain independently reachable depending on caller input). 3.2x price difference for what a caller could reasonably believe is one model. Cross-file, a **fourth** haiku figure exists in `savings_logger.py::_PRICING_PER_MTOK[("claude","claude-haiku-4-5")]` = `(1.00, 5.00)` — matching **none** of the three other haiku figures found repo-wide.

## Cluster D — task_type → tool-name mapping and prompt classification (triplicated)

| File | Mapping name | Classifier feeding it | Default fallback tool |
|---|---|---|---|
| `hooks/auto-route.py` (line 1731-1739) | `TOOL_MAP` (8 keys incl. image/coordination/auto) | `classify_prompt()` — multi-stage: fast-path pattern match (coordination/build/content-gen/introspection/benchmark) → heuristic scoring → Ollama/cheap-API/weak-heuristic escalation | `llm_route` |
| `hooks/agent-route.py` (line 215-220) | `_TOOL_MAP` (5 keys) | `_classify_task_type()` — single-pass regex signal scorer (`_TASK_SIGNALS`, 5 patterns), `max(scores)` with `analyze` fallback if no signal fires | `llm_analyze` |
| `service.py` (line ~199-208) | `_route_for_task()`'s inline dict (5 keys) | `/classify` FastAPI endpoint's `_heuristic_classify()` — a third, independent heuristic | `llm_route` |

Three independent dicts encoding the same logical mapping, three independently-maintained classifiers of markedly different sophistication, two different default fallback tools for an unrecognized task type (`llm_route` vs `llm_analyze`). Currently non-drifted in overlapping keys only because no one has added a 6th task type to one without the others — this is fragility, not correctness. `service.py`'s classification path is additionally suspected dead/orphaned: its HTTP client (`hook_client.classify_prompt`) has **zero importers** anywhere in `src/` (confirmed via `grep -rln "hook_client.classify_prompt" src/` returning empty), meaning the sidecar service and its own independent classifier/mapping may never actually be invoked by the live hook chain, yet remain a third copy of ground truth to keep in sync regardless.

**Emission-time safety note (positive finding, contrast case):** both `auto-route.py` and `agent-route.py` correctly pass the *resolved logical tool name* through `tool_surface.route_tool()`/`call_parts()` before emitting the final directive string to the user/hook output — so the specific CHZ-SURF-01 defect (hardcoded, unregistered tool name reaching the user) does not currently recur in these two files. `tool_surface.py` is the one cluster in this audit where the "single source of truth" claim holds up under verification — see §5 for why the pricing tables didn't get the same treatment.

## Cluster E — Two baseline-selection *policies*, not just two pricing tables

`cost.py::_get_baseline_for_task()` (varies baseline model by task_type/complexity) vs. `receipt_store.compute_receipt()` and `hooks/savings_logger.py::_BASELINE_MODEL_BY_COMPLEXITY` (always Opus). Router.py's accepted-attempt code path (`router.py:2687-2716`) invokes **both** policies for the same event, writing two different savings figures to two different stores (execution ledger vs. receipts.db) with no reconciliation. See `13_HISTORICAL_DEFECT_PATTERNS.md` §4 for detail.

## Why `tool_surface.py` succeeded where the pricing tables failed

`tool_surface.py` is stdlib-only by design specifically so it can be imported by hooks running under interpreters without the `chuzom` package installed — this constraint *forced* every consumer to import from one place rather than hand-copy tool names, and the team backed it with `scripts/lint_tool_surface.py` (CI) and `scripts/trace_northstar.py` (live trace against the running MCP server). No equivalent constraint or CI lint exists for pricing literals; `calibration.py` explicitly opts *out* of importing `cost.py` ("Kept local... so this module stays free of cross-module dependencies and remains pure") — a deliberate architectural choice that trades correctness-under-drift for import-graph purity, and there is no compensating lint to catch the resulting drift.
