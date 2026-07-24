"""Consolidated tool surface — North Star P4 / 1.0 direction (Docs/TOOL_SURFACE_PROPOSAL.md).

These are the front-door tool names from the 73→11 proposal, registered ALONGSIDE
the existing tools (nothing is removed — this is a NON-BREAKING alias layer that
sets up the 1.0 cutover). `llm_act` is the agentic *execution* door: the tool
enforcement steers operational work to, and — like every ``llm_*`` tool — calling
it clears an enforcement lock, so a task that needs to *do* things always has an
unblocked path (no wrong-tool dead-end).
"""
from __future__ import annotations

from mcp.server.fastmcp import Context

from chuzom.tools.admin import (
    llm_budget,
    llm_cache_clear,
    llm_gain,
    llm_health,
    llm_import_profile,
    llm_policy,
    llm_providers,
    llm_savings,
    llm_session_savings,
    llm_session_spend,
    llm_set_profile,
    llm_usage,
)
from chuzom.tools.agents import (
    chuzom_agent_check_budget,
    chuzom_agent_complete_session,
    chuzom_agent_lineage,
    chuzom_agent_list,
)
from chuzom.tools.agentic import llm_delegate
from chuzom.tools.text import (
    llm_analyze,
    llm_code,
    llm_generate,
    llm_query,
    llm_research,
)

# tier → the completion tools' complexity vocabulary
_TIER_TO_COMPLEXITY = {"fast": "simple", "balanced": "moderate", "best": "complex"}


async def llm_act(task: str, budget_usd: float = 1.0, context: str = "") -> str:
    """Agentic execution — do a real task end-to-end: decompose into milestones,
    run them on the cheapest capable tier *with tools* (files/commands/verify),
    escalate on failure without redoing done work, and return an honest JSON
    result (outcome, per-milestone status, events, savings). This is the 1.0 name
    for agentic delegation; currently a thin alias of ``llm_delegate``.

    *context* is optional conversation context handed to the delegated agents."""
    return await llm_delegate(task, budget_usd=budget_usd, context=context)


async def llm(
    prompt: str,
    ctx: Context,
    task: str = "auto",
    tier: str = "balanced",
    context: str | None = None,
    system_prompt: str | None = None,
) -> str:
    """Unified COMPLETION door — one text-in→text-out entry that routes to the
    right cost tier internally, so callers don't pre-pick a tool. *task* selects
    the specialization (auto/query, analyze, code, research, generate); *tier*
    (fast/balanced/best) maps to the model complexity. The 1.0 name that collapses
    llm_query/analyze/code/research/generate; those remain as aliases underneath."""
    complexity = _TIER_TO_COMPLEXITY.get((tier or "").lower(), "moderate")
    t = (task or "auto").lower()
    if t == "research":
        return await llm_research(prompt, ctx, system_prompt=system_prompt, context=context)
    if t == "analyze":
        return await llm_analyze(prompt, ctx, complexity=complexity,
                                 system_prompt=system_prompt, context=context)
    if t == "code":
        return await llm_code(prompt, ctx, complexity=complexity,
                              system_prompt=system_prompt, context=context)
    if t == "generate":
        return await llm_generate(prompt, ctx, complexity=complexity,
                                  system_prompt=system_prompt, context=context)
    # auto / query — the general default
    return await llm_query(prompt, ctx, complexity=complexity,
                           system_prompt=system_prompt, context=context)


async def chuzom_status(view: str = "summary", period: str = "today") -> str:
    """Read-only status/observability door — collapses the many llm_* reporting
    tools into one *view* selector: summary/savings · session_savings · spend ·
    usage · health · providers · gain. The old tools remain as aliases underneath."""
    v = (view or "summary").lower()
    if v in ("savings", "summary"):
        return await llm_savings()
    if v in ("session_savings", "session-savings"):
        return await llm_session_savings()
    if v in ("spend", "session_spend"):
        return await llm_session_spend()
    if v == "usage":
        return await llm_usage(period=period)
    if v == "health":
        return await llm_health()
    if v == "providers":
        return await llm_providers()
    if v == "gain":
        return await llm_gain(period=period)
    return await llm_savings()


async def chuzom_admin(action: str, value: str = "") -> str:
    """Config/admin door — collapses the mutating/config llm_* tools into one
    *action* selector: set_profile (value=profile) · import_profile (value=url) ·
    clear_cache · policy · budget. Old tools stay as aliases underneath."""
    a = (action or "").lower()
    if a == "set_profile":
        return await llm_set_profile(value)
    if a == "import_profile":
        return await llm_import_profile(url=value)
    if a == "clear_cache":
        return await llm_cache_clear()
    if a == "policy":
        return await llm_policy()
    if a == "budget":
        return await llm_budget()
    return f"unknown admin action: {action!r} (try set_profile/import_profile/clear_cache/policy/budget)"


async def chuzom_session(action: str, session_id: str = "", limit: int = 200) -> dict:
    """Agent-session door — collapses the simple chuzom_agent_* lifecycle tools
    into one *action* selector: list · check_budget · complete · lineage (all take
    a session_id, or none). start/route carry richer params — call those tools
    directly. Old tools stay registered underneath."""
    a = (action or "").lower()
    if a == "list":
        return await chuzom_agent_list()
    if a == "check_budget":
        return await chuzom_agent_check_budget(session_id)
    if a == "complete":
        return await chuzom_agent_complete_session(session_id)
    if a == "lineage":
        return await chuzom_agent_lineage(session_id, limit=limit)
    return {"error": f"unknown/rich session action: {action!r}; "
                     "use list/check_budget/complete/lineage, or start/route directly"}


def register(mcp, should_register=None) -> None:
    """Register the consolidated front-door tools (aliases; old tools stay)."""
    if should_register is None or should_register("llm_act"):
        mcp.tool()(llm_act)
    if should_register is None or should_register("llm"):
        mcp.tool()(llm)
    if should_register is None or should_register("chuzom_status"):
        mcp.tool()(chuzom_status)
    if should_register is None or should_register("chuzom_admin"):
        mcp.tool()(chuzom_admin)
    if should_register is None or should_register("chuzom_session"):
        mcp.tool()(chuzom_session)
