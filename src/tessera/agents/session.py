"""SQLite-backed session store at ~/.tessera/sessions.db.

One row per agent session. The session table tracks the lifecycle state
machine; per-step lineage lives in `~/.tessera/lineage.db` linked by
session_id.

Session state transitions:
    create() → ACTIVE
    record_step() → ACTIVE (or BUDGET_EXCEEDED if cap reached)
    complete() → COMPLETED
    error()    → ERRORED
    Terminal states refuse further mutations.
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path

from tessera.agents.base import AgentSession, SessionState
from tessera.agents.budget import BudgetEnvelope, BudgetExceeded


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    started_at REAL NOT NULL,
    completed_at REAL,
    parent_session_id TEXT,
    budget_cap_usd REAL NOT NULL,
    consumed_usd REAL NOT NULL DEFAULT 0.0,
    step_count INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL,
    framework TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
"""

_INSERT = """
INSERT INTO sessions (
    session_id, agent_id, started_at, completed_at, parent_session_id,
    budget_cap_usd, consumed_usd, step_count, state, framework
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_UPDATE_STEP = """
UPDATE sessions SET consumed_usd = ?, step_count = ?, state = ? WHERE session_id = ?
"""

_UPDATE_TERMINAL = """
UPDATE sessions SET state = ?, completed_at = ? WHERE session_id = ?
"""


class SessionNotFound(KeyError):
    """Raised when a session_id isn't in the store."""


class TerminalStateViolation(RuntimeError):
    """Raised when a mutation is attempted on a terminal-state session."""


def _row_to_session(row: tuple) -> AgentSession:
    return AgentSession(
        session_id=row[0],
        agent_id=row[1],
        started_at=row[2],
        completed_at=row[3],
        parent_session_id=row[4],
        budget_cap_usd=row[5],
        consumed_usd=row[6],
        step_count=row[7],
        state=SessionState(row[8]),
        framework=row[9],
    )


