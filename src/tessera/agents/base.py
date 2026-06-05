"""Agent layer data model — AgentProfile + AgentSession + SessionState."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SessionState(str, Enum):
    """Lifecycle states for an agent session.

    Transitions:
        ACTIVE → COMPLETED   (normal finish)
        ACTIVE → ERRORED     (caller hit an unrecoverable error)
        ACTIVE → BUDGET_EXCEEDED  (budget envelope refused a call)
    Terminal states are immutable; record_step on a terminal session is a
    no-op that returns the session unchanged.
    """

    ACTIVE = "active"
    COMPLETED = "completed"
    ERRORED = "errored"
    BUDGET_EXCEEDED = "budget_exceeded"

    @property
    def is_terminal(self) -> bool:
        return self in (SessionState.COMPLETED, SessionState.ERRORED, SessionState.BUDGET_EXCEEDED)


@dataclass(frozen=True)
class AgentProfile:
    """How Tessera should route on behalf of one agent type.

    Profiles are pure data — no behaviour. The decision engine and the
    budget envelope consume them at runtime.

    Attributes:
        id: Stable identifier (matches config/agents.yaml `id:` field).
        description: Human-readable purpose. Surfaced in `tessera_agent_list`.
        tier_preference: Ordered list of preferred model tiers — local /
            cheap / mid / premium. The selector tries these in order.
            Empty means "use the default chain".
        signal_boosts: Multipliers applied to specific signal scores when
            this agent's session is active. E.g. {"code_keywords": 1.5}
            pushes the decision engine harder toward code-routing rules.
        preferred_chain: Chain alias (from config/signals.yaml) the
            selector should resolve. Overrides the default decision chain
            when set.
        default_budget_usd: Per-session budget if the caller doesn't
            override at start_session time.
        hard_max_budget_usd: Absolute cap. Sessions can request lower but
            never higher than this value.
    """

    id: str
    description: str
    tier_preference: tuple[str, ...] = ()
    signal_boosts: dict[str, float] = field(default_factory=dict)
    preferred_chain: str = ""
    default_budget_usd: float = 0.50
    hard_max_budget_usd: float = 2.00


@dataclass(frozen=True)
class AgentSession:
    """One run of one agent. Immutable snapshot — SessionStore returns a
    fresh instance on every update.

    Cost accounting:
        budget_cap_usd is fixed at create time (between profile default
        and profile hard max). consumed_usd grows monotonically via
        record_step. remaining_usd is derived; never stored.
    """

    session_id: str
    agent_id: str
    started_at: float
    completed_at: float | None
    parent_session_id: str | None
    budget_cap_usd: float
    consumed_usd: float
    step_count: int
    state: SessionState
    framework: str | None = None  # which framework adapter started this

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_cap_usd - self.consumed_usd)

    @property
    def is_active(self) -> bool:
        return self.state == SessionState.ACTIVE
