"""F4: per-identity quota enforcement at the routing chokepoint.

Bridges :class:`chuzom.enterprise.quotas.QuotaTracker` into ``route_and_call``.
The tracker shipped fully-formed (its docstring even says "the router calls
``would_exceed()`` BEFORE dispatching") but had **zero callers from the routing
path** — per-identity caps were configurable via the admin API yet never
enforced at routing time. This module closes that gap.

Mirrors :mod:`chuzom.rbac_routing` / :mod:`chuzom.audit_routing`: a thin,
enterprise-gated wrapper with three modes via ``CHUZOM_QUOTA_MODE``:

* **off** — no-op (the pre-F4 behaviour; developer-profile default).
* **warn** — log + audit a breach signal but allow the turn (dual-write window).
* **strict** — raise :class:`QuotaExceeded` BEFORE any reservation / dispatch /
  provider call. The caller pays nothing for the deny.

G-001-style default flip: when ``CHUZOM_QUOTA_MODE`` is unset, enterprise profile
defaults to **strict**, developer profile to **off**. An explicit value always
wins so an operator can canary in ``warn`` before flipping to ``strict``.

Scope note: enforced for the **user** scope today. ``TurnIdentity`` does not yet
carry ``team_id``, so team-scope quota is a follow-up (thread team_id through
identity resolution, then add a second ``would_exceed("team", ...)`` check).

🥷 Backslash-Security: using vibe-coding rules for secured Authentication & Authorization
"""
from __future__ import annotations

import os
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_QUOTA_MODE_ENV = "CHUZOM_QUOTA_MODE"
_STRICT_VALUES = {"strict", "hard"}
_WARN_VALUES = {"warn", "soft", "shadow"}

# Lazy singleton tracker (mirrors rbac/audit bridges). Tests inject their own.
_tracker = None  # type: ignore[var-annotated]


def _resolve_mode() -> str:
    """Return ``'off'`` / ``'warn'`` / ``'strict'`` from env + profile."""
    raw = (os.environ.get(_QUOTA_MODE_ENV) or "").strip().lower()
    if raw in _STRICT_VALUES:
        return "strict"
    if raw in _WARN_VALUES:
        return "warn"
    if raw == "off":
        return "off"
    # Unset / unrecognised → profile-driven default.
    from chuzom.profile import is_enterprise
    return "strict" if is_enterprise() else "off"


def _get_tracker():
    """Resolve the process-wide QuotaTracker (cross-thread safe)."""
    global _tracker
    if _tracker is None:
        from chuzom.enterprise.quotas import QuotaTracker
        _tracker = QuotaTracker(check_same_thread=False)
    return _tracker


def check_quota(
    identity: Any,
    prospective_cost_usd: float = 0.0,
    *,
    tracker=None,
) -> tuple[str, bool, dict]:
    """Pre-dispatch quota gate. Returns ``(mode, breached, info)``.

    ``breached`` is True only for a HARD cap breach (per ``QuotaTracker``
    semantics); ``info`` carries the cap/consumed/period for the audit row and
    the structured refusal. With the default ``prospective_cost_usd=0.0`` this
    refuses a user already over their cap; the post-success ``record_consumption``
    advances the accumulator so the next over-cap call is refused.
    """
    mode = _resolve_mode()
    if mode == "off":
        return ("off", False, {})
    user_id = getattr(identity, "user_id", None)
    if not user_id:
        return (mode, False, {})
    t = tracker or _get_tracker()
    try:
        breached, info = t.would_exceed("user", user_id, prospective_cost_usd)
    except Exception as exc:  # never let a quota-store hiccup break routing
        log.warning("quota_check_failed", error=str(exc))
        return (mode, False, {})
    return (mode, breached, info)


def raise_quota_denied(info: dict):
    """Build the :class:`QuotaExceeded` to raise on a strict breach."""
    from chuzom.enterprise.quotas import QuotaExceeded

    return QuotaExceeded(
        scope=info.get("scope", "user"),
        identifier=info.get("identifier", "?"),
        period=info.get("period", "daily"),
        cap_usd=info.get("cap_usd", 0.0),
        consumed_usd=info.get("consumed_usd", 0.0),
        proposed_usd=info.get("proposed_usd", 0.0),
    )


def record_consumption(
    identity: Any,
    actual_cost_usd: float,
    *,
    tracker=None,
) -> None:
    """Record real per-identity spend after a successful, paid turn.

    Enterprise-gated and a no-op for off-mode, missing identity, or zero cost
    (cached / local / free turns spend nothing). Failures are logged, never
    raised — quota accounting must not break a turn the caller already received.
    """
    if _resolve_mode() == "off":
        return
    if not actual_cost_usd or actual_cost_usd <= 0:
        return
    user_id = getattr(identity, "user_id", None)
    if not user_id:
        return
    t = tracker or _get_tracker()
    try:
        t.consume("user", user_id, float(actual_cost_usd))
    except Exception as exc:
        log.warning("quota_consume_failed", error=str(exc))
