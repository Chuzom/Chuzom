"""T4-M1 (Track-4 cost+privacy, Medium): redaction wired into routing.

Closes the first slice of G-013 (\\`\\`enterprise/redaction.py\\`\\` had zero
callers from the routing path). The router now scrubs PII from the
prompt before dispatch when \\`\\`CHUZOM_REDACTION=on\\`\\` is set, and the
success audit row carries \\`\\`detail.redactions={pii: N, ...}\\`\\` counts so
operators can observe scrub rates without persisting any PII.

Pins:

1. **Env switch.** Off (default) → no-op (prompt unchanged, no
   redactions in audit). On → prompt is scrubbed; counts recorded.
2. **Provider sees the scrubbed prompt.** The dispatcher receives the
   redacted text — pinned by inspecting the kwargs the mocked
   \\`\\`_dispatch_model_loop\\`\\` was called with.
3. **Audit row carries counts.** Successful turns with redactions
   write \\`\\`detail.redactions\\`\\` with per-pattern hit counts.
4. **No PII pinned in tests** — assertions are on counts + the absence
   of the sensitive substring in the post-redaction prompt.
5. **Fail-open.** A broken redactor does NOT break the turn — the
   original prompt is sent and the call proceeds.

See: Docs/audit/post-remediation/GAP_ANALYSIS.md G-013.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# Import enterprise to trigger redactor bootstrap (C-1 plugin seam)
import chuzom.enterprise  # noqa: F401

from chuzom import router as router_mod
from chuzom.audit_routing import reset_audit_log_for_tests
from chuzom.enterprise.audit import AuditLog
from chuzom.idempotency import reset_store_for_tests
from chuzom.redaction_routing import _redaction_enabled, maybe_redact
from chuzom.router import route_and_call
from chuzom.types import LLMResponse, TaskType


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "audit.db"
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(db))
    monkeypatch.delenv("CHUZOM_AUDIT_DISABLED", raising=False)
    reset_audit_log_for_tests()
    yield db
    reset_audit_log_for_tests()


@pytest.fixture
def isolated_idempotency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHUZOM_IDEMPOTENCY_PATH", str(tmp_path / "idem.db"))
    reset_store_for_tests()
    yield
    reset_store_for_tests()


@pytest.fixture
def clean_redaction_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CHUZOM_REDACTION", raising=False)


def _ok_response() -> LLMResponse:
    return LLMResponse(
        content="ok",
        model="m",
        provider="p",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.001,
        latency_ms=10.0,
    )


def _detail_of_recent(audit_db: Path) -> dict:
    rows = AuditLog(db_path=audit_db).recent(limit=1)
    if not rows:
        return {}
    detail = rows[0]["detail"]
    return json.loads(detail) if isinstance(detail, str) else (detail or {})


# Test fixtures use SAFE-LOOKING but realistic-format strings that the
# redactor will pattern-match. None of these are real credentials.
_FAKE_EMAIL = "alice@example.com"
_FAKE_OPENAI_KEY = "sk-abcdef1234567890abcdef1234567890"


# ── 1. Env switch ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("on", True),
        ("ON", True),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("strict", True),
        ("off", False),
        ("", False),
        ("garbage", False),
    ],
)
def test_redaction_env_truth_table(
    clean_redaction_env, monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv("CHUZOM_REDACTION", value)
    assert _redaction_enabled() is expected


def test_redaction_env_unset_defaults_off(clean_redaction_env) -> None:
    assert _redaction_enabled() is False


# ── 2. maybe_redact pure function ────────────────────────────────────────────


def test_maybe_redact_off_returns_prompt_unchanged(clean_redaction_env) -> None:
    prompt = f"email me at {_FAKE_EMAIL}"
    out, counts = maybe_redact(prompt)
    assert out == prompt
    assert counts == {}


def test_maybe_redact_on_scrubs_email(
    clean_redaction_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHUZOM_REDACTION", "on")
    prompt = f"email me at {_FAKE_EMAIL}"
    out, counts = maybe_redact(prompt)
    # PII string is gone; marker is present.
    assert _FAKE_EMAIL not in out
    assert "[REDACTED:email]" in out
    assert counts.get("email") == 1


def test_maybe_redact_on_scrubs_multiple_pattern_types(
    clean_redaction_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHUZOM_REDACTION", "on")
    prompt = f"contact {_FAKE_EMAIL} key {_FAKE_OPENAI_KEY}"
    out, counts = maybe_redact(prompt)
    assert _FAKE_EMAIL not in out
    assert _FAKE_OPENAI_KEY not in out
    # Multiple pattern types counted.
    assert "email" in counts
    assert "openai_key" in counts


def test_maybe_redact_on_with_no_pii_returns_unchanged(
    clean_redaction_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean prompt is returned unchanged; no patterns fire."""
    monkeypatch.setenv("CHUZOM_REDACTION", "on")
    prompt = "what is 1 + 1"
    out, counts = maybe_redact(prompt)
    assert out == prompt
    assert counts == {}


