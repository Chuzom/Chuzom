"""Tier-1 identity: minimal user resolution for the routing audit chain.

Phase 2 of the 2026-06 audit roadmap ships in three tiers:

  Tier 1 — Single user in an enterprise. One ``user_id`` threads through
           every routed turn so the audit chain has *someone* to attribute
           the decision to. No agents, no tenants. This module.
  Tier 2 — Agents on the user's computer. Adds ``agent_id`` alongside
           ``user_id``. Builds on the same env-based resolver.
  Tier 3 — Enterprise-controlled agents. Promotes ``TurnIdentity`` into
           the full ``chuzom.enterprise.identity.Identity`` (User +
           APIToken + Permissions). Wires RBAC into the routing path.

Tier 1's resolver intentionally never talks to the ``enterprise.identity``
``IdentityStore`` — that store assumes SSO / token-issuance machinery that
is out of scope for the single-user developer path. Tier 1 trusts the
operator's environment.
"""
from __future__ import annotations

import getpass
import os
from dataclasses import dataclass


# Env keys — kept here so callers (tests, doctor, install scripts) can
# import them without hardcoding the literal string.
CHUZOM_USER_ID_ENV = "CHUZOM_USER_ID"
CHUZOM_USER_EMAIL_ENV = "CHUZOM_USER_EMAIL"
CHUZOM_ORG_ID_ENV = "CHUZOM_ORG_ID"
# Tier 2: agents running on the user's computer. Optional — when the
# routed turn isn't part of an agent run (e.g. a direct MCP tool call
# from Claude Code), agent_id stays None and the audit row simply omits
# the agent dimension.
CHUZOM_AGENT_ID_ENV = "CHUZOM_AGENT_ID"
# T1-M1 (Q-P-2 Phase 3a): typed-but-implicit tenant axis. When unset,
# the resolver defaults ``tenant_id`` to ``org_id`` so the field is
# never None in production — consumers (budget keys, audit detail,
# log contextvars) can rely on it. Set explicitly only in Phase 3b
# (sidecar-per-tenant) where one chuzom process serves a tenant
# distinct from its org. See Docs/audit/decisions/Q-P-2_multi-tenancy.md.
CHUZOM_TENANT_ID_ENV = "CHUZOM_TENANT_ID"

# Default org for Tier-1 single-user mode. Picked to be obviously
# non-SSO-derived so a future audit reader can tell at a glance that the
# events were emitted before tenancy wiring landed.
DEFAULT_ORG_ID = "local"

# Sentinel fallback when even ``getpass.getuser()`` fails (tty-less
# environments, restricted containers). Never raise — the routing path
# must never block on identity resolution.
_FALLBACK_USER_ID = "unknown"


@dataclass(frozen=True)
class TurnIdentity:
    """Minimal identity used by Tier 1's audit-on-every-turn wiring.

    Carries just enough to populate one ``AuditEvent`` row. Promoted to
    ``chuzom.enterprise.identity.Identity`` in Tier 3 when RBAC lands.

    Attributes
    ----------
    user_id:
        The actor for audit attribution. Sourced from ``CHUZOM_USER_ID``
        with a ``getpass.getuser()`` fallback. Never empty.
    user_email:
        Denormalised email for SIEM readability. Sourced from
        ``CHUZOM_USER_EMAIL`` with a ``<user_id>@local`` fallback so the
        downstream column is never NULL.
    org_id:
        The org the event is bucketed under. Defaults to ``"local"`` for
        Tier 1 single-user mode; replaced by a real org slug in Tier 3.
    """

    user_id: str
    user_email: str
    org_id: str
    # Tier 2: the agent driving this turn, if any. None means "this turn
    # was not part of an agent run" (a direct MCP tool call, a CLI
    # invocation, etc.). When set, the audit row carries an ``agent_id``
    # field in ``detail`` and the log contextvars get an ``agent_id`` key.
    agent_id: str | None = None
    # T1-M1 (Q-P-2 Phase 3a): typed-but-implicit tenant axis. ``None`` on
    # the dataclass default for backwards compat with direct
    # ``TurnIdentity(...)`` construction; ``current_identity()`` always
    # populates it (env > org_id fallback) so production callers see a
    # non-None value. Downstream consumers should treat ``None`` as
    # "no tenant attribution available" — the resolver's job to avoid
    # producing that state in production.
    tenant_id: str | None = None


def current_identity() -> TurnIdentity:
    """Resolve the current identity from the environment.

    Resolution order — first non-empty value wins:

    ``user_id``:
        1. ``CHUZOM_USER_ID`` env var
        2. ``getpass.getuser()`` (works under cron, ssh, and containers
           where ``os.getlogin()`` would raise ``OSError``)
        3. Sentinel ``"unknown"``

    ``user_email``:
        1. ``CHUZOM_USER_EMAIL`` env var
        2. ``"<user_id>@local"``

    ``org_id``:
        1. ``CHUZOM_ORG_ID`` env var
        2. Sentinel ``"local"``

    This function does not raise. The routing path calls it on every
    turn; an unset environment cannot be allowed to break routing.
    """
    user_id = (os.environ.get(CHUZOM_USER_ID_ENV) or "").strip()
    if not user_id:
        try:
            user_id = getpass.getuser()
        except Exception:
            user_id = _FALLBACK_USER_ID

    user_email = (os.environ.get(CHUZOM_USER_EMAIL_ENV) or "").strip()
    if not user_email:
        user_email = f"{user_id}@local"

    org_id = (os.environ.get(CHUZOM_ORG_ID_ENV) or "").strip()
    if not org_id:
        org_id = DEFAULT_ORG_ID

    # agent_id is optional. Blank / whitespace / unset all collapse to None
    # so downstream consumers (audit detail, log contextvars) can use a
    # simple ``if identity.agent_id:`` check.
    agent_id_raw = (os.environ.get(CHUZOM_AGENT_ID_ENV) or "").strip()
    agent_id = agent_id_raw or None

    # T1-M1 (Q-P-2 Phase 3a): tenant_id is non-None in production.
    # Explicit ``CHUZOM_TENANT_ID`` wins; otherwise fall back to
    # ``org_id`` so single-org-per-instance deployments carry the
    # tenant dimension for forward compat without forcing every
    # caller to populate it. Phase 3b (sidecar-per-tenant) sets the
    # env explicitly so chuzom processes within one org can serve
    # distinct tenants.
    tenant_id_raw = (os.environ.get(CHUZOM_TENANT_ID_ENV) or "").strip()
    tenant_id = tenant_id_raw or org_id

    return TurnIdentity(
        user_id=user_id,
        user_email=user_email,
        org_id=org_id,
        agent_id=agent_id,
        tenant_id=tenant_id,
    )


__all__ = [
    "CHUZOM_USER_ID_ENV",
    "CHUZOM_USER_EMAIL_ENV",
    "CHUZOM_ORG_ID_ENV",
    "CHUZOM_AGENT_ID_ENV",
    "CHUZOM_TENANT_ID_ENV",
    "DEFAULT_ORG_ID",
    "TurnIdentity",
    "current_identity",
]
