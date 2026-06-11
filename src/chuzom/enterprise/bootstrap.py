"""Enterprise bootstrap — register implementations at runtime.

Called from enterprise.__init__ to install enterprise redactor into the
core plugin registry. Keeps enterprise code explicit and observable.
"""
from __future__ import annotations

from chuzom.enterprise.redaction import RedactionPolicy, redact_prompt
from chuzom.plugins.redaction import RedactionResult, Redactor, register_redactor


class EnterpriseRedactor(Redactor):
    """Enterprise implementation of Redactor protocol."""

    def __init__(self, policy: RedactionPolicy | None = None):
        self.policy = policy or RedactionPolicy.default()

    def redact_prompt(self, prompt: str) -> RedactionResult:
        """Redact using the enterprise redaction policy."""
        return redact_prompt(prompt, policy=self.policy)


def bootstrap() -> None:
    """Register enterprise redactor into the core plugin registry."""
    register_redactor(EnterpriseRedactor())


__all__ = ["bootstrap", "EnterpriseRedactor"]