# ── 3. End-to-end: provider sees scrubbed prompt ─────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_receives_redacted_prompt_when_on(
    clean_redaction_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency,
) -> None:
    """When CHUZOM_REDACTION=on, the prompt the dispatcher receives
    has the PII scrubbed."""
    monkeypatch.setenv("CHUZOM_REDACTION", "on")

    captured: list[str] = []

    async def _capture_dispatch(**kwargs: Any) -> LLMResponse:
        captured.append(kwargs.get("prompt", ""))
        return _ok_response()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _capture_dispatch)

    sensitive = f"please review code by {_FAKE_EMAIL}"
    await route_and_call(task_type=TaskType.QUERY, prompt=sensitive)

    assert len(captured) == 1
    assert _FAKE_EMAIL not in captured[0]
    assert "[REDACTED:email]" in captured[0]


@pytest.mark.asyncio
async def test_dispatcher_receives_original_prompt_when_off(
    clean_redaction_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency,
) -> None:
    """Default off: prompt passes through unchanged."""
    # No CHUZOM_REDACTION env set → off.
    captured: list[str] = []

    async def _capture_dispatch(**kwargs: Any) -> LLMResponse:
        captured.append(kwargs.get("prompt", ""))
        return _ok_response()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _capture_dispatch)

    sensitive = f"hello {_FAKE_EMAIL}"
    await route_and_call(task_type=TaskType.QUERY, prompt=sensitive)

    assert captured[0] == sensitive


# ── 4. Audit row carries redaction counts ────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_row_carries_redaction_counts(
    clean_redaction_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency,
) -> None:
    monkeypatch.setenv("CHUZOM_REDACTION", "on")

    async def _dispatch(**kwargs: Any) -> LLMResponse:
        return _ok_response()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    await route_and_call(
        task_type=TaskType.QUERY,
        prompt=f"ping {_FAKE_EMAIL} key {_FAKE_OPENAI_KEY}",
    )

    detail = _detail_of_recent(isolated_audit_db)
    assert "redactions" in detail
    redactions = detail["redactions"]
    assert redactions.get("email") == 1
    assert redactions.get("openai_key") == 1


@pytest.mark.asyncio
async def test_audit_row_omits_redactions_when_clean_prompt(
    clean_redaction_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency,
) -> None:
    """A PII-free prompt under CHUZOM_REDACTION=on must NOT carry a
    spurious empty redactions field — keeps the audit schema clean
    for non-PII workloads."""
    monkeypatch.setenv("CHUZOM_REDACTION", "on")

    async def _dispatch(**kwargs: Any) -> LLMResponse:
        return _ok_response()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    await route_and_call(
        task_type=TaskType.QUERY, prompt="what is 1 + 1"
    )
    detail = _detail_of_recent(isolated_audit_db)
    assert "redactions" not in detail


@pytest.mark.asyncio
async def test_audit_row_omits_redactions_when_off(
    clean_redaction_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency,
) -> None:
    """Off mode never writes a redactions field — pinning the
    backwards-compat invariant."""

    async def _dispatch(**kwargs: Any) -> LLMResponse:
        return _ok_response()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    await route_and_call(
        task_type=TaskType.QUERY, prompt=f"hi {_FAKE_EMAIL}"
    )
    detail = _detail_of_recent(isolated_audit_db)
    assert "redactions" not in detail


# ── 5. Fail-open ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redaction_failure_does_not_break_turn(
    clean_redaction_env,
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency,
) -> None:
    """A broken redactor must not break the turn — the original
    prompt is sent and the call proceeds."""
    from chuzom.plugins.redaction import Redactor, RedactionResult, register_redactor

    monkeypatch.setenv("CHUZOM_REDACTION", "on")

    class BrokenRedactor(Redactor):
        def redact_prompt(self, prompt: str) -> RedactionResult:
            raise RuntimeError("redactor died")

    # Register a broken redactor; maybe_redact swallows the exception and returns original.
    register_redactor(BrokenRedactor())

    captured: list[str] = []

    async def _dispatch(**kwargs: Any) -> LLMResponse:
        captured.append(kwargs.get("prompt", ""))
        return _ok_response()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    original = f"hi {_FAKE_EMAIL}"
    resp = await route_and_call(task_type=TaskType.QUERY, prompt=original)
    assert resp.content == "ok"
    # On fail-open the dispatcher receives the original unmodified prompt.
    assert captured[0] == original
