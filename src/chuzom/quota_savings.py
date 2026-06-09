"""Quota-saved metric — weekly + 5h subscription-percentage counterfactual.

Translates chuzom's per-call ``saved_usd`` (= Opus-equivalent counterfactual
minus actual cost) into the same denominator the user sees on
claude.ai: **percentage points of subscription quota**.

Surfaces
--------
1. The routing notice line (``hooks/response_formatter.format_echo_context``)
   appends a short form: ``"saved Xpp wk / Ypp 5h"``.
2. The MCP tool ``llm_quota_saved`` returns the full breakdown.

Calibration
-----------
``weekly_pct`` from claude.ai is denominated in opaque subscription units;
``saved_usd`` is denominated in dollars. To convert, we need a
``$_per_pp`` ratio. This module uses a **configured constant** by default
(``CHUZOM_WEEKLY_QUOTA_USD_OPUS_EQUIV``, default $50 — roughly the
Opus-equivalent dollar value of one week of Claude Pro Max). The
constant is intentionally documented as an estimate; an "observed
calibration" path that derives the ratio from each user's own
historical claude_usage is a follow-up (T-QS-2).

Time windows
------------
* **Weekly** — UTC Monday 00:00 to now. Matches claude.ai's reset cadence.
* **5h** — last 5 hours rolling. Matches the session-limit window.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chuzom.logging import get_logger

log = get_logger("chuzom.quota_savings")


# Default calibration: Opus-equivalent USD per 1% of weekly quota.
# Anthropic Claude Pro Max ≈ $200/month subscription; rough Opus-cost
# equivalent at $15-in/$75-out per million tokens lands the weekly
# budget in the $40-60 range. $50 is the round middle of that band.
_DEFAULT_WEEKLY_QUOTA_USD = 50.0


@dataclass(frozen=True)
class QuotaSavingsSnapshot:
    """One snapshot of the user's quota-savings position.

    Pp = "percentage points" (additive, not multiplicative). E.g.
    counterfactual 47% with current 40% = ``7.0`` pp saved.
    """

    weekly_current_pct: float
    weekly_pp_saved: float
    weekly_counterfactual_pct: float
    weekly_saved_usd: float

    session_current_pct: float
    session_pp_saved: float
    session_counterfactual_pct: float
    session_saved_usd: float

    calibration_usd_per_pp: float
    calibration_source: str  # "configured" | "observed" — latter reserved

    def is_meaningful(self, threshold_pp: float = 0.5) -> bool:
        """True iff at least one window saved more than ``threshold_pp``.
        The routing-notice surface uses this to suppress noise when
        chuzom hasn't done anything cost-relevant yet."""
        return (
            self.weekly_pp_saved >= threshold_pp
            or self.session_pp_saved >= threshold_pp
        )

    def short_form(self) -> str:
        """Compact suffix for the routing notice line, e.g.
        ``"saved 7pp wk / 3pp 5h"``."""
        return (
            f"saved {self.weekly_pp_saved:.1f}pp wk / "
            f"{self.session_pp_saved:.1f}pp 5h"
        )


# ── Time window helpers ────────────────────────────────────────────────────


