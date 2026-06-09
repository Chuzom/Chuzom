"""T2-L1: distributed-safe budget backend.

Defines the :class:`BudgetBackend` Protocol — a duck-typed contract that
the existing in-process :class:`~chuzom.budget_envelope.BudgetEnvelopeManager`
already satisfies — and a persistent :class:`SqliteBudgetBackend` that
honours the same contract with cross-process atomicity via SQLite
``BEGIN IMMEDIATE`` transactions.

Why a separate module
---------------------
``budget_envelope.py`` ships an in-process, asyncio-locked manager whose
docstring explicitly says ``"T2-L1 will replace this with a
distributed-safe backend; the in-process correctness is the shape T2-L1
has to honour."`` This file is that replacement. It is additive only —
nothing in the existing module changes — so callers can migrate one site
at a time via :func:`get_budget_backend`.

Phase 3a vs Phase 3b
--------------------
* **Phase 3a (this PR)**: single SQLite file at
  ``~/.chuzom/budgets.db``. Multiple OS processes coordinate via
  SQLite's file lock (``BEGIN IMMEDIATE``). Multiple coroutines in one
  event loop coordinate via an additional ``asyncio.Lock`` so the
  ordering is FIFO inside the event loop too.
* **Phase 3b (T2-XL1)**: multi-instance coordination via a shared
  backend (Postgres / Redis). Same :class:`BudgetBackend` Protocol;
  drop-in replacement.

Atomicity contract
------------------
For the G-002 acceptance criterion — *100 concurrent calls against
budget N → exactly N succeed* — every ``try_reserve`` /
``release`` / ``commit`` runs inside a single
``BEGIN IMMEDIATE … COMMIT`` round-trip. The transaction takes the
RESERVED lock for the duration of the read-modify-write, so any
contending writer either waits or gets ``SQLITE_BUSY`` (we retry).
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from chuzom.budget_envelope import BudgetEnvelope, BudgetEnvelopeManager
from chuzom.budget_key import BudgetKey
from chuzom.logging import get_logger

log = get_logger("chuzom.budget_backend")


# ── Protocol ───────────────────────────────────────────────────────────────


@runtime_checkable
class BudgetBackend(Protocol):
    """Abstract budget storage + reservation contract.

    The existing :class:`~chuzom.budget_envelope.BudgetEnvelopeManager`
    satisfies this Protocol by duck typing. Any new backend
    (:class:`SqliteBudgetBackend`, future Postgres backend, future Redis
    backend) needs only to expose the same method names with the same
    behavioural contract.

    Threading / async contract
    --------------------------
    ``register`` / ``get`` / ``consumed`` / ``pending`` / ``remaining`` /
    ``tier_state`` are synchronous snapshot reads. ``try_reserve`` /
    ``release`` / ``commit`` are async because backends may need to
    coordinate via a lock (in-process) or a transaction (SQL).
    """

    def register(
        self,
        key: BudgetKey,
        cap_usd: float,
        *,
        parents: tuple[BudgetKey, ...] = (),
        soft_cap_usd: float | None = None,
    ) -> BudgetEnvelope: ...

    def get(self, key: BudgetKey) -> BudgetEnvelope | None: ...

    def consumed(self, key: BudgetKey) -> float: ...

    def pending(self, key: BudgetKey) -> float: ...

    def remaining(self, key: BudgetKey) -> float: ...

    async def try_reserve(self, key: BudgetKey, cost_usd: float) -> bool: ...

    async def release(self, key: BudgetKey, cost_usd: float) -> None: ...

    async def commit(self, key: BudgetKey, cost_usd: float) -> None: ...

    def tier_state(self, key: BudgetKey) -> dict[str, float | bool | None]: ...


# ── SQLite backend ─────────────────────────────────────────────────────────


_SCHEMA = """
CREATE TABLE IF NOT EXISTS envelopes (
    key_blob TEXT PRIMARY KEY,
    cap_usd REAL NOT NULL,
    soft_cap_usd REAL,
    parents_json TEXT NOT NULL DEFAULT '[]',
    consumed_usd REAL NOT NULL DEFAULT 0.0,
    pending_usd REAL NOT NULL DEFAULT 0.0,
    soft_breached INTEGER NOT NULL DEFAULT 0
);
"""

_BUSY_TIMEOUT_MS = 5000  # 5s — generous enough for contention, short enough to surface deadlocks


def _serialise_key(key: BudgetKey) -> str:
    """Canonical string form of a BudgetKey for use as a SQLite PK.

    JSON-array shape preserves ``None``/``null`` distinguishably from
    string ``"None"`` and is trivially reversible if needed. Field
    order matches the dataclass ordering.
    """
    return json.dumps(
        [key.tenant_id, key.org_id, key.user_id, key.agent_id, key.scope]
    )


@dataclass
class _EnvelopeRow:
    cap_usd: float
    soft_cap_usd: float | None
    parents: tuple[BudgetKey, ...]
    consumed_usd: float
    pending_usd: float
    soft_breached: bool


class SqliteBudgetBackend:
    """Persistent budget backend with cross-process atomic
    check-then-charge.

    Single SQLite file. Each mutating call runs inside
    ``BEGIN IMMEDIATE`` so writers serialise on the OS-level file lock.
    Inside one event loop, an additional ``asyncio.Lock`` gives
    coroutines FIFO ordering — without it, two concurrent coroutines
    could both try to BEGIN IMMEDIATE and one would hit
    ``SQLITE_BUSY`` and retry, wasting work.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path(
            os.environ.get("CHUZOM_BUDGETS_DB_PATH")
            or (Path.home() / ".chuzom" / "budgets.db")
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None puts us in autocommit / manual-transaction
        # mode so BEGIN IMMEDIATE is honoured exactly. With the default
        # ("deferred"), Python's sqlite3 wrapper may issue its own BEGIN
        # before ours.
        self._conn = sqlite3.connect(
            str(self.db_path), isolation_level=None, check_same_thread=False
        )
        self._conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(_SCHEMA)
        # In-process coroutine fairness layer. See class docstring.
        self._lock = asyncio.Lock()

    def close(self) -> None:
        self._conn.close()

    # ── Read helpers ──────────────────────────────────────────────────────

    def _load(self, key: BudgetKey) -> _EnvelopeRow | None:
        cur = self._conn.execute(
            "SELECT cap_usd, soft_cap_usd, parents_json, consumed_usd, "
            "pending_usd, soft_breached FROM envelopes WHERE key_blob = ?",
            (_serialise_key(key),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        parents_raw = json.loads(row[2])
        parents = tuple(
            BudgetKey(*p) if isinstance(p, list) else BudgetKey(**p)
            for p in parents_raw
        )
        return _EnvelopeRow(
            cap_usd=row[0],
            soft_cap_usd=row[1],
            parents=parents,
            consumed_usd=row[3],
            pending_usd=row[4],
            soft_breached=bool(row[5]),
        )

    def get(self, key: BudgetKey) -> BudgetEnvelope | None:
        row = self._load(key)
        if row is None:
            return None
        return BudgetEnvelope(
            key=key,
            cap_usd=row.cap_usd,
            parents=row.parents,
            soft_cap_usd=row.soft_cap_usd,
        )

    def consumed(self, key: BudgetKey) -> float:
        row = self._load(key)
        return row.consumed_usd if row else 0.0

    def pending(self, key: BudgetKey) -> float:
        row = self._load(key)
        return row.pending_usd if row else 0.0

    def remaining(self, key: BudgetKey) -> float:
        row = self._load(key)
        if row is None:
            return float("inf")
        return max(0.0, row.cap_usd - row.consumed_usd - row.pending_usd)

    # ── Registration ──────────────────────────────────────────────────────

    def register(
        self,
        key: BudgetKey,
        cap_usd: float,
        *,
        parents: tuple[BudgetKey, ...] = (),
        soft_cap_usd: float | None = None,
    ) -> BudgetEnvelope:
        if cap_usd <= 0:
            raise ValueError(f"cap_usd must be positive, got {cap_usd!r}")
        if soft_cap_usd is not None:
            if soft_cap_usd <= 0:
                raise ValueError(
                    f"soft_cap_usd must be positive, got {soft_cap_usd!r}"
                )
            if soft_cap_usd >= cap_usd:
                raise ValueError(
                    f"soft_cap_usd ({soft_cap_usd}) must be strictly less "
                    f"than cap_usd ({cap_usd})"
                )
        parents_json = json.dumps(
            [
                [p.tenant_id, p.org_id, p.user_id, p.agent_id, p.scope]
                for p in parents
            ]
        )
        # UPSERT preserving accumulated consumed/pending. A re-register
        # with a higher cap must not drop spend history.
        self._conn.execute(
            "INSERT INTO envelopes "
            "(key_blob, cap_usd, soft_cap_usd, parents_json) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key_blob) DO UPDATE SET "
            "cap_usd=excluded.cap_usd, "
            "soft_cap_usd=excluded.soft_cap_usd, "
            "parents_json=excluded.parents_json",
            (_serialise_key(key), float(cap_usd), soft_cap_usd, parents_json),
        )
        return BudgetEnvelope(
            key=key,
            cap_usd=float(cap_usd),
            parents=tuple(parents),
            soft_cap_usd=(
                float(soft_cap_usd) if soft_cap_usd is not None else None
            ),
        )

    # ── Mutations under BEGIN IMMEDIATE ───────────────────────────────────

    def _chain_rows(self, key: BudgetKey) -> list[tuple[BudgetKey, _EnvelopeRow]]:
        """Return [(key, row), (parent_key, parent_row), ...] for every
        registered envelope in the chain. Unregistered parents are
        silently skipped — parity with the in-process manager."""
        out: list[tuple[BudgetKey, _EnvelopeRow]] = []
        row = self._load(key)
        if row is None:
            return out
        out.append((key, row))
        for parent_key in row.parents:
            parent_row = self._load(parent_key)
            if parent_row is not None:
                out.append((parent_key, parent_row))
        return out

    async def try_reserve(self, key: BudgetKey, cost_usd: float) -> bool:
        if cost_usd <= 0:
            return True
        async with self._lock:
            return await asyncio.to_thread(self._try_reserve_sync, key, cost_usd)

    def _try_reserve_sync(self, key: BudgetKey, cost_usd: float) -> bool:
        self._begin_immediate_with_retry()
        try:
            chain = self._chain_rows(key)
            if not chain:
                self._conn.execute("COMMIT")
                return True
            for _, row in chain:
                projected = row.consumed_usd + row.pending_usd + cost_usd
                if projected > row.cap_usd:
                    self._conn.execute("COMMIT")
                    return False
            for env_key, _ in chain:
                self._conn.execute(
                    "UPDATE envelopes SET pending_usd = pending_usd + ? "
                    "WHERE key_blob = ?",
                    (cost_usd, _serialise_key(env_key)),
                )
            self._conn.execute("COMMIT")
            # Soft-tier flip happens outside the transaction (no contention
            # risk for a state flag) so the alerting log line lands after
            # the commit is durable.
            for env_key, _ in chain:
                self._maybe_flip_soft_state(env_key)
            return True
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    async def release(self, key: BudgetKey, cost_usd: float) -> None:
        if cost_usd <= 0:
            return
        async with self._lock:
            await asyncio.to_thread(self._release_sync, key, cost_usd)

    def _release_sync(self, key: BudgetKey, cost_usd: float) -> None:
        self._begin_immediate_with_retry()
        try:
            chain = self._chain_rows(key)
            for env_key, _ in chain:
                self._conn.execute(
                    "UPDATE envelopes SET pending_usd = max(0.0, pending_usd - ?) "
                    "WHERE key_blob = ?",
                    (cost_usd, _serialise_key(env_key)),
                )
            self._conn.execute("COMMIT")
            for env_key, _ in chain:
                self._maybe_flip_soft_state(env_key)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    async def commit(self, key: BudgetKey, cost_usd: float) -> None:
        if cost_usd <= 0:
            return
        async with self._lock:
            await asyncio.to_thread(self._commit_sync, key, cost_usd)

    def _commit_sync(self, key: BudgetKey, cost_usd: float) -> None:
        self._begin_immediate_with_retry()
        try:
            chain = self._chain_rows(key)
            for env_key, _ in chain:
                self._conn.execute(
                    "UPDATE envelopes SET "
                    "consumed_usd = consumed_usd + ?, "
                    "pending_usd = max(0.0, pending_usd - ?) "
                    "WHERE key_blob = ?",
                    (cost_usd, cost_usd, _serialise_key(env_key)),
                )
            self._conn.execute("COMMIT")
            for env_key, _ in chain:
                self._maybe_flip_soft_state(env_key)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _begin_immediate_with_retry(self) -> None:
        """Begin an immediate-mode transaction, retrying briefly on
        SQLITE_BUSY. The PRAGMA busy_timeout above should usually
        absorb contention, but a defensive retry catches the case where
        another writer holds RESERVED across the timeout window."""
        deadline = time.monotonic() + (_BUSY_TIMEOUT_MS / 1000)
        while True:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as err:
                if "busy" in str(err).lower() and time.monotonic() < deadline:
                    time.sleep(0.005)
                    continue
                raise

    # ── Soft tier ─────────────────────────────────────────────────────────

    def _maybe_flip_soft_state(self, key: BudgetKey) -> None:
        row = self._load(key)
        if row is None or row.soft_cap_usd is None:
            return
        total = row.consumed_usd + row.pending_usd
        is_breached = total >= row.soft_cap_usd
        if is_breached == row.soft_breached:
            return
        self._conn.execute(
            "UPDATE envelopes SET soft_breached = ? WHERE key_blob = ?",
            (1 if is_breached else 0, _serialise_key(key)),
        )
        if is_breached:
            log.warning(
                "budget_soft_cap_breached",
                key=str(key),
                soft_cap_usd=row.soft_cap_usd,
                cap_usd=row.cap_usd,
                consumed_usd=row.consumed_usd,
                pending_usd=row.pending_usd,
            )

    def tier_state(self, key: BudgetKey) -> dict[str, float | bool | None]:
        row = self._load(key)
        if row is None:
            return {
                "cap_usd": None,
                "soft_cap_usd": None,
                "consumed_usd": 0.0,
                "pending_usd": 0.0,
                "remaining_usd": float("inf"),
                "usage_pct": None,
                "soft_breached": False,
            }
        return {
            "cap_usd": row.cap_usd,
            "soft_cap_usd": row.soft_cap_usd,
            "consumed_usd": row.consumed_usd,
            "pending_usd": row.pending_usd,
            "remaining_usd": max(
                0.0, row.cap_usd - row.consumed_usd - row.pending_usd
            ),
            "usage_pct": (row.consumed_usd + row.pending_usd) / row.cap_usd,
            "soft_breached": row.soft_breached,
        }


# ── Factory ───────────────────────────────────────────────────────────────


_BACKEND_KIND_SQLITE = "sqlite"
_BACKEND_KIND_MEMORY = "memory"
_BACKEND_KIND_POSTGRES = "postgres"
_BACKEND_KIND_DEFAULT = _BACKEND_KIND_SQLITE
_KNOWN_BACKENDS = {
    _BACKEND_KIND_SQLITE,
    _BACKEND_KIND_MEMORY,
    _BACKEND_KIND_POSTGRES,
}

_backend: BudgetBackend | None = None


def get_budget_backend() -> BudgetBackend:
    """Return the module-level budget backend singleton.

    Selection: ``CHUZOM_BUDGET_BACKEND`` env var, one of:

    * ``sqlite`` (default) — persistent, single-instance cross-process-safe
      via SQLite ``BEGIN IMMEDIATE``.
    * ``memory`` — in-process :class:`BudgetEnvelopeManager`, useful for
      tests and ephemeral deployments.
    * ``postgres`` (T2-XL1, Phase 3b) — multi-instance coordination via a
      shared Postgres database. Requires the ``postgres`` extra and
      ``CHUZOM_BUDGET_POSTGRES_DSN`` to be set. Falls back to ``sqlite``
      if the dep / DSN is missing (fail-open posture).

    Invalid values fall back to the safer ``sqlite`` default — a
    misconfigured env var must never break boot.
    """
    global _backend
    if _backend is not None:
        return _backend
    raw = os.environ.get("CHUZOM_BUDGET_BACKEND", "").strip().lower()
    kind = raw if raw in _KNOWN_BACKENDS else _BACKEND_KIND_DEFAULT
    if kind == _BACKEND_KIND_MEMORY:
        _backend = BudgetEnvelopeManager()
    elif kind == _BACKEND_KIND_POSTGRES:
        try:
            from chuzom.budget_backend_postgres import PostgresBudgetBackend
            _backend = PostgresBudgetBackend()
        except (ImportError, RuntimeError) as err:
            # Fail-open: a missing dep or DSN must not break boot.
            # Operators see the warning and can fix; routing continues
            # against the local SQLite backend in the meantime.
            log.warning(
                "postgres_backend_unavailable_fallback_sqlite",
                error=str(err),
            )
            _backend = SqliteBudgetBackend()
    else:
        _backend = SqliteBudgetBackend()
    return _backend


def reset_budget_backend_for_tests() -> None:
    """Drop the singleton so the next ``get_budget_backend`` starts
    fresh. Production code never calls this."""
    global _backend
    if _backend is not None and hasattr(_backend, "close"):
        try:
            _backend.close()
        except Exception:
            pass
    _backend = None


__all__ = [
    "BudgetBackend",
    "SqliteBudgetBackend",
    "get_budget_backend",
    "reset_budget_backend_for_tests",
]
