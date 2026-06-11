"""G-002 — Tier-3 token auth becomes the runtime identity path under
``CHUZOM_PROFILE=enterprise``.

The pre-G-002 ``current_identity()`` trusted env vars
(``CHUZOM_USER_ID``, ``CHUZOM_ORG_ID``, ``CHUZOM_AGENT_ID``) with no
cryptographic validation. Any process that set ``CHUZOM_USER_ID=admin``
routed as admin. Tier-3 token auth existed in ``enterprise/identity.py``
but was not the runtime path.

G-002 flips the runtime path under enterprise profile to require a
``CHUZOM_TOKEN`` bearer credential validated through ``IdentityStore``
+ ``Permission.ROUTE_PROMPT``. Failure raises
``EnterpriseIdentityRequired`` so the first routed turn fails loudly.

Developer profile preserves the env-trust resolver — backward compat
is the whole point of the profile knob (slice 3).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom import identity as identity_mod
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch) -> None:
    """Strip every env this slice touches so each test starts clean."""
    for env in (
        "CHUZOM_PROFILE",
        "CHUZOM_TOKEN",
        "CHUZOM_USER_ID",
        "CHUZOM_USER_EMAIL",
        "CHUZOM_ORG_ID",
        "CHUZOM_AGENT_ID",
        "CHUZOM_TENANT_ID",
    ):
        monkeypatch.delenv(env, raising=False)
    # Reset the cached enterprise store so each test gets a fresh
    # resolution path; tests that need a store inject their own.
    monkeypatch.setattr(identity_mod, "_enterprise_store", None)


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False
    )


@pytest.fixture
def routable_token(store: IdentityStore) -> str:
    """Issue an EMPLOYEE token — has ``Permission.ROUTE_PROMPT``."""
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="dev@acme.test", display_name="Dev",
        role=Role.EMPLOYEE,
    )
    return store.issue_token(user.id, name="laptop").plaintext


# ── 1. Developer profile (default) — env-trust preserved ───────────────────


def test_developer_profile_uses_env_trust(monkeypatch) -> None:
    """Pre-G-002 behaviour: env values flow through unchanged."""
    monkeypatch.setenv("CHUZOM_USER_ID", "alice")
    monkeypatch.setenv("CHUZOM_USER_EMAIL", "alice@x")
    monkeypatch.setenv("CHUZOM_ORG_ID", "team42")
    ti = identity_mod.current_identity()
    assert ti.user_id == "alice"
    assert ti.user_email == "alice@x"
    assert ti.org_id == "team42"


def test_developer_profile_fallback_chain(monkeypatch) -> None:
    """No env set → getpass / sentinel fallback (unchanged contract)."""
    monkeypatch.setattr(identity_mod.getpass, "getuser", lambda: "yali")
    ti = identity_mod.current_identity()
    assert ti.user_id == "yali"
    assert ti.user_email == "yali@local"
    assert ti.org_id == "local"


def test_developer_profile_does_not_require_token(monkeypatch) -> None:
    """Developer profile must not consult CHUZOM_TOKEN at all —
    explicitly setting an invalid token is fine."""
    monkeypatch.setenv("CHUZOM_TOKEN", "tsr_bogus")
    monkeypatch.setattr(identity_mod.getpass, "getuser", lambda: "dev")
    ti = identity_mod.current_identity()
    assert ti.user_id == "dev"


# ── 2. Enterprise profile — refuses env-trust ───────────────────────────────


def test_enterprise_no_token_raises(monkeypatch) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    with pytest.raises(identity_mod.EnterpriseIdentityRequired) as excinfo:
        identity_mod.current_identity()
    msg = str(excinfo.value).lower()
    assert "chuzom_token" in msg
    assert "g-002" in msg or "admin api" in msg


def test_enterprise_empty_token_raises(monkeypatch) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", "   ")
    with pytest.raises(identity_mod.EnterpriseIdentityRequired):
        identity_mod.current_identity()


def test_enterprise_invalid_token_raises(
    monkeypatch, store: IdentityStore
) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", "tsr_definitely-not-a-real-token")
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    with pytest.raises(identity_mod.EnterpriseIdentityRequired) as excinfo:
        identity_mod.current_identity()
    assert "valid token" in str(excinfo.value).lower()


def test_enterprise_user_lacking_route_prompt_raises(
    monkeypatch, store: IdentityStore
) -> None:
    """A token whose permission set excludes ROUTE_PROMPT is refused.

    Issuing a token with an empty permissions tuple simulates a
    misconfigured role mapping; the resolver must catch it."""
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="restricted@acme.test", display_name="R",
        role=Role.EMPLOYEE,
    )
    tok = store.issue_token(user.id, name="restricted", permissions=())
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", tok.plaintext)
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    with pytest.raises(identity_mod.EnterpriseIdentityRequired) as excinfo:
        identity_mod.current_identity()
    assert "route_prompt" in str(excinfo.value).lower()


def test_enterprise_revoked_token_raises(
    monkeypatch, store: IdentityStore, routable_token: str
) -> None:
    """Revoke a previously-good token; auth must fail."""
    # Find the token id by looking up the user we know exists.
    user = store.get_user_by_email("dev@acme.test")
    # We can't get the token id back from the plaintext, but the same
    # user's other tokens revoke en-masse via revoke_user_tokens.
    store.revoke_user_tokens(user.id)
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", routable_token)
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    with pytest.raises(identity_mod.EnterpriseIdentityRequired):
        identity_mod.current_identity()


# ── 3. Enterprise profile — happy path ──────────────────────────────────────


def test_enterprise_valid_token_returns_turn_identity(
    monkeypatch, store: IdentityStore, routable_token: str
) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", routable_token)
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    ti = identity_mod.current_identity()
    assert ti.user_email == "dev@acme.test"
    assert ti.org_id != "local"  # came from the store, not the sentinel
    assert ti.tenant_id == ti.org_id  # default tenant alias


def test_enterprise_agent_id_env_still_applies(
    monkeypatch, store: IdentityStore, routable_token: str
) -> None:
    """The agent dimension stays env-driven even under enterprise —
    agent_id is workflow-attribution, not an auth principal."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", routable_token)
    monkeypatch.setenv("CHUZOM_AGENT_ID", "doc-summariser-v2")
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    ti = identity_mod.current_identity()
    assert ti.agent_id == "doc-summariser-v2"


def test_enterprise_explicit_tenant_id_overrides_org(
    monkeypatch, store: IdentityStore, routable_token: str
) -> None:
    """``CHUZOM_TENANT_ID`` env beats the org_id fallback so Phase-3b
    sidecar-per-tenant deployments can serve a tenant distinct from
    the chuzom process's own org."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", routable_token)
    monkeypatch.setenv("CHUZOM_TENANT_ID", "subsidiary-eu")
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    ti = identity_mod.current_identity()
    assert ti.tenant_id == "subsidiary-eu"


def test_enterprise_ignores_chuzom_user_id_env(
    monkeypatch, store: IdentityStore, routable_token: str
) -> None:
    """Setting CHUZOM_USER_ID under enterprise profile must NOT
    override the authenticated identity. This is the whole point
    of G-002."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", routable_token)
    monkeypatch.setenv("CHUZOM_USER_ID", "spoofed-admin")
    monkeypatch.setenv("CHUZOM_USER_EMAIL", "spoofed@evil.test")
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    ti = identity_mod.current_identity()
    assert ti.user_email == "dev@acme.test"
    assert ti.user_id != "spoofed-admin"
