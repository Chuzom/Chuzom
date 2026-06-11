"""Phase 3b — per-identity routing allow-lists, populated from the
authenticated (SSO/SCIM-provisioned) identity and enforced on the
routing path.

Before this, ``rbac_routing.check_provider`` / ``check_model`` read
``getattr(identity, "allowed_*", None)`` — and no identity carried the
attribute, so per-provider/model allow-listing was a silent no-op for
real principals. This wires the missing half: the ``IdentityStore``
persists per-user allow-lists (set by SCIM/OIDC provisioning or the
admin API), ``authenticate`` carries them onto the ``Identity.user``,
and ``current_identity`` propagates them to the ``TurnIdentity`` the
router already gates on.

Safety contract pinned here: ``None`` == unrestricted; an empty list is
normalised to ``None`` so it can never silently deny-all.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from chuzom.enterprise.identity import IdentityStore, User
from chuzom.enterprise.rbac import Role


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(db_path=tmp_path / "identity.db", check_same_thread=False)


def _make_user(store: IdentityStore, **kwargs: Any) -> User:
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    return store.create_user(
        org_id=org.id, team_id=team.id, email="e@x",
        display_name="E", role=Role.EMPLOYEE, **kwargs,
    )


# ── 1. Store round-trip + safety normalisation ──────────────────────────────


def test_allowlists_round_trip(store: IdentityStore) -> None:
    u = _make_user(
        store,
        allowed_providers=frozenset({"gemini", "anthropic"}),
        allowed_models=frozenset({"gemini/gemini-2.5-flash"}),
    )
    read = store.get_user(u.id)
    assert read.allowed_providers == frozenset({"gemini", "anthropic"})
    assert read.allowed_models == frozenset({"gemini/gemini-2.5-flash"})


def test_unset_allowlists_are_none_not_empty(store: IdentityStore) -> None:
    """The critical safety property: no policy → ``None`` (allow-all),
    never ``frozenset()`` (which the gates would read as deny-all)."""
    u = _make_user(store)
    read = store.get_user(u.id)
    assert read.allowed_providers is None
    assert read.allowed_models is None


def test_empty_allowlist_normalised_to_none(store: IdentityStore) -> None:
    """An accidental empty set must not deny-all — it's normalised to
    unrestricted at the store boundary."""
    u = _make_user(
        store, allowed_providers=frozenset(), allowed_models=frozenset()
    )
    read = store.get_user(u.id)
    assert read.allowed_providers is None
    assert read.allowed_models is None


def test_legacy_db_migrated_and_reads_none(tmp_path: Path) -> None:
    """A pre-Phase-3b identity DB (no allow-list columns) is migrated on
    open; its existing users surface ``None`` (unrestricted)."""
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE orgs (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            created_at REAL NOT NULL);
        CREATE TABLE teams (id TEXT PRIMARY KEY, org_id TEXT NOT NULL,
            name TEXT NOT NULL, monthly_budget_usd REAL NOT NULL DEFAULT 0.0,
            created_at REAL NOT NULL, UNIQUE(org_id, name));
        CREATE TABLE users (id TEXT PRIMARY KEY, org_id TEXT NOT NULL,
            team_id TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL, role TEXT NOT NULL,
            external_id TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL);
        INSERT INTO orgs VALUES ('o','acme',1.0);
        INSERT INTO teams VALUES ('t','o','platform',0.0,1.0);
        INSERT INTO users VALUES ('u','o','t','e@x','E','employee','',1,1.0);
        """
    )
    conn.commit()
    conn.close()

    store = IdentityStore(db_path=db, check_same_thread=False)
    cols = {r[1] for r in store._conn.execute("PRAGMA table_info(users)").fetchall()}
    assert {"allowed_providers", "allowed_models"} <= cols
    legacy = store.get_user("u")
    assert legacy.allowed_providers is None
    assert legacy.allowed_models is None


# ── 2. End-to-end: token → identity → enforcement on route_and_call ─────────


@pytest.fixture
def enterprise_identity_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Stand up a real IdentityStore the enterprise resolver reads,
    under the enterprise profile. Returns the store so tests can mint
    users + tokens."""
    from chuzom import identity as identity_mod
    from chuzom.audit_routing import reset_audit_log_for_tests
    from chuzom.idempotency import reset_store_for_tests

    id_db = tmp_path / "identity.db"
    monkeypatch.setenv("CHUZOM_IDENTITY_PATH", str(id_db))
    monkeypatch.setenv("CHUZOM_DEPLOYMENT_PROFILE", "enterprise")
    monkeypatch.delenv("CHUZOM_PROFILE", raising=False)
    monkeypatch.delenv("CHUZOM_RBAC_MODE", raising=False)  # profile drives it
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(tmp_path / "audit.db"))
    monkeypatch.setenv("CHUZOM_IDEMPOTENCY_PATH", str(tmp_path / "idem.db"))
    # Reset the resolver singletons so they pick up CHUZOM_IDENTITY_PATH.
    monkeypatch.setattr(identity_mod, "_enterprise_store", None)
    reset_audit_log_for_tests()
    reset_store_for_tests()
    return IdentityStore(db_path=id_db, check_same_thread=False)


def _token_for(store: IdentityStore, **user_kwargs: Any) -> str:
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id, email="alice@x",
        display_name="Alice", role=Role.EMPLOYEE, **user_kwargs,
    )
    return store.issue_token(user.id, name="laptop").plaintext


@pytest.mark.asyncio
async def test_token_allowlist_denies_disallowed_model_e2e(
    enterprise_identity_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Phase 3b headline. A token whose user is restricted to a
    provider that's in no production chain → ``route_and_call`` (which
    resolves the identity from the token) filters every candidate and
    raises ``PermissionDenied``. Proves the allow-list flows
    token → identity → the already-wired gate, with NO explicit
    CHUZOM_RBAC_MODE (the enterprise profile supplies strict)."""
    from chuzom.enterprise.rbac import PermissionDenied
    from chuzom.router import route_and_call
    from chuzom.types import TaskType

    token = _token_for(
        enterprise_identity_env,
        allowed_providers=frozenset({"no-such-provider"}),
    )
    monkeypatch.setenv("CHUZOM_TOKEN", token)
    with pytest.raises(PermissionDenied):
        await route_and_call(task_type=TaskType.QUERY, prompt="hi")


@pytest.mark.asyncio
async def test_unrestricted_token_routes_e2e(
    enterprise_identity_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A token whose user has no allow-list (None = unrestricted) routes
    normally under the enterprise profile — the absence of a policy must
    not deny-all."""
    from chuzom import router as router_mod
    from chuzom.router import route_and_call
    from chuzom.types import LLMResponse, TaskType

    token = _token_for(enterprise_identity_env)  # no allow-lists
    monkeypatch.setenv("CHUZOM_TOKEN", token)

    async def _fake_dispatch(**kwargs: Any) -> LLMResponse:
        models = kwargs.get("models_to_try", ["gemini/gemini-2.5-flash"])
        return LLMResponse(
            content="ok", model=models[0], provider="gemini",
            input_tokens=1, output_tokens=1, cost_usd=0.001, latency_ms=10.0,
        )

    monkeypatch.setattr(router_mod, "_dispatch_model_loop", _fake_dispatch)
    resp = await route_and_call(task_type=TaskType.QUERY, prompt="hi")
    assert resp.content == "ok"
