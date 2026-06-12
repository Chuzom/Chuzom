"""Enterprise bootstrap — register implementations at runtime.

Called from enterprise.__init__ to install enterprise implementations into the
core plugin registry. Keeps enterprise code explicit and observable.

Currently registers:
- Redactor (for prompt PII redaction)
- AuditHandler (for immutable audit logging)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chuzom.enterprise.redaction import RedactionPolicy, redact_prompt
from chuzom.plugins.redaction import RedactionResult, Redactor, register_redactor
from chuzom.plugins.audit import AuditHandler, register_audit_handler

if TYPE_CHECKING:
    from chuzom.enterprise.audit import AuditEvent


class EnterpriseRedactor(Redactor):
    """Enterprise implementation of Redactor protocol."""

    def __init__(self, policy: RedactionPolicy | None = None):
        self.policy = policy or RedactionPolicy.default()

    def redact_prompt(self, prompt: str) -> RedactionResult:
        """Redact using the enterprise redaction policy."""
        return redact_prompt(prompt, policy=self.policy)


class EnterpriseAuditHandler(AuditHandler):
    """Enterprise implementation of AuditHandler protocol.

    Lazily constructs AuditLog on first append to avoid initialization
    failures during bootstrap if the audit database is not yet available.
    """

    def __init__(self):
        self._log = None

    def append(self, event: AuditEvent) -> None:
        """Append event to the enterprise audit log."""
        if self._log is None:
            from chuzom.enterprise.audit import AuditLog
            self._log = AuditLog()
        self._log.append(event)


def bootstrap() -> None:
    """Register enterprise plugins into the core plugin registry."""
    register_redactor(EnterpriseRedactor())
    register_audit_handler(EnterpriseAuditHandler())


__all__ = ["bootstrap", "EnterpriseRedactor", "EnterpriseAuditHandler"]
