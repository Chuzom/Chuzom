"""Tool slim mode — tiered tool registration for token budget management.

Registering all 41 tools injects ~8,000 tokens into every Claude session,
degrading routing accuracy past 20–30K context tokens. Slim mode solves
this by registering only the tools appropriate for the active tier.

Three tiers (controlled via CHUZOM_SLIM env var):
  off      — all tools registered (default, backward-compatible)
  routing  — 12 core routing + admin tools (recommended for most users)
  core     — 4 essential tools only (maximum token savings)

Usage in server.py:
    from chuzom.tool_tiers import make_should_register
    gate = make_should_register(get_config().chuzom_slim)
    routing.register(mcp, gate)
"""

from __future__ import annotations

from typing import Callable

CORE_TOOLS: frozenset[str] = frozenset({
    "llm_query",
    "llm_code",
    "llm_research",
    "llm_usage",
})
"""4-tool tier — essential tools only. Maximum token savings (~7,500 tokens saved)."""

ROUTING_TOOLS: frozenset[str] = CORE_TOOLS | frozenset({
    "llm_analyze",
    "llm_generate",
    "llm_classify",
    "llm_route",
    "llm_auto",
    "llm_check_usage",
    "llm_set_profile",
    "llm_health",
    "llm_session_spend",
    "llm_session_savings",  # v10.1.0 — tier-grouped savings dashboard
    "llm_savings",
    "llm_reroute",
    "llm_select_agent",
})
"""12-tool tier — routing + core admin tools. Recommended for most users (~5,000 tokens saved)."""

# North Star 1.0 cutover (staged): the CONSOLIDATED front-door surface. Opt into it
# with CHUZOM_SLIM=consolidated to *run* the collapsed ~11-tool surface today (old
# tools hidden, not removed). This validates the doors cover every capability before
# the breaking 1.0 step that actually removes the 73 old tools.
CONSOLIDATED_TOOLS: frozenset[str] = frozenset({
    "llm",             # unified completion door (query/analyze/code/research/generate)
    "llm_act",         # agentic execution door (delegation)
    "chuzom_status",   # observability door (savings/usage/health/…)
    "chuzom_admin",    # config door (set_profile/clear_cache/…)
    "chuzom_session",  # agent-lifecycle door (list/check_budget/complete/lineage)
    "llm_route",       # auto-routing decision (no door alias yet)
    "llm_image",       # media (future: llm_media)
    "llm_audio",       # media (future: llm_media)
    "llm_edit",        # file ops (future: llm_fs)
    "chuzom_agent_start_session",  # rich session action (kept until chuzom_session covers it)
    "chuzom_agent_route",          # rich session action
})
"""~11-tool CONSOLIDATED front-door tier (North Star 1.0 direction)."""


def make_should_register(slim: str) -> Callable[[str], bool]:
    """Return a predicate that controls which tools are registered at startup.

    Args:
        slim: One of "off", "routing", or "core".
              Any other value defaults to "off" (all tools registered).

    Returns:
        Callable that takes a tool name and returns True if it should be registered.
    """
    slim = (slim or "off").strip().lower()

    if slim == "core":
        return lambda name: name in CORE_TOOLS
    if slim == "routing":
        return lambda name: name in ROUTING_TOOLS
    if slim == "consolidated":
        return lambda name: name in CONSOLIDATED_TOOLS
    # "off" or any unknown value — register everything
    return lambda name: True


def tier_summary(slim: str) -> str:
    """Return a human-readable summary of the active slim tier."""
    slim = (slim or "off").strip().lower()
    if slim == "core":
        return f"core ({len(CORE_TOOLS)} tools — maximum token savings)"
    if slim == "routing":
        return f"routing ({len(ROUTING_TOOLS)} tools — recommended)"
    if slim == "consolidated":
        return f"consolidated ({len(CONSOLIDATED_TOOLS)} front-door tools — North Star 1.0 surface)"
    return "off (all tools — maximum compatibility)"
