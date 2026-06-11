"""P0-3: distributed budget-envelope enforcement at the routing chokepoint.

Bridges the distributed :class:`~chuzom.budget_backend.BudgetBackend` (envelope
``try_reserve`` / ``commit`` / ``release`` with tenant→org→user rollup) into
``route_and_call``. The envelope system shipped fully-formed but had **zero
production callers** — the router only used an in-process token path
(``reserve_tokens("anthropic", 500)``), so a registered envelope never actually
capped spend. This module wires it in.

Mode via ``CHUZOM_ENVELOPE_MODE`` (mirrors :mod:`chuzom.quota_routing`):

* **off** — no-op (developer-profile default).
* **strict** — refuse the turn when a registered envelope rejects the
  reservation (enterprise-profile default).

Safety: the backend is a **no-op pass-through** when no envelope is registered
for the turn's key (``try_reserve`` returns True on an empty chain), so wiring
this into the hot path never blocks routing until an operator registers a cap.
A store hiccup is also fail-open — budget accounting must not break a turn.

Lifecycle (matches the backend contract — reserve and settle with explicit
amounts): reserve the *estimate* before dispatch; on success ``release(est)``
then ``commit(actual)``; on failure ``release(est)``. ``release(est)`` undoes
the reservation and ``commit(actual)`` records true spend, so ``pending`` stays
clean even when the estimate and the actual cost differ.

EXPERIMENTAL for multi-instance: enforcement is proven against the SQLite
backend (single-instance, cross-process-safe via ``BEGIN IMMEDIATE``) in CI. The
Postgres backend's multi-instance coordination is not yet covered by a
real-Postgres CI test — do not rely on cross-instance envelope enforcement until
that lands (Phase D).

🥷 Backslash-Security: using vibe-coding rules for secured Authentication & Authorization
"""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)

_ENVELOPE_MODE_ENV = "CHUZOM_ENVELOPE_MODE"
_STRICT_VALUES = {"strict", "hard"}
_OFF_VALUES = {"off"}


def _resolve_mode() -> str:
    """Return ``'off'`` / ``'strict'`` from env + profile."""
    import os
    raw = (os.environ.get(_ENVELOPE_MODE_ENV) or "").strip().lower()
    if raw in _STRICT_VALUES:
        return "strict"
    if raw in _OFF_VALUES:
        return "off"
    from chuzom.profile import is_enterprise
    return "strict" if is_enterprise() else "off"


def _get_backend():
    from chuzom.budget_backend import get_budget_backend
    return get_budget_backend()


def _key_for(identity: Any):
    from chuzom.budget_key import budget_key_from_identity
    return budget_key_from_identity(identity)


async def reserve_envelope(
    identity: Any, est_cost_usd: float, *, backend=None
) -> tuple[str, bool, Any]:
    """Reserve ``est_cost_usd`` against the turn's envelope.

    Returns ``(mode, ok, key)``. ``ok`` is False only when a *registered*
    envelope in the key's rollup chain is exhausted — the caller should then
    refuse the turn (zero spend). Otherwise ``ok`` is True and ``key`` is the
    reserved :class:`BudgetKey` so the caller can settle exactly what it
    reserved. Off-mode / missing identity / store error → ``(mode, True, None)``.
    """
    mode = _resolve_mode()
    if mode == "off":
        return ("off", True, None)
    if not getattr(identity, "user_id", None):
        return (mode, True, None)
    b = backend or _get_backend()
    key = _key_for(identity)
    try:
        ok = await b.try_reserve(key, float(est_cost_usd or 0.0))
    except Exception as exc:  # fail-open: a budget-store hiccup must not break routing
        log.warning("envelope_reserve_failed", error=str(exc))
        return (mode, True, None)
    return (mode, bool(ok), key)


async def commit_envelope(
    key: Any, est_cost_usd: float, actual_cost_usd: float, *, backend=None
) -> None:
    """Settle a successful turn: undo the reservation, record the real spend."""
    if key is None:
        return
    b = backend or _get_backend()
    try:
        await b.release(key, float(est_cost_usd or 0.0))
        await b.commit(key, float(actual_cost_usd or 0.0))
    except Exception as exc:
        log.warning("envelope_commit_failed", error=str(exc))


async def release_envelope(key: Any, est_cost_usd: float, *, backend=None) -> None:
    """Settle a failed / cancelled / timed-out turn: release the reservation."""
    if key is None:
        return
    b = backend or _get_backend()
    try:
        await b.release(key, float(est_cost_usd or 0.0))
    except Exception as exc:
        log.warning("envelope_release_failed", error=str(exc))


__all__ = ["reserve_envelope", "commit_envelope", "release_envelope"]
