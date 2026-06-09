"""T2-M2: per-identity ``BudgetEnvelope`` with parent-child propagation.

Builds on T2-M1's ``BudgetKey`` (shape) and per-key reservation
primitives (``reserve_for`` / ``release_for``) by adding:

* **Caps.** Each envelope has a ``cap_usd``; the manager refuses
  reservations that would push consumed+pending over the cap.
* **Parent propagation.** A child envelope declares its parents; a
  reservation on the child is checked against every parent's cap
  atomically. If any envelope in the chain would breach, the
  reservation is refused and **no** envelope is changed.
* **Atomic check-then-charge** under an in-process ``asyncio.Lock``.
  T2-L1 will replace this with a distributed-safe backend; the
  in-process correctness is the shape T2-L1 has to honour.

Today's accounting is in-process only. Single-process deployments
get correct behaviour; multi-process / multi-host coordination lands
in T2-XL1 (per-tenant single-writer or central event stream — the
Q-P-2 hybrid A→B path explicitly defers this to Phase 3b).

Contract:

* ``register(key, cap_usd, parents=())`` — register or replace an
  envelope. Re-registering a key with a different cap is allowed;
  parent set must remain a subset of previously-known envelopes.
* ``try_reserve(key, cost_usd)`` — async. Returns ``True`` and
  reserves ``cost_usd`` on self + each parent. Returns ``False`` if
  any envelope would breach; no changes made.
* ``release(key, cost_usd)`` — async. Reverts a prior ``try_reserve``
  on self + parents (cancel / refund path).
* ``commit(key, cost_usd)`` — async. Moves ``cost_usd`` from
  pending to consumed on self + parents (success path).
* ``consumed(key)`` / ``pending(key)`` / ``remaining(key)`` —
  introspection accessors. Non-async because they read snapshot
  values; concurrent mutations may produce strictly-monotone-ish
  numbers, which is the correct semantic for a metric.

See: Docs/audit/post-remediation/GAP_ANALYSIS.md G-002 (parent-child
budget propagation slice of the per-identity budget cluster).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from chuzom.budget import release_for, reserve_for
from chuzom.budget_key import BudgetKey
from chuzom.logging import get_logger

log = get_logger("chuzom.budget_envelope")


@dataclass(frozen=True)
class BudgetEnvelope:
    """Static description of one envelope.

    The dynamic state (consumed_usd, pending tally) lives in the
    manager — the envelope is just the *contract*: which key, what
    cap, which parents to debit on every reservation.
    """

    key: BudgetKey
    cap_usd: float
    parents: tuple[BudgetKey, ...] = field(default_factory=tuple)


class BudgetEnvelopeManager:
    """In-process atomic manager for BudgetEnvelope state.

    Single coarse asyncio.Lock around mutations: correct for the
    in-process case, simple to reason about, and gives T2-L1 a
    concrete reference behaviour to match when the distributed
    backend lands.
    """

    def __init__(self) -> None:
        self._envelopes: dict[BudgetKey, BudgetEnvelope] = {}
        self._consumed: dict[BudgetKey, float] = {}
        # Per-key pending in addition to budget._pending_spend_by_key.
        # The duplication is deliberate: the global dict carries every
        # reservation chuzom makes anywhere; this dict scopes to
        # envelopes specifically so a release on the envelope manager
        # doesn't accidentally floor a reservation that some other
        # subsystem made on the same key.
        self._pending: dict[BudgetKey, float] = {}
        self._lock = asyncio.Lock()

    def register(
        self,
        key: BudgetKey,
        cap_usd: float,
        *,
        parents: tuple[BudgetKey, ...] = (),
    ) -> BudgetEnvelope:
        """Register or replace an envelope.

        ``cap_usd`` must be positive; ``parents`` may name keys that
        were not yet registered — they will be honoured if/when they
        are. A re-register preserves any existing consumed/pending
        totals so a long-lived parent re-registered with a higher cap
        does not lose its accounting history.
        """
        if cap_usd <= 0:
            raise ValueError(f"cap_usd must be positive, got {cap_usd!r}")
        env = BudgetEnvelope(key=key, cap_usd=float(cap_usd), parents=tuple(parents))
        self._envelopes[key] = env
        self._consumed.setdefault(key, 0.0)
        self._pending.setdefault(key, 0.0)
        return env

    def get(self, key: BudgetKey) -> BudgetEnvelope | None:
        return self._envelopes.get(key)

    def consumed(self, key: BudgetKey) -> float:
        return self._consumed.get(key, 0.0)

    def pending(self, key: BudgetKey) -> float:
        return self._pending.get(key, 0.0)

    def remaining(self, key: BudgetKey) -> float:
        """``cap - consumed - pending`` floored at zero; ``inf`` for
        keys without a registered envelope (no enforcement)."""
        env = self._envelopes.get(key)
        if env is None:
            return float("inf")
        return max(
            0.0,
            env.cap_usd - self._consumed.get(key, 0.0) - self._pending.get(key, 0.0),
        )

    def _chain(self, key: BudgetKey) -> list[BudgetEnvelope]:
        """Return [self_env, *parent_envs] for the registered envelopes
        in the parent chain. Unregistered parents are silently
        skipped — caller knows what envelopes it registered."""
        out: list[BudgetEnvelope] = []
        env = self._envelopes.get(key)
        if env is None:
            return out
        out.append(env)
        for parent_key in env.parents:
            parent = self._envelopes.get(parent_key)
            if parent is not None:
                out.append(parent)
        return out

    async def try_reserve(self, key: BudgetKey, cost_usd: float) -> bool:
        """Atomic: walk self + parents; if every cap accommodates
        ``cost_usd`` on top of (consumed + pending), commit the
        reservation on each and return True. Otherwise return False
        and leave every envelope unchanged.

        Non-positive ``cost_usd`` is a no-op that returns True.
        """
        if cost_usd <= 0:
            return True
        async with self._lock:
            chain = self._chain(key)
            if not chain:
                # No envelope registered → no enforcement.
                return True
            for env in chain:
                projected = (
                    self._consumed.get(env.key, 0.0)
                    + self._pending.get(env.key, 0.0)
                    + cost_usd
                )
                if projected > env.cap_usd:
                    return False
            # All checks passed; commit pending on each.
            for env in chain:
                self._pending[env.key] = (
                    self._pending.get(env.key, 0.0) + cost_usd
                )
                reserve_for(env.key, cost_usd)
            return True

    async def release(self, key: BudgetKey, cost_usd: float) -> None:
        """Revert a prior ``try_reserve``. Cancel / refund path."""
        if cost_usd <= 0:
            return
        async with self._lock:
            chain = self._chain(key)
            for env in chain:
                current = self._pending.get(env.key, 0.0)
                self._pending[env.key] = max(0.0, current - cost_usd)
                release_for(env.key, cost_usd)

    async def commit(self, key: BudgetKey, cost_usd: float) -> None:
        """Move ``cost_usd`` from pending to consumed on self + parents.

        Success path: caller called ``try_reserve(key, estimated)``,
        the provider returned with ``actual_cost``, caller calls
        ``commit(key, actual_cost)`` AND ``release(key, estimated)`` if
        actual ≠ estimated — or just ``commit(key, estimated)`` if the
        accounting tolerance is acceptable.
        """
        if cost_usd <= 0:
            return
        async with self._lock:
            chain = self._chain(key)
            for env in chain:
                self._consumed[env.key] = (
                    self._consumed.get(env.key, 0.0) + cost_usd
                )
                # Decrement pending to match — production callers should
                # pair commit() with release() of any unused reservation.
                self._pending[env.key] = max(
                    0.0, self._pending.get(env.key, 0.0) - cost_usd
                )
                release_for(env.key, cost_usd)


# ── Module-level singleton ──────────────────────────────────────────────────

_manager: BudgetEnvelopeManager | None = None


def get_manager() -> BudgetEnvelopeManager:
    global _manager
    if _manager is None:
        _manager = BudgetEnvelopeManager()
    return _manager


def reset_manager_for_tests() -> None:
    """Drop the singleton so the next ``get_manager`` starts fresh.
    Production code never calls this."""
    global _manager
    _manager = None
    # Drop the global per-key reservation dict too so tests don't
    # leak pending spend between runs.
    from chuzom.budget import reset_pending_spend_for_tests
    reset_pending_spend_for_tests()


__all__ = [
    "BudgetEnvelope",
    "BudgetEnvelopeManager",
    "get_manager",
    "reset_manager_for_tests",
]
