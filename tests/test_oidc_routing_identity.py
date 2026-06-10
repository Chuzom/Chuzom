"""Integration: an OIDC JWT in CHUZOM_TOKEN resolves through current_identity().

Proves the wiring end-to-end on the real routing resolver: enterprise profile +
CHUZOM_OIDC_ISSUER + a valid signed JWT → JIT-provisioned TurnIdentity. No network
(JWKS injected) and no real IdP.
"""
from __future__ import annotations

import json
import time

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

import chuzom.identity as idmod  # noqa: E402
from chuzom.enterprise.identity import IdentityStore  # noqa: E402
from chuzom.enterprise.oidc import OidcConfig, OidcValidator  # noqa: E402
from chuzom.enterprise.rbac import Role  # noqa: E402

ISSUER = "https://idp.test/realms/chuzom"
AUD = "chuzom"
KID = "k1"


@pytest.fixture
def federated(tmp_path, monkeypatch):
    """Wire an enterprise+OIDC environment with an injected-JWKS validator."""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    jwks = {"keys": [jwk]}

    def mint(*, sub="okta|99", email="sso@acme.com", groups=("chuzom-admins",)):
        now = int(time.time())
        payload = {
            "sub": sub, "email": email, "groups": list(groups),
            "iss": ISSUER, "aud": AUD, "iat": now, "nbf": now, "exp": now + 300,
        }
        return jwt.encode(payload, priv, algorithm="RS256", headers={"kid": KID})

    store = IdentityStore(db_path=tmp_path / "identity.db")
    cfg = OidcConfig(issuer=ISSUER, audience=AUD,
                     jwks_uri="https://idp.test/never-fetched",
                     role_map={"chuzom-admins": Role.ADMIN, "chuzom-users": Role.EMPLOYEE})
    monkeypatch.setattr(idmod, "_enterprise_store", store)
    monkeypatch.setattr(idmod, "_oidc_validator", OidcValidator(cfg, jwks=jwks))
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("CHUZOM_OIDC_AUDIENCE", AUD)
    yield mint, store
    store.close()


def test_oidc_token_resolves_and_provisions(federated, monkeypatch):
    mint, store = federated
    monkeypatch.setenv("CHUZOM_TOKEN", mint())
    ident = idmod.current_identity()
    assert ident.user_email == "sso@acme.com"
    assert ident.org_id  # default org auto-created
    # The user was JIT-provisioned with the admin role + IdP subject.
    user = store.get_user_by_email("sso@acme.com")
    assert user.role == Role.ADMIN
    assert user.external_id == "okta|99"


def test_second_login_is_idempotent(federated, monkeypatch):
    mint, store = federated
    monkeypatch.setenv("CHUZOM_TOKEN", mint())
    first = idmod.current_identity()
    second = idmod.current_identity()
    assert first.user_id == second.user_id
    rows = store._conn.execute(
        "SELECT COUNT(*) FROM users WHERE email = ?", ("sso@acme.com",)
    ).fetchone()[0]
    assert rows == 1


def test_employee_group_maps_to_employee(federated, monkeypatch):
    mint, store = federated
    monkeypatch.setenv("CHUZOM_TOKEN", mint(email="dev@acme.com", groups=("chuzom-users",)))
    idmod.current_identity()
    assert store.get_user_by_email("dev@acme.com").role == Role.EMPLOYEE


def test_invalid_oidc_token_raises(federated, monkeypatch):
    mint, store = federated
    monkeypatch.setenv("CHUZOM_TOKEN", "garbage.not.a.jwt")
    with pytest.raises(idmod.EnterpriseIdentityRequired):
        idmod.current_identity()


def test_dev_profile_ignores_oidc(federated, monkeypatch):
    mint, store = federated
    monkeypatch.setenv("CHUZOM_PROFILE", "developer")
    monkeypatch.setenv("CHUZOM_USER_ID", "alice")
    monkeypatch.delenv("CHUZOM_TOKEN", raising=False)
    ident = idmod.current_identity()
    assert ident.user_id == "alice"  # env-trust path, OIDC never consulted
