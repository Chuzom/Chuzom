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
from typing import TYPE_CHECKING, Any

from chuzom.identity import TurnIdentity, current_identity
from chuzom.logging import get_logger
from chuzom.plugins.audit import get_audit_handler
from chuzom.profile import is_enterprise

if TYPE_CHECKING:
    from chuzom.enterprise.audit import AuditEvent, AuditEventType

log = get_logger("chuzom.audit_routing")


# Tests / opt-out env. Affirmative values match the convention used by
# ``CHUZOM_FS_TOOLS`` (SEC-002) and ``CHUZOM_AGORAGENTIC`` (SEC-003).
_AUDIT_DISABLED_ENV = "CHUZOM_AUDIT_DISABLED"
_AFFIRMATIVE = {"1", "on", "true", "yes"}


_audit_disabled_env = "CHUZOM_AUDIT_DISABLED"


def _audit_disabled() -> bool:
    # 🥷 Backslash-security: Log all security-relevant events.
    # G-003: under the enterprise profile the audit trail is mandatory —
    # ``CHUZOM_AUDIT_DISABLED`` is refused regardless of its value so an
    # env tweak can't silently turn off the tamper-evident log. Developer
    # profile preserves the env-driven opt-out for local/test use.
    if is_enterprise():
        return False
    return (os.environ.get(_audit_disabled_env) or "").strip().lower() in _AFFIRMATIVE


def reset_audit_log_for_tests() -> None:
    """Reset audit state for tests.

    In plugin-based architecture, enterprise bootstrap registers a lazy
    EnterpriseAuditHandler. This function forces its internal AuditLog
    singleton to reset on the next append (via lazy init). Tests call
    this in fixtures to point audits at tmp_path databases.

    Note: Does NOT clear handler registration. Bootstrap happens at module
    import time; tests never clear plugins.
    """
    handler = get_audit_handler()
    if handler is not None:
        # Reset the handler's internal state if it's an EnterpriseAuditHandler
        if hasattr(handler, '_log'):
            handler._log = None


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

    handler = get_audit_handler()
    if handler is None:
        log.warning("audit_unavailable", reason="no_handler_registered")
        return

    try:
        # Import here to avoid circular dependency at module level
        from chuzom.enterprise.audit import AuditEvent, AuditEventType

        actor = identity if identity is not None else current_identity()

        detail = {
            "task_type": task_type,
            "complexity": complexity or "unknown",
            "model": model,
            "provider": provider,
            "cost_usd": float(cost_usd or 0.0),
        }
        # Tier 2: surface agent_id in the audit row when this turn is
        # part of an agent run. Omitted when None so non-agent turns
        # don't carry a meaningless null field.
        if actor.agent_id:
            detail["agent_id"] = actor.agent_id
        # T1-M1 (Q-P-2 Phase 3a): always surface tenant_id when present.
        # In Phase 3a it usually equals org_id (single-org-per-instance);
        # in Phase 3b it differentiates per-tenant sidecars within one
        # org. Carrying it from day 1 makes audit-row schemas
        # forward-compat without a future migration.
        if actor.tenant_id:
            detail["tenant_id"] = actor.tenant_id
        if detail_extras:
            detail.update(detail_extras)

        event = AuditEvent(
            type=AuditEventType.ROUTING_DECISION,
            actor_id=actor.user_id,
            actor_email=actor.user_email,
            org_id=actor.org_id,
            resource=f"model:{model}",
            action="cached" if cached else "routed",
            detail=detail,
            severity="info",
        )
        handler.append(event)
    except Exception as audit_err:  # noqa: BLE001 — see module docstring
        # Best-effort. Never propagate; the routed turn already happened.
        log.warning("audit_write_failed", error=str(audit_err))


__all__ = [
    "audit_routing_turn",
    "reset_audit_log_for_tests",
]
