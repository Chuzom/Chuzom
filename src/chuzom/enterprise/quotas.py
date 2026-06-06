"""Per-identity quotas — daily + monthly spend caps with pre-emptive refusal.

Each user and team can have a `QuotaPolicy` defining daily + monthly
USD caps. The router calls `QuotaTracker.would_exceed()` BEFORE
dispatching to a provider; on True it returns a structured refusal that
the caller surfaces to the user without spending money.

Soft and hard limits: soft hits emit a warning audit event but allow
the call; hard hits raise QuotaExceeded. Most orgs configure soft at
80% and hard at 100%.

SQLite at ~/.chuzom/quotas.db. Periodic time bucketing: daily rolls
at UTC midnight; monthly rolls at UTC start-of-month. The implementation
stores per-period accumulators rather than scanning lineage on each
call — O(1) per check.
"""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class QuotaExceeded(Exception):
    """Raised when a routing call would breach the configured cap."""

    def __init__(
        self,
        scope: str,  # "user" or "team"
        identifier: str,  # user_id or team_id
        period: str,  # "daily" or "monthly"
        cap_usd: float,
        consumed_usd: float,
        proposed_usd: float,
    ):
        self.scope = scope
        self.identifier = identifier
        self.period = period
        self.cap_usd = cap_usd
        self.consumed_usd = consumed_usd
        self.proposed_usd = proposed_usd
        super().__init__(
            f"{scope} {identifier!r} {period} quota exceeded — "
            f"cap=${cap_usd:.2f}, consumed=${consumed_usd:.2f}, "
            f"proposed=${proposed_usd:.2f}"
        )


@dataclass(frozen=True)
class QuotaPolicy:
    """Per-identity caps. Zero on either bound means unlimited."""

    daily_cap_usd: float = 0.0
    monthly_cap_usd: float = 0.0
    soft_warning_pct: float = 0.80  # emit a soft hit at 80% by default
    hard_block: bool = True  # if False, log + allow even at 100%

    @property
    def is_unlimited(self) -> bool:
        return self.daily_cap_usd == 0 and self.monthly_cap_usd == 0


# ────────────────────────────────────────────────────────────────────────
# Schema
# ────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS quota_consumption (
    scope TEXT NOT NULL,
    identifier TEXT NOT NULL,
    period TEXT NOT NULL,
    bucket TEXT NOT NULL,
    consumed_usd REAL NOT NULL DEFAULT 0.0,
    last_update REAL NOT NULL,
    PRIMARY KEY (scope, identifier, period, bucket)
);

CREATE TABLE IF NOT EXISTS quota_policies (
    scope TEXT NOT NULL,
    identifier TEXT NOT NULL,
    daily_cap_usd REAL NOT NULL DEFAULT 0.0,
    monthly_cap_usd REAL NOT NULL DEFAULT 0.0,
    soft_warning_pct REAL NOT NULL DEFAULT 0.80,
    hard_block INTEGER NOT NULL DEFAULT 1,
    updated_at REAL NOT NULL,
    PRIMARY KEY (scope, identifier)
);

