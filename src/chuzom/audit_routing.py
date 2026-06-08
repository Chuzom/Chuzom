"""Tier-1 audit-on-every-turn helper.

Bridges the routing path to the existing
``chuzom.enterprise.audit.AuditLog`` (which was shipped as enterprise
scaffolding in earlier releases but had zero call sites from
``router.route_and_call`` until Tier 1). One row per successful routed
turn, attributed to ``TurnIdentity`` resolved from the operator's env.

Design choices:

* **Lazy module-level singleton.** ``AuditLog()`` opens a SQLite
  connection in its constructor; opening on every call would dominate
  the routing-path latency. The first call to
  :func:`audit_routing_turn` creates the log and caches it for the
  lifetime of the process.
* **Best-effort, fail-open.** A failure here must never break the
  routed turn — the user is owed an answer even if
  ``~/.chuzom/audit.db`` is unwritable. Exceptions are logged and
  swallowed. Tier 3 will introduce a fail-closed mode behind a config
  flag for regulated deployments.
* **Disable via env.** ``CHUZOM_AUDIT_DISABLED=1`` (or any affirmative
  value) skips the audit append entirely. Useful for tests that don't
  exercise auditing and for users who explicitly opt out of local
  audit-DB writes.

The shape of the event is canonical (``AuditEventType.ROUTING_DECISION``)
so the existing CEF/JSON/CSV exporters Just Work.
"""
from __future__ import annotations

import os
import threading
from typing import Any

from chuzom.enterprise.audit import AuditEvent, AuditEventType, AuditLog
from chuzom.identity import TurnIdentity, current_identity
from chuzom.logging import get_logger

log = get_logger("chuzom.audit_routing")


# Tests / opt-out env. Affirmative values match the convention used by
# ``CHUZOM_FS_TOOLS`` (SEC-002) and ``CHUZOM_AGORAGENTIC`` (SEC-003).
_AUDIT_DISABLED_ENV = "CHUZOM_AUDIT_DISABLED"
_AFFIRMATIVE = {"1", "on", "true", "yes"}


# Module-level singleton + a lock to make first-call construction
# thread-safe. ``threading.Lock`` is the right tool here even though
# routing is asyncio-driven: the singleton is shared across whatever
# concurrent tasks happen to call ``audit_routing_turn`` first.
_audit_log: AuditLog | None = None
_audit_log_lock = threading.Lock()


def _audit_disabled() -> bool:
    return (os.environ.get(_AUDIT_DISABLED_ENV) or "").strip().lower() in _AFFIRMATIVE


def _get_audit_log() -> AuditLog:
    """Return the process-wide :class:`AuditLog`, constructing on first call."""
    global _audit_log
    if _audit_log is None:
        with _audit_log_lock:
            if _audit_log is None:  # re-check under lock
                _audit_log = AuditLog()
    return _audit_log


def reset_audit_log_for_tests() -> None:
    """Clear the module-level :class:`AuditLog` singleton.

    Tests use this in their fixtures to force the next call to construct
    a fresh log pointed at the test's ``tmp_path`` ``CHUZOM_AUDIT_PATH``.
    Production code never calls this.
    """
    global _audit_log
    with _audit_log_lock:
        _audit_log = None


def audit_routing_turn(
    *,
    identity: TurnIdentity | None,
    task_type: str,
    complexity: str | None,
    model: str,
    provider: str,
    cost_usd: float,
    cached: bool = False,
    detail_extras: dict[str, Any] | None = None,
) -> None:
    """Append one ``routing.decision`` audit row.

    Called from ``router.route_and_call`` just before every successful
    return path (cached hit + cold-fetched). Identity is resolved from
    env via :func:`chuzom.identity.current_identity` when ``None``.

    Failure modes are swallowed and logged at WARNING — callers must not
    catch exceptions from this function because there should not be
    any. See module docstring for the rationale.
    """
    if _audit_disabled():
        return

    try:
        actor = identity if identity is not None else current_identity()

        event = AuditEvent(
            type=AuditEventType.ROUTING_DECISION,
            actor_id=actor.user_id,
            actor_email=actor.user_email,
            org_id=actor.org_id,
            resource=f"model:{model}",
            action="cached" if cached else "routed",
            detail={
                "task_type": task_type,
                "complexity": complexity or "unknown",
                "model": model,
                "provider": provider,
                "cost_usd": float(cost_usd or 0.0),
                **(detail_extras or {}),
            },
            severity="info",
        )
        _get_audit_log().append(event)
    except Exception as audit_err:  # noqa: BLE001 — see module docstring
        # Best-effort. Never propagate; the routed turn already happened.
        log.warning("audit_write_failed", error=str(audit_err))


__all__ = [
    "audit_routing_turn",
    "reset_audit_log_for_tests",
]
