"""Tier-2 / partial OBS-001: structlog contextvars carry routing identity.

``router.route_and_call`` binds ``request_id`` / ``user_id`` / ``org_id``
(and ``agent_id`` when set) into structlog's contextvar layer at the
top of the turn. Every log line emitted by the turn (and any nested
call it makes) then carries those fields automatically — no manual
threading through every ``log.info(..., user_id=..., request_id=...)``
call.

We don't exercise the full ``route_and_call`` here (it talks to live
providers). The smaller assertion: when we call the identity helper +
manually bind the same way ``route_and_call`` does, the contextvar
``get_contextvars()`` snapshot reflects the bound keys. The wiring is
covered by integration tests in ``test_router.py`` once those exist.

See: Tier-2 of the three-tier Phase 2 plan + partial OBS-001 from the
2026-06 audit (full OBS-001 = ``tenant_id`` + full identity = Tier 3).
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Defensive: tests/commands/test_routing.py:9 does
#   sys.modules["structlog"] = MagicMock()
# at module-import time. Depending on pytest's file-collection order
# (which differs between local + CI), our module-level ``import
# structlog`` below can end up bound to that mock instead of the real
# library, and every assertion against ``get_contextvars()`` fails
# because MagicMock.__getitem__ returns another mock. Force a clean
# re-import of the real structlog before we bind it.
if isinstance(sys.modules.get("structlog"), MagicMock):
    del sys.modules["structlog"]

import pytest  # noqa: E402
import structlog  # noqa: E402

from chuzom.identity import TurnIdentity  # noqa: E402


@pytest.fixture(autouse=True)
def clear_structlog_contextvars():
    """Ensure each test starts with a fresh contextvar slate."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


def _bind_like_router(identity: TurnIdentity, request_id: str) -> None:
    """Replicate the bind logic from ``router.route_and_call`` so this
    file can exercise it without booting the full router.

    Keep this in sync with the production binding block — both should
    set the same keys with the same values."""
    payload = {
        "request_id": request_id,
        "user_id": identity.user_id,
        "org_id": identity.org_id,
    }
    if identity.agent_id:
        payload["agent_id"] = identity.agent_id
    structlog.contextvars.bind_contextvars(**payload)


# ── Bind contains the expected keys ──────────────────────────────────────────


def test_bind_includes_request_user_org() -> None:
    ident = TurnIdentity(
        user_id="alice",
        user_email="alice@corp.io",
        org_id="acme",
    )
    _bind_like_router(ident, request_id="abc12345")

    bound = structlog.contextvars.get_contextvars()
    assert bound["request_id"] == "abc12345"
    assert bound["user_id"] == "alice"
    assert bound["org_id"] == "acme"


def test_bind_includes_agent_when_set() -> None:
    ident = TurnIdentity(
        user_id="alice",
        user_email="alice@corp.io",
        org_id="acme",
        agent_id="agno-reviewer",
    )
    _bind_like_router(ident, request_id="abc12345")

    bound = structlog.contextvars.get_contextvars()
    assert bound["agent_id"] == "agno-reviewer"


def test_bind_omits_agent_when_none() -> None:
    """No agent_id key in the contextvar payload when identity has
    None. Downstream JSON log consumers see no spurious null field."""
    ident = TurnIdentity(
        user_id="alice",
        user_email="alice@corp.io",
        org_id="acme",
    )
    _bind_like_router(ident, request_id="abc12345")

    bound = structlog.contextvars.get_contextvars()
    assert "agent_id" not in bound


# ── Contextvars actually flow into structlog log lines ───────────────────────


def test_log_emission_carries_bound_keys(caplog) -> None:
    """End-to-end: bind, then emit a log line, then assert the captured
    log record carries the bound keys.

    ``caplog`` captures stdlib log records; structlog flows through
    stdlib via the ProcessorFormatter. We assert on the keys present
    in the event_dict (kw fields), not the rendered string, so output
    rendering choices don't break the test.
    """
    from chuzom.logging import configure_logging, get_logger

    configure_logging()  # idempotent; module-level _CONFIGURED guard
    log = get_logger("chuzom.test")

    ident = TurnIdentity(
        user_id="alice",
        user_email="alice@corp.io",
        org_id="acme",
        agent_id="agno-reviewer",
    )
    _bind_like_router(ident, request_id="abc12345")

    log.info("test_event", extra_field="present")

    # caplog records carry the structured log message text. We assert
    # that the bound keys appear in some form (the ConsoleRenderer
    # renders them as `key=value` in the message string). Use
    # ``getMessage()`` because ``LogRecord.message`` isn't set until
    # a Formatter calls ``format()`` on the record.
    rendered = " ".join(record.getMessage() for record in caplog.records)
    assert "request_id" in rendered
    assert "user_id" in rendered
    assert "org_id" in rendered
    assert "agent_id" in rendered
    assert "abc12345" in rendered
    assert "alice" in rendered
    assert "acme" in rendered
    assert "agno-reviewer" in rendered
