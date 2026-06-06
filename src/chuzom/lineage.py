"""Routing lineage — persist every routing decision and flag inversions.

A LineageRecord captures the full audit trail of a single routing decision:
which signals fired, what task_type/complexity was inferred, the chain of
models attempted, the model that succeeded, latency and cost, and any
notable anomalies (most importantly: inversions).

An **inversion** is a mismatch between classified complexity and the model
actually used. Two kinds:

    UP-INVERSION (most important): classified=complex but model is in the
        cheap tier. Indicates the cheap model was used despite the prompt
        being complex — likely a misroute that under-served the user.

    DOWN-INVERSION: classified=simple but model is premium. Indicates the
        cheap chain failed (all fallbacks exhausted) and the premium model
        was used unnecessarily — likely an over-spend.

Inversions are the feedback signal that drives the empirical learning loop
in v0.0.3+ (quality_gap re-derivation from real outcomes).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable


class Tier(str, Enum):
    """Coarse model tier — used for inversion detection."""

    LOCAL = "local"  # Ollama, on-device
    CHEAP = "cheap"  # Haiku, Gemini Flash, GPT-4o-mini, Groq
    MID = "mid"  # GPT-4o, Gemini Pro, Sonnet
    PREMIUM = "premium"  # Opus, o3, GPT-5
    UNKNOWN = "unknown"


class Inversion(str, Enum):
    NONE = "none"
    UP = "up_inversion"  # complex query → cheap/local tier
    DOWN = "down_inversion"  # simple query → premium tier


# Coarse map: complexity bucket -> expected tier upper bound.
# Crossing this boundary flags an inversion.
_COMPLEXITY_EXPECTED_TIER: dict[str, Tier] = {
    "simple": Tier.CHEAP,
    "moderate": Tier.MID,
    "complex": Tier.PREMIUM,
}

_TIER_ORDER: dict[Tier, int] = {
    Tier.LOCAL: 0,
    Tier.CHEAP: 1,
    Tier.MID: 2,
    Tier.PREMIUM: 3,
    Tier.UNKNOWN: -1,
}


@dataclass(frozen=True)
class LineageRecord:
    """One routing decision, fully audited.

    v0.0.2 adds agent-session attribution (agent_id, session_id, step_index,
    parent_session_id, framework). All five are optional — when the call
    isn't part of an agent run, they're left None and the row behaves
    exactly like a v0.0.1 row.
    """

    id: str
    timestamp: float
    host: str  # claude-code / cursor / codex / gemini-cli / codex-cli
    prompt_fingerprint: str  # SHA-256 of normalized prompt (privacy-safe)
    task_type: str  # query / research / generate / analyze / code / image
    complexity: str  # simple / moderate / complex
    classifier_method: str  # heuristic / signal_engine / llm / fallback
    signal_scores: dict[str, float]  # signal_name -> score
    fired_decisions: tuple[str, ...]
    chain_attempted: tuple[str, ...]  # ordered model IDs tried
    model_chosen: str
    model_tier: Tier
    inversion: Inversion
    outcome: str  # success / fail / timeout / quota
    latency_ms: int
    cost_usd: float
    notes: str = ""
    # ── v0.0.2 agent-session attribution (all optional) ──────────────────
    agent_id: str | None = None
    session_id: str | None = None
    step_index: int | None = None
    parent_session_id: str | None = None
    framework: str | None = None  # agno / hermes / langgraph / crewai / ...

    def to_row(self) -> tuple:
        return (
            self.id,
            self.timestamp,
            self.host,
            self.prompt_fingerprint,
            self.task_type,
            self.complexity,
            self.classifier_method,
            json.dumps(self.signal_scores),
            json.dumps(list(self.fired_decisions)),
            json.dumps(list(self.chain_attempted)),
            self.model_chosen,
            self.model_tier.value,
            self.inversion.value,
            self.outcome,
            self.latency_ms,
            self.cost_usd,
            self.notes,
            self.agent_id,
            self.session_id,
            self.step_index,
            self.parent_session_id,
            self.framework,
        )


def detect_inversion(complexity: str, model_tier: Tier) -> Inversion:
    """Classify a (complexity, tier) pair as up-/down-/no-inversion.

    Up-inversion: complex query → cheap or local. Most actionable.
    Down-inversion: simple query → premium. Wasted spend.
    """
    expected = _COMPLEXITY_EXPECTED_TIER.get(complexity)
    if expected is None or model_tier == Tier.UNKNOWN:
        return Inversion.NONE
    actual_rank = _TIER_ORDER[model_tier]
    expected_rank = _TIER_ORDER[expected]
    if complexity == "complex" and actual_rank < expected_rank:
        return Inversion.UP
    if complexity == "simple" and actual_rank > expected_rank:
        return Inversion.DOWN
    return Inversion.NONE


def tier_for_model(model_id: str) -> Tier:
    """Best-effort tier lookup based on model_id substrings.

    Used by lineage when the router doesn't pass an explicit tier. The
    canonical mapping lives in chuzom.model_selector; this is a fallback.
    """
    m = model_id.lower()
    if any(k in m for k in ("ollama", "qwen3.5", "gemma", "llama3", "phi-3")):
        return Tier.LOCAL
    if any(k in m for k in (
        "haiku", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-3.1-flash",
        "gpt-4o-mini", "gpt-5-nano", "groq",
    )):
        return Tier.CHEAP
    if any(k in m for k in (
        "sonnet", "gpt-4o", "gemini-1.5-pro", "gemini-2.5-pro", "gemini-3.1-pro",
    )):
        return Tier.MID
    if any(k in m for k in ("opus", "o3", "gpt-5", "claude-4")):
        return Tier.PREMIUM
    return Tier.UNKNOWN


# Base schema — runs first. Indexes here reference only columns that
# exist since v0.0.1, so they never fail on a pre-v0.0.2 DB.
_BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    host TEXT NOT NULL,
    prompt_fingerprint TEXT NOT NULL,
    task_type TEXT NOT NULL,
    complexity TEXT NOT NULL,
    classifier_method TEXT NOT NULL,
    signal_scores TEXT NOT NULL,
    fired_decisions TEXT NOT NULL,
    chain_attempted TEXT NOT NULL,
    model_chosen TEXT NOT NULL,
    model_tier TEXT NOT NULL,
    inversion TEXT NOT NULL,
    outcome TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    -- v0.0.2: agent-session attribution (nullable for backward compat).
    -- On a fresh DB these are created here; on a pre-v0.0.2 DB the
    -- CREATE TABLE IF NOT EXISTS is a no-op and _MIGRATIONS below
    -- adds the columns instead.
    agent_id TEXT,
    session_id TEXT,
    step_index INTEGER,
    parent_session_id TEXT,
    framework TEXT
);
CREATE INDEX IF NOT EXISTS idx_lineage_timestamp ON lineage(timestamp);
CREATE INDEX IF NOT EXISTS idx_lineage_inversion ON lineage(inversion);
CREATE INDEX IF NOT EXISTS idx_lineage_model ON lineage(model_chosen);
"""

