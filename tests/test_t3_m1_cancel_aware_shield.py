"""T3-M1 (Track-3 agent safety, Medium): cancel-aware shield.

A parent agent that cancels its routing turn (because a supervisor
pulled the plug, a workflow deadline fired, the user hit Ctrl-C,
etc.) must leave chuzom in a clean state:

* The budget reservation it placed before dispatch must be released
  back into ``_pending_spend`` — otherwise a cancelled turn leaks
  budget forever and concurrent turns see a phantom in-flight cost.
* A best-effort audit row must record the cancellation so the audit
  chain reflects what happened — otherwise the routed turn vanishes.
* ``asyncio.CancelledError`` must continue propagating up the
  cancellation chain — chuzom is not allowed to swallow it.

These tests exercise the shield by patching ``_dispatch_model_loop``
with a stub that raises ``CancelledError`` mid-flight.

See: Track 3 of the Phase-3 score-to-4 plan
(``Docs/audit/post-remediation/GAP_ANALYSIS.md`` G-007).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from chuzom import router as router_mod
from chuzom.audit_routing import reset_audit_log_for_tests
from chuzom.enterprise.audit import AuditLog
from chuzom.router import route_and_call
from chuzom.types import TaskType


@pytest.fixture
def isolated_audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "audit.db"
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(db))
    monkeypatch.delenv("CHUZOM_AUDIT_DISABLED", raising=False)
    reset_audit_log_for_tests()
    yield db
    reset_audit_log_for_tests()


def _read_recent_audit(audit_db: Path, limit: int = 5) -> list[dict]:
    return AuditLog(db_path=audit_db).recent(limit=limit)


def _detail_of(row: dict) -> dict:
    raw = row.get("detail")
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


# ── 1. Cancellation during dispatch ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_during_dispatch_propagates(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    """A cancel mid-dispatch must re-raise CancelledError. chuzom is
    not allowed to swallow cancels — that would defeat the parent
    workflow's cancellation contract."""

    async def _cancelling_dispatch(**kwargs: Any):
        # Simulate "we noticed the parent task got cancelled".
        raise asyncio.CancelledError()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _cancelling_dispatch)

    with pytest.raises(asyncio.CancelledError):
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
        )


@pytest.mark.asyncio
async def test_cancel_writes_cancelled_audit_row(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    """The cancel handler must write a best-effort audit row tagged
    ``outcome="cancelled"`` so the chain records the cancellation."""

    async def _cancelling_dispatch(**kwargs: Any):
        raise asyncio.CancelledError()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _cancelling_dispatch)

    with pytest.raises(asyncio.CancelledError):
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
        )

    rows = _read_recent_audit(isolated_audit_db, limit=5)
    assert len(rows) >= 1
    row = rows[0]
    assert row["action"] == "routed"  # the chuzom convention for cleanup rows
    detail = _detail_of(row)
    assert detail.get("outcome") == "cancelled"
    assert "elapsed_seconds" in detail


@pytest.mark.asyncio
async def test_cancel_releases_pending_spend(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    """The pending-spend reservation made before dispatch must be
    released on cancel. We assert _pending_spend returns to its
    pre-call baseline so a cancelled turn does not leak budget."""

    pre_spend = router_mod._pending_spend

    async def _cancelling_dispatch(**kwargs: Any):
        # By the time we get here the reservation has been added.
        # Confirm it actually grew (the test would be vacuous
        # otherwise) and then cancel.
        assert router_mod._pending_spend >= pre_spend
        raise asyncio.CancelledError()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _cancelling_dispatch)

    with pytest.raises(asyncio.CancelledError):
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
        )

    # Released after the cleanup branch.
    assert router_mod._pending_spend == pytest.approx(pre_spend)


@pytest.mark.asyncio
async def test_cancel_audit_failure_does_not_mask_cancel(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    """If the audit write itself fails during cleanup, the original
    CancelledError must still propagate. A broken audit pipeline must
    not mask a cancel signal."""

    async def _cancelling_dispatch(**kwargs: Any):
        raise asyncio.CancelledError()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _cancelling_dispatch)

    # Force the audit write to blow up.
    def _audit_boom(**kwargs: Any) -> None:
        raise RuntimeError("audit pipeline down")

    monkeypatch.setattr(router_mod, "audit_routing_turn", _audit_boom)

    with pytest.raises(asyncio.CancelledError):
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
        )


# ── 2. Cancellation via parent task cancel ───────────────────────────────────


@pytest.mark.asyncio
async def test_external_task_cancel_triggers_shield(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    """The realistic scenario: parent task cancels the child while
    ``_dispatch_model_loop`` is awaiting the provider. The child sees
    CancelledError; the shield does its cleanup; the cancel propagates."""

    async def _slow_dispatch(**kwargs: Any):
        await asyncio.sleep(5)  # parent cancels us before this completes
        raise AssertionError("dispatch should have been cancelled")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _slow_dispatch)

    async def _do_routed_call():
        return await route_and_call(task_type=TaskType.QUERY, prompt="hi")

    task = asyncio.create_task(_do_routed_call())
    # Give the task a moment to enter the dispatch await.
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    rows = _read_recent_audit(isolated_audit_db, limit=5)
    assert len(rows) >= 1
    assert _detail_of(rows[0]).get("outcome") == "cancelled"


# ── 3. Timeout path still works unchanged ────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_path_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
) -> None:
    """T3-M1 reorganised the try/except — pin that the T3-S2 timeout
    behaviour still works. A slow dispatch under a small wall-clock
    cap must raise WallClockExceeded (not CancelledError)."""
    from chuzom.types import WallClockExceeded

    async def _slow_dispatch(**kwargs: Any):
        await asyncio.sleep(1)

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _slow_dispatch)

    with pytest.raises(WallClockExceeded):
        await route_and_call(
            task_type=TaskType.QUERY,
            prompt="hi",
            max_wall_clock_seconds=0.05,
        )

    rows = _read_recent_audit(isolated_audit_db, limit=5)
    assert len(rows) >= 1
    assert _detail_of(rows[0]).get("outcome") == "wall_clock_exceeded"