CREATE INDEX IF NOT EXISTS idx_quota_bucket ON quota_consumption(scope, identifier, period);
"""


def _current_bucket(period: str) -> str:
    """UTC-aligned period bucket key."""
    now = datetime.now(timezone.utc)
    if period == "daily":
        return now.strftime("%Y-%m-%d")
    if period == "monthly":
        return now.strftime("%Y-%m")
    raise ValueError(f"unknown period {period!r}")


# ────────────────────────────────────────────────────────────────────────
# Tracker
# ────────────────────────────────────────────────────────────────────────

class QuotaTracker:
    """SQLite-backed quota state."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path(
            os.environ.get("CHUZOM_QUOTAS_PATH")
            or (Path.home() / ".chuzom" / "quotas.db")
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── Policy management ─────────────────────────────────────────────

    def set_policy(
        self, scope: str, identifier: str, policy: QuotaPolicy
    ) -> None:
        if scope not in ("user", "team"):
            raise ValueError(f"unknown scope {scope!r}")
        self._conn.execute(
            "INSERT OR REPLACE INTO quota_policies "
            "(scope, identifier, daily_cap_usd, monthly_cap_usd, "
            "soft_warning_pct, hard_block, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (scope, identifier,
             policy.daily_cap_usd, policy.monthly_cap_usd,
             policy.soft_warning_pct,
             1 if policy.hard_block else 0,
             time.time()),
        )
        self._conn.commit()

    def get_policy(
        self, scope: str, identifier: str
    ) -> QuotaPolicy:
        row = self._conn.execute(
            "SELECT daily_cap_usd, monthly_cap_usd, soft_warning_pct, "
            "hard_block FROM quota_policies "
            "WHERE scope = ? AND identifier = ?",
            (scope, identifier),
        ).fetchone()
        if not row:
            return QuotaPolicy()  # unlimited default
        return QuotaPolicy(
            daily_cap_usd=row[0], monthly_cap_usd=row[1],
            soft_warning_pct=row[2], hard_block=bool(row[3]),
        )

    # ── Consumption + checks ──────────────────────────────────────────

    def consumed(self, scope: str, identifier: str, period: str) -> float:
        bucket = _current_bucket(period)
        row = self._conn.execute(
            "SELECT consumed_usd FROM quota_consumption "
            "WHERE scope = ? AND identifier = ? AND period = ? AND bucket = ?",
            (scope, identifier, period, bucket),
        ).fetchone()
        return row[0] if row else 0.0

    def would_exceed(
        self,
        scope: str, identifier: str,
        prospective_cost_usd: float,
    ) -> tuple[bool, dict]:
        """Pre-check before dispatching a routing call.

        Returns (would_exceed, info_dict). The info dict is suitable to
        surface in an audit event when the call is refused, and to
        return to the caller for a structured error.
        """
        policy = self.get_policy(scope, identifier)
        if policy.is_unlimited:
            return (False, {"unlimited": True})

        info = {"scope": scope, "identifier": identifier}
        for period, cap in (
            ("daily", policy.daily_cap_usd),
            ("monthly", policy.monthly_cap_usd),
        ):
            if cap <= 0:
                continue
            consumed = self.consumed(scope, identifier, period)
            projected = consumed + prospective_cost_usd
            if projected > cap and policy.hard_block:
                info.update({
                    "period": period, "cap_usd": cap,
                    "consumed_usd": consumed,
                    "proposed_usd": prospective_cost_usd,
                })
                return (True, info)
            if projected > cap * policy.soft_warning_pct:
                info.setdefault("soft_hits", []).append({
                    "period": period, "cap_usd": cap,
                    "consumed_usd": consumed,
                    "pct": projected / cap,
                })
        return (False, info)

    def consume(
        self,
        scope: str, identifier: str,
        cost_usd: float,
    ) -> None:
        """Record actual spend. Should be called after a successful
        routing call with the real cost (post-provider response)."""
        for period in ("daily", "monthly"):
            bucket = _current_bucket(period)
            self._conn.execute(
                "INSERT INTO quota_consumption "
                "(scope, identifier, period, bucket, consumed_usd, last_update) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (scope, identifier, period, bucket) DO UPDATE "
                "SET consumed_usd = consumed_usd + excluded.consumed_usd, "
                "last_update = excluded.last_update",
                (scope, identifier, period, bucket, cost_usd, time.time()),
            )
        self._conn.commit()

    def raise_if_would_exceed(
        self, scope: str, identifier: str, prospective_cost_usd: float
    ) -> None:
        """Raise QuotaExceeded if the call would breach. Returns silently
        otherwise."""
        breached, info = self.would_exceed(
            scope, identifier, prospective_cost_usd
        )
        if breached:
            raise QuotaExceeded(
                scope=info["scope"], identifier=info["identifier"],
                period=info["period"], cap_usd=info["cap_usd"],
                consumed_usd=info["consumed_usd"],
                proposed_usd=info["proposed_usd"],
            )

    def close(self) -> None:
        self._conn.close()
