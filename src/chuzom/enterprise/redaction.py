"""Back-compat shim — the redactor now lives in the CORE package.

WHY IT MOVED
============

Nothing in this module was ever enterprise-specific: it is a pattern table, a
Luhn check, and a layered scrub. But living under ``enterprise/`` meant it did
not ship, because ``enterprise/`` is excluded from public distributions.

Five persistence paths imported ``persist_redact`` from here — ``result_cache``,
``semantic_cache``, ``idempotency``, ``context``, ``session_store`` — each
inside a ``try/except`` that falls back to ``secret_scrubber.scrub_text``. So on
every real install the import failed, the fallback ran, and the fallback does
not carry these patterns. Measured against the PUBLISHED package: JWTs, Slack
tokens, emails, SSNs, phone numbers, credit-card numbers and prose secrets all
passed through to disk, 7 of 7.

The suite never caught it because the development tree HAS ``enterprise/``. The
tests exercised the one configuration users never run.

This shim keeps existing enterprise imports working. New code should import
``chuzom.persist_redaction`` directly.
"""

from __future__ import annotations

from chuzom.persist_redaction import (  # noqa: F401
    RedactionPolicy,
    persist_redact,
    redact_prompt,
)

__all__ = ["RedactionPolicy", "persist_redact", "redact_prompt"]
