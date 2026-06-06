"""Agent layer — profiles, sessions, budget envelope.

Chuzom does NOT execute agents. It tracks routing decisions per agent
session, applies per-profile routing biases (tier preference, signal
boosts), and enforces per-session budget caps.

The agent runtime — plan / act / observe / reflect — lives in the host
CLI (Claude Code subagents, Cursor Composer) or in an external framework
(Agno, Hermes, LangGraph, CrewAI). Chuzom makes those calls smarter +
auditable; it doesn't replace the loop.

Usage:
    from chuzom.agents import AgentRegistry, AgentSession, SessionStore

    registry = AgentRegistry.from_yaml(Path("config/agents.yaml"))
    profile = registry.get("code-reviewer")
    store = SessionStore()
    session = store.create(agent_id=profile.id, budget_usd=profile.default_budget_usd)
    # ... call chuzom_agent_route(session_id=session.session_id, prompt=...)
    summary = store.complete(session.session_id)
"""
from chuzom.agents.base import (
    AgentProfile,
    AgentSession,
    SessionState,
)
from chuzom.agents.budget import BudgetEnvelope, BudgetExceeded
from chuzom.agents.registry import AgentRegistry
from chuzom.agents.session import SessionStore

__all__ = [
    "AgentProfile",
    "AgentSession",
    "SessionState",
    "BudgetEnvelope",
    "BudgetExceeded",
    "AgentRegistry",
    "SessionStore",
]
