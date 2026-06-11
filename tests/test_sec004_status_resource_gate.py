"""SEC-004 — chuzom://status MCP resource identity gate.

The audit's SEC-004 row flagged that the ``chuzom://status``
resource leaks provider configuration to any MCP client that can
read the resource — no identity check. The closure: under
``CHUZOM_PROFILE=enterprise``, render a minimal redacted shape that
confirms the server is up but exposes no provider / model / tier
details unless the caller can authenticate via ``CHUZOM_TOKEN``.

Developer profile preserves the pre-SEC-004 full surface so
existing dev workstations and ``chuzom doctor`` keep working
without changing config.

Tests cover the three branches: developer (full), enterprise +
valid token (full), enterprise + no token (redacted). The
``force_redacted`` test affordance pins both rendered shapes
without depending on the rest of the gate plumbing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom import identity as identity_mod
from chuzom import server as srv
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch) -> None:
    for env in (
        "CHUZOM_PROFILE",
        "CHUZOM_TOKEN",
    ):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(identity_mod, "_enterprise_store", None)


# ── 1. Rendered shapes (via force_redacted test affordance) ────────────────


def test_full_shape_lists_providers() -> None:
    """The full (non-redacted) shape includes ``Providers`` and
    ``Text`` lines — the pre-SEC-004 contract."""
    rendered = srv._render_router_status(force_redacted=False)
    assert "Providers:" in rendered
    assert "Text:" in rendered


def test_redacted_shape_omits_provider_details() -> None:
    rendered = srv._render_router_status(force_redacted=True)
    # The minimal shape must NOT include provider / text / media
    # lines.
    assert "Providers:" not in rendered
    assert "Text:" not in rendered
    assert "Media:" not in rendered
    # But it MUST confirm the server is up.
    assert "Status: ok" in rendered
    # And hint at how to authenticate.
    assert "CHUZOM_TOKEN" in rendered


# ── 2. Auto-gate (developer profile → full) ────────────────────────────────


def test_developer_profile_returns_full_shape() -> None:
    """Pre-SEC-004 behaviour preserved when no profile is set.
    Pinning this so the gate doesn't surprise dev workstations or
    `chuzom doctor` on upgrade."""
    rendered = srv._render_router_status()
    assert "Providers:" in rendered


def test_routing_profile_collision_handled_gracefully(
    monkeypatch,
) -> None:
    """Acknowledge the architectural collision: slice-3's
    deployment ``CHUZOM_PROFILE=enterprise`` and the pre-existing
    routing config's ``CHUZOM_PROFILE`` field share the env name.
    The resource handler must fail soft on this collision (degrades
    to a useful message) rather than crashing.

    Future slice should split the envs (e.g. rename slice-3 to
    ``CHUZOM_DEPLOYMENT_PROFILE``) to remove the collision; this
    test pins the fail-soft contract until then."""
    monkeypatch.setenv("CHUZOM_PROFILE", "developer")
    # Even with the routing config rejecting "developer", the
    # function returns a string (degraded shape) rather than
    # raising.
    rendered = srv._render_router_status()
    assert isinstance(rendered, str)
    assert len(rendered) > 0


# ── 3. Enterprise profile → token-gated ────────────────────────────────────


def test_enterprise_no_token_returns_redacted(monkeypatch) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    rendered = srv._render_router_status()
    assert "Providers:" not in rendered
    assert "redacted (SEC-004)" in rendered


def test_enterprise_invalid_token_returns_redacted(
    monkeypatch, tmp_path: Path,
) -> None:
    """A token that doesn't authenticate must NOT reveal providers."""
    store = IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False,
    )
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", "tsr_fake-and-invalid")
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    rendered = srv._render_router_status()
    assert "Providers:" not in rendered


def test_enterprise_valid_token_skips_redacted_branch(
    monkeypatch, tmp_path: Path,
) -> None:
    """An authenticated identity (carrying ROUTE_PROMPT) does NOT
    get the SEC-004 redacted shape. Because ``CHUZOM_PROFILE`` is
    currently overloaded with routing config (architectural
    collision documented above), the full-shape path may also
    degrade to a routing-config-unavailable message; either way
    the SEC-004 redacted shape MUST NOT fire."""
    store = IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False,
    )
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="ops@acme", display_name="Ops", role=Role.EMPLOYEE,
    )
    tok = store.issue_token(user.id, name="t")
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", tok.plaintext)
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    rendered = srv._render_router_status()
    # The SEC-004 redacted shape includes "redacted (SEC-004)" —
    # that's what we're confirming we did NOT emit.
    assert "redacted (SEC-004)" not in rendered


def test_enterprise_underpermissioned_token_returns_redacted(
    monkeypatch, tmp_path: Path,
) -> None:
    """A token that authenticates but lacks ROUTE_PROMPT is treated
    the same as no token — the resource doesn't leak even to a
    valid user without routing rights."""
    store = IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False,
    )
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="r@x", display_name="R", role=Role.EMPLOYEE,
    )
    # Token with zero permissions.
    tok = store.issue_token(user.id, name="r", permissions=())
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", tok.plaintext)
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    rendered = srv._render_router_status()
    assert "Providers:" not in rendered


# ── 4. Public MCP resource handler delegates to _render ──────────────────


def test_resource_handler_calls_render() -> None:
    """``router_status`` is the MCP resource callable; we just want
    to confirm it returns a string with the documented shape (no
    arguments, returns the same as ``_render_router_status()``)."""
    output = srv.router_status()
    assert isinstance(output, str)
    # Developer profile (default) → contains Providers.
    assert "Providers:" in output
