"""T4-M1: prompt redaction at the routing chokepoint.

Closes the first slice of G-013 (``enterprise/redaction.py`` shipped
but had zero callers from the routing path). When the
``CHUZOM_REDACTION`` env switch is set to ``on``, the prompt that
``route_and_call`` receives is scrubbed via
``enterprise.redaction.redact_prompt`` **before** it reaches any
provider. The audit row carries per-pattern hit counts so operators
can observe the scrub rate without persisting any PII.

Modes via ``CHUZOM_REDACTION``:

* **off** (default) — no-op. Preserves pre-T4-M1 behaviour (prompt
  passes through unchanged). Operators who haven't reviewed which
  patterns chuzom redacts must opt in explicitly.
* **on** — every routed turn's prompt is redacted before dispatch.
  Audit detail records ``redactions={pii: N, email: N, ...}``.

The redaction policy is the ``RedactionPolicy.default()`` from
``enterprise.redaction``; per-tenant / per-classification policies
land in T4-M2 (per-classification provider allow-list) and T4-XL1
(full ZDR plumbing).

See: Docs/audit/post-remediation/GAP_ANALYSIS.md G-013.
"""
from __future__ import annotations

import os

from chuzom.enterprise.redaction import RedactionResult, redact_prompt
from chuzom.logging import get_logger
from chuzom.profile import is_enterprise

log = get_logger("chuzom.redaction_routing")


_REDACTION_ENV = "CHUZOM_REDACTION"
_AFFIRMATIVE = {"on", "1", "true", "yes", "strict"}


def _redaction_enabled() -> bool:
    # G-012: an explicit affirmative env always enables; an explicit
    # non-affirmative value (e.g. ``off``) always disables — including
    # the documented enterprise operator opt-out. Only when the env is
    # unset does the deployment profile decide: enterprise defaults
    # redaction on, developer keeps it off.
    raw = (os.environ.get(_REDACTION_ENV) or "").strip().lower()
    if raw in _AFFIRMATIVE:
        return True
    if raw == "" and is_enterprise():
        return True
    return False


def maybe_redact(prompt: str) -> tuple[str, dict[str, int]]:
    """Return ``(scrubbed_prompt, counts)`` per the env switch.

    * Off (default) → returns the prompt unchanged and an empty
      counts dict. The caller can avoid extra audit-detail entries by
      checking ``if counts: ...``.
    * On → calls ``redact_prompt`` with the default policy. The
      redacted prompt is what the provider sees; the counts dict
      records how many of each pattern type fired.

    Failures of the redaction policy are logged at WARNING and the
    original prompt is returned unchanged (fail-open) so a broken
    redactor cannot break the routing path. Operators who need
    fail-closed guarantees should refuse to start chuzom without a
    valid redaction policy at boot time, not bolt it onto every turn.
    """
    if not _redaction_enabled():
        return prompt, {}
    try:
        result: RedactionResult = redact_prompt(prompt)
    except Exception as err:  # noqa: BLE001 — fail-open
        log.warning("redaction_failed", error=str(err))
        return prompt, {}
    return result.text, dict(result.counts)


__all__ = [
    "maybe_redact",
]
