"""T3-M2 (Track-3 agent safety, Medium): deadline propagation.

Parent workflows set an absolute ``time.monotonic()`` deadline and
pass it verbatim into every nested ``route_and_call``. Each turn:

* Refuses to start work if the deadline has already passed (raises
  ``DeadlineExceeded`` before any provider is contacted).
* Caps its dispatch wall-clock at ``min(deadline_remaining,
  max_wall_clock_seconds)`` — the tighter constraint wins.
* On timeout, distinguishes deadline-driven (``DeadlineExceeded``)
  from wall-clock-driven (``WallClockExceeded``) so callers know
  whether to retry (wall-clock = a different model may succeed;
  deadline = stop the workflow).

See: Docs/audit/post-remediation/GAP_ANALYSIS.md G-007.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from pathlib import Path
from typing import Any

import pytest

from chuzom import router as router_mod
from chuzom.audit_routing import reset_audit_log_for_tests
from chuzom.enterprise.audit import AuditLog
from chuzom.idempotency import reset_store_for_tests
from chuzom.router import route_and_call
from chuzom.types import (
    DeadlineExceeded,
    LLMResponse,
    TaskType,
    WallClockExceeded,
)


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
def isolated_idempotency_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setenv("CHUZOM_IDEMPOTENCY_PATH", str(tmp_path / "idem.db"))
    reset_store_for_tests()
    yield
    reset_store_for_tests()


def _ok_response(content: str = "ok") -> LLMResponse:
    return LLMResponse(
        content=content,
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


# ── 1. Signature + exception shape ───────────────────────────────────────────


def test_signature_accepts_deadline_monotonic() -> None:
    sig = inspect.signature(route_and_call)
    assert "deadline_monotonic" in sig.parameters
    p = sig.parameters["deadline_monotonic"]
    assert p.default is None
    assert p.kind is inspect.Parameter.KEYWORD_ONLY


def test_deadline_exceeded_is_a_timeout_error() -> None:
    """Generic ``try/except TimeoutError`` must catch both this and
    ``WallClockExceeded`` — operators who don't care about the
    distinction can keep using the stdlib idiom."""
    assert issubclass(DeadlineExceeded, TimeoutError)


def test_deadline_exceeded_carries_attributes() -> None:
    exc = DeadlineExceeded(
        "x", deadline_monotonic=100.5, over_by_seconds=2.0
    )
    assert exc.deadline_monotonic == pytest.approx(100.5)
    assert exc.over_by_seconds == pytest.approx(2.0)


def test_deadline_exceeded_over_by_optional() -> None:
    exc = DeadlineExceeded("x", deadline_monotonic=100.0)
    assert exc.over_by_seconds is None


# ── 2. Pre-flight: past-deadline refuses to start ────────────────────────────


@pytest.mark.asyncio
async def test_past_deadline_raises_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db,
) -> None:
    """A deadline already in the past must raise immediately — no
    provider contacted, no idempotency lookup, no budget reservation."""

    async def _should_never_run(**kwargs: Any) -> LLMResponse:
        raise AssertionError("dispatch must not be reached")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _should_never_run)

    past_deadline = time.monotonic() - 1.0  # 1s in the past
    with pytest.raises(DeadlineExceeded) as excinfo:
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
            deadline_monotonic=past_deadline,
        )
    assert excinfo.value.deadline_monotonic == pytest.approx(past_deadline)
    assert excinfo.value.over_by_seconds is not None
    assert excinfo.value.over_by_seconds >= 0.5


@pytest.mark.asyncio
async def test_past_deadline_writes_audit_row(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db,
) -> None:
    async def _never(**kwargs: Any) -> LLMResponse:
        raise AssertionError("dispatch must not be reached")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _never)

    past_deadline = time.monotonic() - 0.5
    with pytest.raises(DeadlineExceeded):
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
            deadline_monotonic=past_deadline,
        )

    detail = _detail_of_recent(isolated_audit_db)
    assert detail.get("outcome") == "deadline_exceeded"
    assert detail.get("deadline_monotonic") == pytest.approx(past_deadline)


# ── 3. Mid-flight: deadline fires during dispatch ────────────────────────────


@pytest.mark.asyncio
async def test_deadline_fires_during_slow_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db,
) -> None:
    """A dispatch that takes longer than the deadline remaining must
    raise DeadlineExceeded (NOT WallClockExceeded), since the deadline
    is the binding constraint."""

    async def _slow(**kwargs: Any) -> LLMResponse:
        await asyncio.sleep(5)
        raise AssertionError("should have timed out")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _slow)

    deadline = time.monotonic() + 0.1  # 100ms from now
    with pytest.raises(DeadlineExceeded):
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
            deadline_monotonic=deadline,
        )


@pytest.mark.asyncio
async def test_wall_clock_fires_when_tighter_than_deadline(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db,
) -> None:
    """When max_wall_clock_seconds is tighter than the deadline, the
    timeout is wall-clock-driven and WallClockExceeded fires."""

    async def _slow(**kwargs: Any) -> LLMResponse:
        await asyncio.sleep(5)

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _slow)

    # Deadline far in the future; wall-clock cap tight.
    far_deadline = time.monotonic() + 60.0
    with pytest.raises(WallClockExceeded):
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
            deadline_monotonic=far_deadline,
            max_wall_clock_seconds=0.05,
        )


@pytest.mark.asyncio
async def test_min_cap_wins_when_both_set(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db,
) -> None:
    """With both deadline (50ms remaining) AND max_wall_clock_seconds
    (5s), the deadline wins — DeadlineExceeded raised."""

    async def _slow(**kwargs: Any) -> LLMResponse:
        await asyncio.sleep(2)

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _slow)

    near_deadline = time.monotonic() + 0.05
    with pytest.raises(DeadlineExceeded):
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
            deadline_monotonic=near_deadline,
            max_wall_clock_seconds=5.0,
        )


# ── 4. Happy path: deadline far enough → success ────────────────────────────


@pytest.mark.asyncio
async def test_loose_deadline_allows_success(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db,
) -> None:
    async def _quick(**kwargs: Any) -> LLMResponse:
        await asyncio.sleep(0.01)
        return _ok_response("done")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _quick)

    resp = await route_and_call(
        task_type=TaskType.QUERY,
        prompt="hi",
        deadline_monotonic=time.monotonic() + 60.0,
    )
    assert resp.content == "done"


@pytest.mark.asyncio
async def test_default_none_preserves_existing_contract(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db,
) -> None:
    """deadline_monotonic=None must NOT affect routing behaviour."""

    async def _quick(**kwargs: Any) -> LLMResponse:
        return _ok_response("default-ok")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _quick)

    resp = await route_and_call(task_type=TaskType.QUERY, prompt="hi")
    assert resp.content == "default-ok"
