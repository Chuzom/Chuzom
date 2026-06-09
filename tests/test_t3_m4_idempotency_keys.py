"""T3-M4 (Track-3 agent safety, Medium): idempotency-key dedupe.

Prevents an agent that retries a logical "turn" from producing
duplicate provider costs OR duplicate side effects when the turn's
output drives tool calls downstream.

Pins:

1. **Store contract.** ``IdempotencyStore.store`` / ``lookup`` /
   ``sweep_expired`` behave correctly under hit, miss, expired-row,
   corrupt-payload, and empty-key conditions.

2. **Router integration.** ``route_and_call(idempotency_key=...)``:
   * On miss → dispatch runs, response persisted, response returned.
   * On hit  → dispatch skipped, audit row written with
     ``outcome="idempotency_dedupe"``, cached response returned.
   * Default ``idempotency_key=None`` preserves pre-T3-M4 behaviour.

3. **Fail-open.** Lookup / persist failures are logged and never
   break the success path.

See: Docs/audit/post-remediation/GAP_ANALYSIS.md G-008 (idempotency
slice of the runaway-protection cluster).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from chuzom import router as router_mod
from chuzom.audit_routing import reset_audit_log_for_tests
from chuzom.enterprise.audit import AuditLog
from chuzom.idempotency import (
    IdempotencyStore,
    get_store,
    reset_store_for_tests,
)
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
def isolated_idempotency_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    db = tmp_path / "idem.db"
    monkeypatch.setenv("CHUZOM_IDEMPOTENCY_PATH", str(db))
    reset_store_for_tests()
    yield db
    reset_store_for_tests()


def _mock_response(content: str = "ok", cost: float = 0.005) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        input_tokens=10,
        output_tokens=20,
        cost_usd=cost,
        latency_ms=15.0,
    )


def _detail_of_recent(audit_db: Path, n: int = 1) -> dict:
    rows = AuditLog(db_path=audit_db).recent(limit=n)
    if not rows:
        return {}
    detail = rows[0]["detail"]
    return json.loads(detail) if isinstance(detail, str) else (detail or {})


# ── 1. Store contract ────────────────────────────────────────────────────────


def test_lookup_miss_returns_none(isolated_idempotency_db: Path) -> None:
    s = IdempotencyStore(db_path=isolated_idempotency_db)
    assert s.lookup("never-stored") is None


def test_lookup_hit_returns_stored_response(
    isolated_idempotency_db: Path,
) -> None:
    s = IdempotencyStore(db_path=isolated_idempotency_db)
    r = _mock_response()
    s.store("k1", r)
    out = s.lookup("k1")
    assert out is not None
    assert out.content == r.content
    assert out.model == r.model
    assert out.provider == r.provider
    assert out.cost_usd == pytest.approx(r.cost_usd)


def test_store_empty_key_is_noop(isolated_idempotency_db: Path) -> None:
    s = IdempotencyStore(db_path=isolated_idempotency_db)
    s.store("", _mock_response())  # must not raise
    assert s.lookup("") is None


def test_lookup_expired_row_returns_none_and_sweeps(
    isolated_idempotency_db: Path,
) -> None:
    s = IdempotencyStore(db_path=isolated_idempotency_db)
    # Store with a 0.5s TTL.
    r = _mock_response()
    s.store("k1", r, ttl_seconds=0.5)
    # Sleep just past the TTL.
    time.sleep(0.6)
    assert s.lookup("k1") is None
    # Row removed from the table.
    row = s._conn.execute(
        "SELECT key FROM idempotency_entries WHERE key = ?", ("k1",)
    ).fetchone()
    assert row is None


def test_sweep_expired_bulk_deletes(isolated_idempotency_db: Path) -> None:
    s = IdempotencyStore(db_path=isolated_idempotency_db)
    s.store("k1", _mock_response(), ttl_seconds=0.5)
    s.store("k2", _mock_response(), ttl_seconds=0.5)
    s.store("k3", _mock_response(), ttl_seconds=60.0)  # not expired
    time.sleep(0.6)
    deleted = s.sweep_expired()
    assert deleted == 2
    # k3 still present.
    assert s.lookup("k3") is not None


def test_corrupt_payload_returns_none(isolated_idempotency_db: Path) -> None:
    """A row written with invalid JSON returns None instead of
    propagating a JSONDecodeError out of lookup. Tests the fail-open
    convention."""
    s = IdempotencyStore(db_path=isolated_idempotency_db)
    # Insert raw corrupt row bypassing the helper.
    now = time.time()
    s._conn.execute(
        "INSERT INTO idempotency_entries (key, created_at, expires_at, payload_json) "
        "VALUES (?, ?, ?, ?)",
        ("corrupt", now, now + 60.0, "{not json"),
    )
    s._conn.commit()
    assert s.lookup("corrupt") is None


def test_replace_overwrites_prior_value(isolated_idempotency_db: Path) -> None:
    s = IdempotencyStore(db_path=isolated_idempotency_db)
    s.store("k1", _mock_response(content="v1"))
    s.store("k1", _mock_response(content="v2"))
    out = s.lookup("k1")
    assert out is not None
    assert out.content == "v2"


# ── 2. Router integration ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_call_runs_and_persists(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db: Path,
) -> None:
    """First call with an idempotency_key dispatches normally and
    persists the response under the key."""
    calls: list[dict[str, Any]] = []

    async def _dispatch(**kwargs):
        calls.append(kwargs)
        return _mock_response(content="first")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    resp = await route_and_call(
        task_type=TaskType.QUERY,
        prompt="hello",
        idempotency_key="agent-turn-42",
    )
    assert resp.content == "first"
    assert len(calls) == 1
    # Persisted: a fresh lookup hits.
    out = get_store().lookup("agent-turn-42")
    assert out is not None
    assert out.content == "first"


@pytest.mark.asyncio
async def test_replay_under_same_key_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db: Path,
) -> None:
    """Second call with the same key returns the cached response
    WITHOUT contacting the provider. The mock dispatch fails the test
    if it runs more than once."""
    call_count = {"n": 0}

    async def _dispatch(**kwargs):
        call_count["n"] += 1
        return _mock_response(content="provider-said")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    # First call dispatches.
    await route_and_call(
        task_type=TaskType.QUERY,
        prompt="hello",
        idempotency_key="replay-1",
    )
    assert call_count["n"] == 1

    # Second call short-circuits.
    resp2 = await route_and_call(
        task_type=TaskType.QUERY,
        prompt="hello",
        idempotency_key="replay-1",
    )
    assert resp2.content == "provider-said"
    assert call_count["n"] == 1  # dispatch did NOT run again


@pytest.mark.asyncio
async def test_replay_writes_dedupe_audit_row(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db: Path,
) -> None:
    """The cached return path writes an audit row tagged with
    ``outcome="idempotency_dedupe"`` so the SIEM can see the dedupe."""

    async def _dispatch(**kwargs):
        return _mock_response(content="x")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    await route_and_call(
        task_type=TaskType.QUERY, prompt="hi", idempotency_key="key-A"
    )
    await route_and_call(
        task_type=TaskType.QUERY, prompt="hi", idempotency_key="key-A"
    )

    detail = _detail_of_recent(isolated_audit_db)
    assert detail.get("outcome") == "idempotency_dedupe"
    assert detail.get("idempotency_key") == "key-A"


@pytest.mark.asyncio
async def test_no_key_default_preserves_existing_behaviour(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db: Path,
) -> None:
    """When ``idempotency_key`` is not passed (default None), every
    call dispatches — preserving the pre-T3-M4 contract."""
    call_count = {"n": 0}

    async def _dispatch(**kwargs):
        call_count["n"] += 1
        return _mock_response()

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    await route_and_call(task_type=TaskType.QUERY, prompt="hi")
    await route_and_call(task_type=TaskType.QUERY, prompt="hi")
    assert call_count["n"] == 2  # both calls hit the dispatcher


@pytest.mark.asyncio
async def test_different_keys_do_not_share(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db: Path,
) -> None:
    """Distinct keys are independent — k1's response doesn't satisfy
    a k2 lookup."""
    call_count = {"n": 0}

    async def _dispatch(**kwargs):
        call_count["n"] += 1
        return _mock_response(content=f"call-{call_count['n']}")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    r1 = await route_and_call(
        task_type=TaskType.QUERY, prompt="a", idempotency_key="k1"
    )
    r2 = await route_and_call(
        task_type=TaskType.QUERY, prompt="b", idempotency_key="k2"
    )
    assert r1.content == "call-1"
    assert r2.content == "call-2"
    assert call_count["n"] == 2


# ── 3. Fail-open ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lookup_failure_does_not_break_turn(
    monkeypatch: pytest.MonkeyPatch,
    isolated_audit_db: Path,
    isolated_idempotency_db: Path,
) -> None:
    """A broken IdempotencyStore.lookup must not propagate. The turn
    proceeds as if no key were present."""

    async def _dispatch(**kwargs):
        return _mock_response(content="from-provider")

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _dispatch)

    # Patch the store getter to return a sabotaged store.
    class _BadStore:
        def lookup(self, key: str) -> Any:
            raise RuntimeError("disk full")

        def store(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("disk full")

    monkeypatch.setattr(router_mod, "_get_idempotency_store", lambda: _BadStore())

    resp = await route_and_call(
        task_type=TaskType.QUERY, prompt="hi", idempotency_key="any-key"
    )
    assert resp.content == "from-provider"
