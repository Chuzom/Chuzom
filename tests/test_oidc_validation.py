"""Hermetic OIDC validation tests — local RSA key + injected JWKS, no network.

JWT-first: the validator needs only a JWKS (to find the public key by `kid`) and
a signed token. We mint both in-process so CI never calls an IdP.
"""
from __future__ import annotations

import json
import time

import pytest

# The sso extra (PyJWT[crypto]) must be present to run these.
jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from chuzom.enterprise.oidc import (  # noqa: E402
    OidcClaims,
    OidcConfig,
    OidcError,
    OidcValidator,
    _coerce_groups,
    _parse_role_map,
)
from chuzom.enterprise.rbac import Role  # noqa: E402

TEST_KID = "chuzom-test-key-1"
TEST_ISSUER = "https://idp.test/realms/chuzom"
TEST_AUDIENCE = "chuzom"


@pytest.fixture(scope="module")
def keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


@pytest.fixture(scope="module")
def jwks(keypair):
    _, public_key = keypair
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": TEST_KID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


@pytest.fixture
def mint(keypair):
    priv, _ = keypair

    def _mint(
        *,
        sub="okta|abc123",
        email="dev@acme.com",
        groups=None,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        kid=TEST_KID,
        expires_in=300,
        sign_key=None,
        omit=(),
        extra=None,
    ):
        now = int(time.time())
        payload = {
            "sub": sub,
            "email": email,
            "groups": ["chuzom-users"] if groups is None else groups,
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "nbf": now,
            "exp": now + expires_in,
        }
        for k in omit:
            payload.pop(k, None)
        if extra:
            payload.update(extra)
        return jwt.encode(payload, sign_key or priv, algorithm="RS256",
                          headers={"kid": kid})

    return _mint


def _cfg():
    return OidcConfig(
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        jwks_uri="https://idp.test/never-fetched",
        role_map={"chuzom-admins": Role.ADMIN, "chuzom-users": Role.EMPLOYEE},
    )


async def test_valid_token_yields_claims(jwks, mint):
    v = OidcValidator(_cfg(), jwks=jwks)
    claims = await v.validate(mint(email="dev@acme.com", groups=["chuzom-admins"]))
    assert isinstance(claims, OidcClaims)
    assert claims.email == "dev@acme.com"
    assert claims.subject == "okta|abc123"
    assert v.map_role(claims.groups) == Role.ADMIN


async def test_employee_default_when_no_group_matches(jwks, mint):
    v = OidcValidator(_cfg(), jwks=jwks)
    claims = await v.validate(mint(groups=["unmapped-group"]))
    assert v.map_role(claims.groups) == Role.EMPLOYEE


async def test_highest_privilege_group_wins(jwks, mint):
    v = OidcValidator(_cfg(), jwks=jwks)
    claims = await v.validate(mint(groups=["chuzom-users", "chuzom-admins"]))
    assert v.map_role(claims.groups) == Role.ADMIN


async def test_expired_token_rejected(jwks, mint):
    v = OidcValidator(_cfg(), jwks=jwks)
    # Beyond the 30s leeway so it is unambiguously expired.
    with pytest.raises(OidcError, match="expired"):
        await v.validate(mint(expires_in=-120))


async def test_wrong_audience_rejected(jwks, mint):
    v = OidcValidator(_cfg(), jwks=jwks)
    with pytest.raises(OidcError, match="audience"):
        await v.validate(mint(audience="some-other-app"))


async def test_wrong_issuer_rejected(jwks, mint):
    v = OidcValidator(_cfg(), jwks=jwks)
    with pytest.raises(OidcError, match="issuer"):
        await v.validate(mint(issuer="https://evil.test"))


async def test_forged_signature_rejected(jwks, mint):
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    v = OidcValidator(_cfg(), jwks=jwks)
    with pytest.raises(OidcError):
        await v.validate(mint(sign_key=attacker))


async def test_unknown_kid_rejected(jwks, mint):
    v = OidcValidator(_cfg(), jwks=jwks)
    with pytest.raises(OidcError, match="signing key"):
        await v.validate(mint(kid="does-not-exist"))


async def test_missing_email_claim_rejected(jwks, mint):
    v = OidcValidator(_cfg(), jwks=jwks)
    with pytest.raises(OidcError, match="email"):
        await v.validate(mint(omit=("email",)))


async def test_malformed_token_rejected(jwks):
    v = OidcValidator(_cfg(), jwks=jwks)
    with pytest.raises(OidcError):
        await v.validate("not-a-jwt")


def test_role_map_parsing():
    m = _parse_role_map("admins=admin, users=employee, junk, bad=nope")
    assert m == {"admins": Role.ADMIN, "users": Role.EMPLOYEE}


def test_groups_coercion_variants():
    assert _coerce_groups(["a", "b"]) == ("a", "b")
    assert _coerce_groups("a b c") == ("a", "b", "c")
    assert _coerce_groups("a,b,c") == ("a", "b", "c")
    assert _coerce_groups(None) == ()