def _start_of_week_utc(now: datetime | None = None) -> datetime:
    """UTC Monday 00:00 most recently preceding ``now``."""
    now = now or datetime.now(timezone.utc)
    # weekday(): Mon=0..Sun=6
    days_since_mon = now.weekday()
    monday = (now - timedelta(days=days_since_mon)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday


def _start_of_5h_window_utc(now: datetime | None = None) -> datetime:
    """Now minus 5 hours."""
    now = now or datetime.now(timezone.utc)
    return now - timedelta(hours=5)


# ── Calibration ────────────────────────────────────────────────────────────


def _resolve_weekly_quota_usd() -> float:
    """Read the configured weekly quota in Opus-equivalent USD."""
    raw = os.environ.get("CHUZOM_WEEKLY_QUOTA_USD_OPUS_EQUIV", "")
    if not raw:
        return _DEFAULT_WEEKLY_QUOTA_USD
    try:
        value = float(raw)
    except ValueError:
        log.warning(
            "invalid_weekly_quota_env",
            value=raw,
            fallback=_DEFAULT_WEEKLY_QUOTA_USD,
        )
        return _DEFAULT_WEEKLY_QUOTA_USD
    if value <= 0:
        return _DEFAULT_WEEKLY_QUOTA_USD
    return value


def _calibration_usd_per_pp() -> tuple[float, str]:
    """Return ``(usd_per_pp, source)``. ``source`` is "configured" or
    (future) "observed". Today the configured path is the only one;
    the second tuple element documents that for callers."""
    weekly_usd = _resolve_weekly_quota_usd()
    return weekly_usd / 100.0, "configured"


# ── DB query ───────────────────────────────────────────────────────────────


def _default_db_path() -> Path:
    """Resolve the usage DB path. Honours CHUZOM_USAGE_DB_PATH for tests."""
    override = os.environ.get("CHUZOM_USAGE_DB_PATH")
    if override:
        return Path(override)
    return Path.home() / ".chuzom" / "usage.db"


def _sum_saved_usd_since(db_path: Path, since: datetime) -> float:
    """Sum ``saved_usd`` from the ``usage`` table since ``since`` (UTC).

    Returns ``0.0`` when the DB is missing or the column is absent — the
    metric is purely additive and a missing DB should never break the
    routing notice. The ``usage.saved_usd`` column was added by an
    idempotent ALTER migration, so its presence isn't guaranteed on
    older deployments."""
    if not db_path.exists():
        return 0.0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            since_iso = since.strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute(
                "SELECT COALESCE(SUM(saved_usd), 0.0) FROM usage WHERE timestamp >= ?",
                (since_iso,),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
        finally:
            conn.close()
    except sqlite3.OperationalError as err:
        # Most common: ``no such column: saved_usd`` on pre-migration DBs.
        log.debug("quota_savings_query_failed", error=str(err))
        return 0.0
    except Exception as err:
        log.warning("quota_savings_query_unexpected", error=str(err))
        return 0.0


# ── Public API ─────────────────────────────────────────────────────────────


def compute_quota_savings(
    *,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> QuotaSavingsSnapshot | None:
    """Compute the current quota-savings snapshot.

    Returns ``None`` when no usage cache is available — without
    ``state.get_last_usage()`` we cannot anchor the counterfactual to
    a meaningful current %.
    """
    from chuzom import state as _state

    cached = _state.get_last_usage()
    if cached is None:
        return None

    # ClaudeSubscriptionUsage returns 0.0-1.0 fractions; we surface 0-100.
    weekly_current_pct = cached.weekly_pct * 100.0
    session_current_pct = cached.session_pct * 100.0

    db = db_path or _default_db_path()
    weekly_saved = _sum_saved_usd_since(db, _start_of_week_utc(now))
    session_saved = _sum_saved_usd_since(db, _start_of_5h_window_utc(now))

    usd_per_pp, source = _calibration_usd_per_pp()
    # Guard against pathological calibration (env injected as 0).
    if usd_per_pp <= 0:
        usd_per_pp = _DEFAULT_WEEKLY_QUOTA_USD / 100.0
        source = "configured"

    weekly_pp = weekly_saved / usd_per_pp if weekly_saved > 0 else 0.0
    session_pp = session_saved / usd_per_pp if session_saved > 0 else 0.0

    return QuotaSavingsSnapshot(
        weekly_current_pct=weekly_current_pct,
        weekly_pp_saved=weekly_pp,
        weekly_counterfactual_pct=weekly_current_pct + weekly_pp,
        weekly_saved_usd=weekly_saved,
        session_current_pct=session_current_pct,
        session_pp_saved=session_pp,
        session_counterfactual_pct=session_current_pct + session_pp,
        session_saved_usd=session_saved,
        calibration_usd_per_pp=usd_per_pp,
        calibration_source=source,
    )


# ── Per-call provider hint (subscription vs API tier) ────────────────────


_SUBSCRIPTION_PROVIDERS = frozenset({"anthropic", "cc"})
_API_PROVIDERS = frozenset({"openai", "gemini", "codex", "groq", "deepseek"})
_FREE_LOCAL_PROVIDERS = frozenset({"ollama", "vllm", "lm_studio"})


def _sum_cost_usd_since_for_provider(
    db_path: Path, since: datetime, provider: str
) -> float:
    """Sum ``cost_usd`` from the ``usage`` table for one provider since
    ``since``. Best-effort: missing DB or schema → 0.0."""
    if not db_path.exists():
        return 0.0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            since_iso = since.strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM usage "
                "WHERE provider = ? AND timestamp >= ?",
                (provider, since_iso),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return 0.0
    except Exception:
        return 0.0


def provider_route_hint(
    provider: str,
    *,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> str | None:
    """Return a short routing-notice suffix specific to ``provider``.

    * **Subscription tier** (``anthropic`` / ``cc``) — show how much of
      the Claude subscription quota is still available, in the same
      weekly + 5h denomination the user sees on claude.ai. Reads from
      the cached usage snapshot.
    * **API tier** (``gemini``, ``openai``, ``codex``, …) — show the
      cumulative cost in the rolling last 30 days for THIS provider, so
      the user can see whether the routing they just got was
      pulling from a budget that is starting to bite.
    * **Free / local** (``ollama``, ``vllm``, ``lm_studio``) — return
      ``None``; no metric makes sense for a zero-cost local call.

    Best-effort: returns ``None`` on any data gap rather than raising.
    The routing notice must never break because a metric isn't ready.
    """
    if provider in _FREE_LOCAL_PROVIDERS:
        return None
    if provider in _SUBSCRIPTION_PROVIDERS:
        from chuzom import state as _state
        cached = _state.get_last_usage()
        if cached is None:
            return None
        weekly_left = max(0.0, 100.0 - cached.weekly_pct * 100.0)
        session_left = max(0.0, 100.0 - cached.session_pct * 100.0)
        return f"wk left {weekly_left:.0f}% · 5h left {session_left:.0f}%"
    if provider in _API_PROVIDERS:
        db = db_path or _default_db_path()
        since = (now or datetime.now(timezone.utc)) - timedelta(days=30)
        total = _sum_cost_usd_since_for_provider(db, since, provider)
        if total <= 0.0:
            return None
        return f"30d on {provider}: ${total:.2f}"
    return None


__all__ = [
    "QuotaSavingsSnapshot",
    "compute_quota_savings",
    "provider_route_hint",
]