class SessionStore:
    """SQLite-backed store. One row per agent session; mutations are
    immediate writes. Caller is responsible for serializing concurrent
    access to the same session_id."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path(
            os.environ.get("TESSERA_SESSIONS_PATH")
            or (Path.home() / ".tessera" / "sessions.db")
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def create(
        self,
        *,
        agent_id: str,
        budget_usd: float,
        parent_session_id: str | None = None,
        framework: str | None = None,
    ) -> AgentSession:
        """Open a new active session with the given budget cap."""
        if budget_usd <= 0:
            raise ValueError("budget_usd must be positive")
        session_id = str(uuid.uuid4())
        now = time.time()
        session = AgentSession(
            session_id=session_id,
            agent_id=agent_id,
            started_at=now,
            completed_at=None,
            parent_session_id=parent_session_id,
            budget_cap_usd=budget_usd,
            consumed_usd=0.0,
            step_count=0,
            state=SessionState.ACTIVE,
            framework=framework,
        )
        self._conn.execute(
            _INSERT,
            (
                session.session_id,
                session.agent_id,
                session.started_at,
                None,
                session.parent_session_id,
                session.budget_cap_usd,
                session.consumed_usd,
                session.step_count,
                session.state.value,
                session.framework,
            ),
        )
        self._conn.commit()
        return session

    def get(self, session_id: str) -> AgentSession:
        cursor = self._conn.execute(
            "SELECT session_id, agent_id, started_at, completed_at, "
            "parent_session_id, budget_cap_usd, consumed_usd, step_count, "
            "state, framework FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise SessionNotFound(session_id)
        return _row_to_session(row)

    def envelope(self, session_id: str) -> BudgetEnvelope:
        """Construct a BudgetEnvelope reflecting current consumed/cap."""
        s = self.get(session_id)
        return BudgetEnvelope(cap_usd=s.budget_cap_usd, consumed_usd=s.consumed_usd)

    def check_budget(
        self, session_id: str, prospective_cost_usd: float
    ) -> bool:
        """True if charging prospective_cost would NOT breach the cap.

        Returns False (instead of raising) so callers can render a useful
        error or downshift before refusing.
        """
        env = self.envelope(session_id)
        return not env.would_exceed(prospective_cost_usd)

    def record_step(self, session_id: str, cost_usd: float) -> AgentSession:
        """Record an actual call's cost. Increments step_count and consumed.

        If the new consumed would breach the cap, the session transitions
        to BUDGET_EXCEEDED and BudgetExceeded is raised. Caller should
        decide whether to still log the lineage row (yes, for audit) or
        roll it back (rare).
        """
        s = self.get(session_id)
        if s.state.is_terminal:
            raise TerminalStateViolation(
                f"session {session_id} is {s.state.value}; cannot record_step"
            )
        env = BudgetEnvelope(cap_usd=s.budget_cap_usd, consumed_usd=s.consumed_usd)
        breached = env.would_exceed(cost_usd)
        new_consumed = s.consumed_usd + cost_usd
        new_step = s.step_count + 1
        new_state = SessionState.BUDGET_EXCEEDED if breached else SessionState.ACTIVE
        completed_at = time.time() if breached else None
        self._conn.execute(
            _UPDATE_STEP, (new_consumed, new_step, new_state.value, session_id)
        )
        if breached:
            self._conn.execute(
                _UPDATE_TERMINAL,
                (new_state.value, completed_at, session_id),
            )
        self._conn.commit()
        if breached:
            raise BudgetExceeded(
                session_id=session_id,
                cap_usd=s.budget_cap_usd,
                consumed_usd=s.consumed_usd,
                proposed_usd=cost_usd,
            )
        return self.get(session_id)

    def complete(self, session_id: str) -> AgentSession:
        """Mark the session COMPLETED. Idempotent — re-completing a
        completed session is a no-op (returns the same row)."""
        s = self.get(session_id)
        if s.state == SessionState.COMPLETED:
            return s
        if s.state.is_terminal:
            raise TerminalStateViolation(
                f"session {session_id} is {s.state.value}; cannot complete"
            )
        now = time.time()
        self._conn.execute(
            _UPDATE_TERMINAL,
            (SessionState.COMPLETED.value, now, session_id),
        )
        self._conn.commit()
        return self.get(session_id)

    def error(self, session_id: str) -> AgentSession:
        """Mark the session ERRORED. Used when the caller hits an
        unrecoverable failure mid-run."""
        s = self.get(session_id)
        if s.state.is_terminal:
            return s  # idempotent — already terminal
        now = time.time()
        self._conn.execute(
            _UPDATE_TERMINAL,
            (SessionState.ERRORED.value, now, session_id),
        )
        self._conn.commit()
        return self.get(session_id)

    # ── Queries ───────────────────────────────────────────────────────────

    def children(self, parent_session_id: str) -> list[AgentSession]:
        """All sessions spawned by parent_session_id (for nested agent rollups)."""
        cursor = self._conn.execute(
            "SELECT session_id, agent_id, started_at, completed_at, "
            "parent_session_id, budget_cap_usd, consumed_usd, step_count, "
            "state, framework FROM sessions WHERE parent_session_id = ? "
            "ORDER BY started_at ASC",
            (parent_session_id,),
        )
        return [_row_to_session(row) for row in cursor.fetchall()]

    def by_agent(self, agent_id: str, limit: int = 50) -> list[AgentSession]:
        cursor = self._conn.execute(
            "SELECT session_id, agent_id, started_at, completed_at, "
            "parent_session_id, budget_cap_usd, consumed_usd, step_count, "
            "state, framework FROM sessions WHERE agent_id = ? "
            "ORDER BY started_at DESC LIMIT ?",
            (agent_id, limit),
        )
        return [_row_to_session(row) for row in cursor.fetchall()]

    def rollup(self, session_id: str) -> dict:
        """Total cost across this session + all its descendants.

        Used for nested agent reporting: agent A spawned agent B, B spawned
        C — rollup(A) sums A + B + C.
        """
        s = self.get(session_id)
        total_cost = s.consumed_usd
        total_steps = s.step_count
        descendant_count = 0
        # BFS through children
        frontier = self.children(session_id)
        while frontier:
            next_frontier: list[AgentSession] = []
            for child in frontier:
                total_cost += child.consumed_usd
                total_steps += child.step_count
                descendant_count += 1
                next_frontier.extend(self.children(child.session_id))
            frontier = next_frontier
        return {
            "session_id": session_id,
            "agent_id": s.agent_id,
            "total_cost_usd": total_cost,
            "total_steps": total_steps,
            "descendant_session_count": descendant_count,
            "state": s.state.value,
        }

    def close(self) -> None:
        self._conn.close()
