"""MCP tool: ``llm_delegate`` — agentic delegation entry point.

Thin wrapper. The heavy logic (planning, milestone-gated escalating execution,
acceptance, savings) lives in ``chuzom.agentic``. This module builds the default
backends (planner + Codex adapter ladder) and calls the delegation service. The
planner/adapter factories are module-level and injectable so tests never touch a
live model.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from chuzom.agentic.adapters import CodexAdapter
from chuzom.agentic.planner import PlannerModel, PlanRejected, hybrid_plan
from chuzom.agentic.service import run_delegation

# Injectable factories — tests override these; production uses the defaults.
planner_factory: Callable[[], PlannerModel] | None = None
adapters_factory: Callable[[], dict[int, Any]] | None = None


_PLANNER_SYSTEM = (
    "You are a task planner for an automated coding agent. Break the task into a "
    "small ordered list of milestones. Every milestone MUST have an OBJECTIVE, "
    "executable acceptance check — never a subjective one. Output ONLY a JSON array."
)


def _planner_prompt(goal: str) -> str:
    return (
        f"Task: {goal}\n\n"
        "Return ONLY a JSON array of milestones (no prose). Each item is "
        '{"id": str, "description": str, "acceptance": <check>} where <check> is one of:\n'
        '  {"type":"cmd","command":["argv","..."]}   # passes iff the command exits 0\n'
        '  {"type":"lint","paths":["path","..."]}     # passes iff the linter is clean\n'
        '  {"type":"diff","files":["f"],"symbols":["s"]}  # produced files/symbols present\n'
        '  {"type":"canary","marker":"TOKEN"}         # marker present in the output\n'
    )


def _extract_plan_json(text: str) -> list[dict[str, Any]] | None:
    """Robustly pull a JSON milestone array out of a model's text response."""
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        i, j = text.find("["), text.rfind("]")
        candidate = text[i : j + 1] if (i != -1 and j > i) else None
    if candidate is None:
        return None
    try:
        val = json.loads(candidate)
    except (ValueError, TypeError):
        return None
    return val if isinstance(val, list) else None


def _default_planner() -> PlannerModel:
    """Live planner: routes to a chuzom-selected model that emits an objective-check
    milestone plan, then parses the JSON. Fails closed (PlanRejected) on any error
    so the tool surfaces an honest 'planning failed' rather than fabricating done."""
    async def planner_model(goal: str) -> list[dict[str, Any]]:
        try:
            from chuzom.router import route_and_call
            from chuzom.types import TaskType
            resp = await route_and_call(
                TaskType.ANALYZE, _planner_prompt(goal), system_prompt=_PLANNER_SYSTEM,
            )
        except Exception as exc:  # noqa: BLE001 — any routing failure fails closed
            raise PlanRejected(f"planner routing failed: {exc}") from exc
        plan = _extract_plan_json(getattr(resp, "content", "") or "")
        if plan is None:
            raise PlanRejected("planner model did not return a parseable JSON milestone plan")
        return plan
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
        milestones = await hybrid_plan(task, planner)
    except PlanRejected as exc:
        return json.dumps({"outcome": "surfaced", "ok": False, "reason": f"planning failed: {exc}"})
    result = run_delegation(
        task, milestones, adapters,
        baseline_cost_per_milestone=baseline_cost_per_milestone,
        budget_cap_usd=budget_usd,
    )
    # Record the honest saving into chuzom's ledger (fail-open — never breaks the call).
    from chuzom.agentic.telemetry import record_delegation_savings
    await record_delegation_savings(result)
    return json.dumps(result)


def register(mcp) -> None:
    """Register the llm_delegate tool with the FastMCP server."""
    mcp.tool()(llm_delegate)