# Idempotent migrations for DBs created before v0.0.2 — each fails harmlessly
# if the column already exists. Must run BEFORE _POST_MIGRATION_INDEXES so
# the v0.0.2 indexes can reference the newly-added columns.
_MIGRATIONS = (
    "ALTER TABLE lineage ADD COLUMN agent_id TEXT",
    "ALTER TABLE lineage ADD COLUMN session_id TEXT",
    "ALTER TABLE lineage ADD COLUMN step_index INTEGER",
    "ALTER TABLE lineage ADD COLUMN parent_session_id TEXT",
    "ALTER TABLE lineage ADD COLUMN framework TEXT",
)

# Indexes that depend on v0.0.2 columns — created only after migrations run.
_POST_MIGRATION_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_lineage_session ON lineage(session_id);
CREATE INDEX IF NOT EXISTS idx_lineage_agent ON lineage(agent_id);
"""

_INSERT = """
INSERT INTO lineage (
    id, timestamp, host, prompt_fingerprint, task_type, complexity,
    classifier_method, signal_scores, fired_decisions, chain_attempted,
    model_chosen, model_tier, inversion, outcome, latency_ms, cost_usd, notes,
    agent_id, session_id, step_index, parent_session_id, framework
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class LineageStore:
    """SQLite-backed lineage store. One row per routing decision.

    Default location: ~/.chuzom/lineage.db (gitignored). Override via the
    CHUZOM_LINEAGE_PATH env var for tests or custom installs.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path(
            os.environ.get("CHUZOM_LINEAGE_PATH")
            or (Path.home() / ".chuzom" / "lineage.db")
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        # 1. Base schema — safe on any DB version (CREATE IF NOT EXISTS
        #    on table + pre-v0.0.2 indexes).
        self._conn.executescript(_BASE_SCHEMA)
        # 2. Apply idempotent migrations for v0.0.2 columns. Pre-v0.0.2
        #    DBs need ALTER TABLE; newly-created DBs already have these
        #    columns from _BASE_SCHEMA and skip via duplicate-column guard.
        for stmt in _MIGRATIONS:
            try:
                self._conn.execute(stmt)
            except sqlite3.OperationalError as err:
                if "duplicate column" not in str(err):
                    raise
        # 3. v0.0.2 indexes — must run AFTER migrations so the referenced
        #    columns exist on a pre-v0.0.2 DB.
        self._conn.executescript(_POST_MIGRATION_INDEXES)
        self._conn.commit()

    def record(self, entry: LineageRecord) -> None:
        self._conn.execute(_INSERT, entry.to_row())
        self._conn.commit()
        # Auto-emit to OpenTelemetry when enabled. Fast path: avoid the
        # import + function call entirely when no OTLP endpoint is set.
        # Failure to emit must never block the lineage write — lineage is
        # the durable record, observability is best-effort.
        if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            try:
                from chuzom.observability import emit_routing_decision

                emit_routing_decision(entry)
            except Exception:
                pass

    def recent(self, limit: int = 50) -> list[dict]:
        cursor = self._conn.execute(
            "SELECT * FROM lineage ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def inversions(self, kind: Inversion | None = None, limit: int = 50) -> list[dict]:
        if kind is None:
            cursor = self._conn.execute(
                "SELECT * FROM lineage WHERE inversion != 'none' "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM lineage WHERE inversion = ? ORDER BY timestamp DESC LIMIT ?",
                (kind.value, limit),
            )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def summary(self) -> dict:
        cursor = self._conn.execute(
            "SELECT inversion, COUNT(*) FROM lineage GROUP BY inversion"
        )
        counts = dict(cursor.fetchall())
        total = sum(counts.values())
        return {
            "total_decisions": total,
            "no_inversion": counts.get("none", 0),
            "up_inversions": counts.get("up_inversion", 0),
            "down_inversions": counts.get("down_inversion", 0),
            "inversion_rate": (total - counts.get("none", 0)) / total if total else 0.0,
        }

    # ── v0.0.2: session-aware queries ─────────────────────────────────────

    def by_session(self, session_id: str) -> list[dict]:
        """Every routing decision in a single agent session, ordered by step."""
        cursor = self._conn.execute(
            "SELECT * FROM lineage WHERE session_id = ? "
            "ORDER BY step_index ASC, timestamp ASC",
            (session_id,),
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def session_cost(self, session_id: str) -> float:
        """Cumulative cost across all steps in a session."""
        cursor = self._conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM lineage WHERE session_id = ?",
            (session_id,),
        )
        return float(cursor.fetchone()[0])

    def by_agent(self, agent_id: str, limit: int = 100) -> list[dict]:
        """Recent decisions for one agent profile, across all its sessions."""
        cursor = self._conn.execute(
            "SELECT * FROM lineage WHERE agent_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (agent_id, limit),
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def by_framework(self, framework: str, limit: int = 100) -> list[dict]:
        """Recent decisions originating from one framework adapter."""
        cursor = self._conn.execute(
            "SELECT * FROM lineage WHERE framework = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (framework, limit),
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        self._conn.close()


def make_record(
    *,
    host: str,
    prompt_fingerprint: str,
    task_type: str,
    complexity: str,
    classifier_method: str,
    signal_scores: dict[str, float],
    fired_decisions: Iterable[str],
    chain_attempted: Iterable[str],
    model_chosen: str,
    outcome: str,
    latency_ms: int,
    cost_usd: float,
    model_tier: Tier | None = None,
    notes: str = "",
    # ── v0.0.2 agent-session attribution ──────────────────────────────────
    agent_id: str | None = None,
    session_id: str | None = None,
    step_index: int | None = None,
    parent_session_id: str | None = None,
    framework: str | None = None,
) -> LineageRecord:
    """Convenience builder — derives tier + inversion automatically.

    Agent-session fields are optional. When omitted, the record describes a
    standalone routing decision (v0.0.1 semantics). When provided, the row
    joins the agent's lineage for cost rollups + session replay.
    """
    tier = model_tier if model_tier is not None else tier_for_model(model_chosen)
    inversion = detect_inversion(complexity, tier)
    return LineageRecord(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        host=host,
        prompt_fingerprint=prompt_fingerprint,
        task_type=task_type,
        complexity=complexity,
        classifier_method=classifier_method,
        signal_scores=dict(signal_scores),
        fired_decisions=tuple(fired_decisions),
        chain_attempted=tuple(chain_attempted),
        model_chosen=model_chosen,
        model_tier=tier,
        inversion=inversion,
        outcome=outcome,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        notes=notes,
        agent_id=agent_id,
        session_id=session_id,
        step_index=step_index,
        parent_session_id=parent_session_id,
        framework=framework,
    )
