"""Audit handler plugin interface and registry.

Core defines an AuditHandler Protocol; enterprise registers a concrete implementation.
Audit routing calls get_audit_handler() and fails open if no handler is registered.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chuzom.enterprise.audit import AuditEvent


class AuditHandler(Protocol):
    """Plugin interface for audit logging."""

    def append(self, event: AuditEvent) -> None:
        """Append an audit event to the log."""
        ...


# Runtime registry for audit handler implementations
_HANDLERS: dict[str, AuditHandler] = {}
_DEFAULT = "default"


def register_audit_handler(handler: AuditHandler, name: str = _DEFAULT) -> None:
    """Register an audit handler implementation."""
    _HANDLERS[name] = handler


def get_audit_handler(name: str = _DEFAULT) -> AuditHandler | None:
    """Get the registered audit handler, or None if not registered."""
    return _HANDLERS.get(name)


__all__ = [
    "AuditHandler",
    "register_audit_handler",
    "get_audit_handler",
]
