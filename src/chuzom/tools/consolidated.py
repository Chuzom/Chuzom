"""Consolidated tool surface — North Star P4 / 1.0 direction (Docs/TOOL_SURFACE_PROPOSAL.md).

These are the front-door tool names from the 73→11 proposal, registered ALONGSIDE
the existing tools (nothing is removed — this is a NON-BREAKING alias layer that
sets up the 1.0 cutover). `llm_act` is the agentic *execution* door: the tool
enforcement steers operational work to, and — like every ``llm_*`` tool — calling
it clears an enforcement lock, so a task that needs to *do* things always has an
unblocked path (no wrong-tool dead-end).
"""
from __future__ import annotations

from chuzom.tools.agentic import llm_delegate


async def llm_act(task: str, budget_usd: float = 1.0, context: str = "") -> str:
    """Agentic execution — do a real task end-to-end: decompose into milestones,
    run them on the cheapest capable tier *with tools* (files/commands/verify),
    escalate on failure without redoing done work, and return an honest JSON
    result (outcome, per-milestone status, events, savings). This is the 1.0 name
    for agentic delegation; currently a thin alias of ``llm_delegate``.

    *context* is optional conversation context handed to the delegated agents."""
    return await llm_delegate(task, budget_usd=budget_usd, context=context)


def register(mcp, should_register=None) -> None:
    """Register the consolidated front-door tools (aliases; old tools stay)."""
    if should_register is None or should_register("llm_act"):
        mcp.tool()(llm_act)
