"""Agent layer — profiles, sessions, budget envelope.

Tessera does NOT execute agents. It tracks routing decisions per agent
session, applies per-profile routing biases (tier preference, signal
boosts), and enforces per-session budget caps.

The agent runtime — plan / act / observe / reflect — lives in the host
CLI (Claude Code subagents, Cursor Composer) or in an external framework
(Agno, Hermes, LangGraph, CrewAI). Tessera makes those calls smarter +
auditable; it doesn't replace the loop.

Usage:
    from tessera.agents import AgentRegistry, AgentSession, SessionStore

    registry = AgentRegistry.from_yaml(Path("config/agents.yaml"))
    profile = registry.get("code-reviewer")
    store = SessionStore()
    session = store.create(agent_id=profile.id, budget_usd=profile.default_budget_usd)
    # ... call tessera_agent_route(session_id=session.session_id, prompt=...)
    summary = store.complete(session.session_id)
"""
from tessera.agents.base import (
    AgentProfile,
    AgentSession,
    SessionState,
)
from tessera.agents.budget import BudgetEnvelope, BudgetExceeded
from tessera.agents.registry import AgentRegistry
from tessera.agents.session import SessionStore

__all__ = [
    "AgentProfile",
    "AgentSession",
    "SessionState",
    "BudgetEnvelope",
    "BudgetExceeded",
    "AgentRegistry",
    "SessionStore",
]
