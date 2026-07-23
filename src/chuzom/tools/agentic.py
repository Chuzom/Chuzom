"""MCP tool: ``llm_delegate`` — agentic delegation entry point.

Thin wrapper. The heavy logic (planning, milestone-gated escalating execution,
acceptance, savings) lives in ``chuzom.agentic``. This module builds the default
backends (planner + Codex adapter ladder) and calls the delegation service. The
planner/adapter factories are module-level and injectable so tests never touch a
live model.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from chuzom.agentic.adapters import CodexAdapter
from chuzom.agentic.planner import PlannerModel, PlanRejected, hybrid_plan
from chuzom.agentic.service import run_delegation

# Injectable factories — tests override these; production uses the defaults.
planner_factory: Callable[[], PlannerModel] | None = None
adapters_factory: Callable[[], dict[int, Any]] | None = None


def _default_planner() -> PlannerModel:
    """Default planner. Wiring to chuzom's live routing (a model that emits an
    objective-check plan) is deferred; until then it fails closed so the tool
    surfaces an honest 'could not plan' result rather than fabricating done."""
    def planner_model(_goal: str) -> list[dict[str, Any]]:
        raise PlanRejected(
            "default planner not yet wired to chuzom routing (WIP) — "
            "call with an injected planner or supply milestones"
        )
    return planner_model


def _default_adapters() -> dict[int, Any]:
    # tier 1 = Codex-as-agent (subscription, $0 metered). Local tier-0 lands with P3b.
    return {1: CodexAdapter(tier=1)}


async def llm_delegate(
    task: str, budget_usd: float = 1.0, baseline_cost_per_milestone: float = 0.20
) -> str:
    """Agentic delegation: decompose *task* into milestones, run them on the
    cheapest capable tier with objective acceptance checks, escalate on failure
    without redoing achieved milestones, and return a JSON result with the
    outcome, transparency events, and honest savings. Never gets stuck — an
    unmeetable milestone is surfaced, not looped."""
    planner = (planner_factory or _default_planner)()
    adapters = (adapters_factory or _default_adapters)()
    try:
        milestones = hybrid_plan(task, planner)
    except PlanRejected as exc:
        return json.dumps({"outcome": "surfaced", "ok": False, "reason": f"planning failed: {exc}"})
    result = run_delegation(
        task, milestones, adapters,
        baseline_cost_per_milestone=baseline_cost_per_milestone,
        budget_cap_usd=budget_usd,
    )
    return json.dumps(result)


def register(mcp) -> None:
    """Register the llm_delegate tool with the FastMCP server."""
    mcp.tool()(llm_delegate)
