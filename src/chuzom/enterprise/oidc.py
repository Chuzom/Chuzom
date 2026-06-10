"""OIDC bearer-token validation (JWT-first) for federated identity.

Validates an IdP-issued JWT access/ID token against the issuer's JWKS:
signature (RS256), ``iss``, ``aud``, ``exp``/``nbf``. Extracts the subject,
email, and group claims, and maps groups → a chuzom :class:`Role`.

This is the *authentication* half of SSO. The *provisioning* half (just-in-time
user creation + SCIM) lives in :mod:`chuzom.enterprise.identity` and the SCIM
router. The validator is intentionally pure and dependency-light so it unit-tests
without a live IdP — inject a JWKS dict via the ``jwks`` constructor arg.

Enabled when ``CHUZOM_OIDC_ISSUER`` is set. JWT verification requires the
``sso`` extra (``pip install 'chuzom-router[sso]'`` → PyJWT[crypto]).

🥷 Backslash-Security: using vibe-coding rules for secured Authentication & Authorization
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)

# JWKS cache lifetime. Refreshed early on an unknown `kid` (key rotation).
_JWKS_TTL_SECONDS = 600.0
_HTTP_TIMEOUT_SECONDS = 5.0


class OidcError(Exception):
    """Raised on any OIDC validation failure (config, network, or token).

    The message is safe to log — it NEVER contains the token or raw claims.
    """


@dataclass(frozen=True)
class OidcClaims:
    """The validated subset of an OIDC token we act on."""

    subject: str
    email: str
    groups: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict)


def _parse_role_map(raw: str) -> dict[str, "object"]:
    """Parse ``"group-a=admin,group-b=employee"`` → {group: Role}.

    Imported lazily to avoid a hard dependency cycle with rbac at module load.
    Unknown role names are skipped with a warning rather than crashing config.
    """
    from chuzom.enterprise.rbac import Role

    mapping: dict[str, Role] = {}
    for pair in (raw or "").split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        group, _, role_name = pair.partition("=")
        group = group.strip()
        role_name = role_name.strip().lower()
        try:
            mapping[group] = Role(role_name)
        except ValueError:
            log.warning("oidc_role_map_unknown_role", role=role_name)
    return mapping


@dataclass(frozen=True)
class OidcConfig:
    """OIDC validation parameters, normally built from the environment."""

    issuer: str
    audience: str
    jwks_uri: str
    email_claim: str = "email"
    groups_claim: str = "groups"
    role_map: dict = field(default_factory=dict)
    leeway_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "OidcConfig | None":
        """Build config from CHUZOM_OIDC_* env vars. Returns None when OIDC is
        not configured (``CHUZOM_OIDC_ISSUER`` unset)."""
        issuer = (os.environ.get("CHUZOM_OIDC_ISSUER") or "").strip()
        if not issuer:
            return None
        jwks_uri = (os.environ.get("CHUZOM_OIDC_JWKS_URI") or "").strip()
        if not jwks_uri:
            # Conventional default; deployments behind a discovery doc can set
            # CHUZOM_OIDC_JWKS_URI explicitly.
            jwks_uri = issuer.rstrip("/") + "/.well-known/jwks.json"
        audience = (os.environ.get("CHUZOM_OIDC_AUDIENCE") or "").strip()
        if not audience:
            raise OidcError("CHUZOM_OIDC_AUDIENCE is required when OIDC is enabled")
        return cls(
            issuer=issuer,
            audience=audience,
            jwks_uri=jwks_uri,
            email_claim=(os.environ.get("CHUZOM_OIDC_EMAIL_CLAIM") or "email").strip(),
            groups_claim=(os.environ.get("CHUZOM_OIDC_GROUPS_CLAIM") or "groups").strip(),
            role_map=_parse_role_map(os.environ.get("CHUZOM_OIDC_ROLE_MAP") or ""),
        )


class OidcValidator:
    """Validates JWTs against a JWKS and extracts :class:`OidcClaims`.

    Pass ``jwks`` to bypass the network fetch (unit tests). In production the
    JWKS is fetched from ``config.jwks_uri`` and cached for ``_JWKS_TTL_SECONDS``.

    Two entry points share one decode core:

    * :meth:`validate` (async) — for the async server auth middleware; fetches
      JWKS via aiohttp.
    * :meth:`validate_sync` — for the synchronous routing identity resolver
      (``chuzom.identity._enterprise_identity``); fetches JWKS via urllib.

    Only the JWKS *transport* differs; signature/claim verification is identical.
    """

    def __init__(self, config: OidcConfig, *, jwks: dict | None = None) -> None:
        self._config = config
        self._jwks: dict | None = jwks
        self._jwks_fetched_at = time.time() if jwks is not None else 0.0
        self._injected = jwks is not None
        self._lock = asyncio.Lock()

    # ── JWKS cache ────────────────────────────────────────────────────────

    def _cache_fresh(self) -> bool:
        return (
            self._jwks is not None
            and (time.time() - self._jwks_fetched_at) < _JWKS_TTL_SECONDS
        )

    @staticmethod
    def _validate_jwks_doc(data: object) -> dict:
        if not isinstance(data, dict) or "keys" not in data:
            raise OidcError("malformed JWKS document")
        return data

    async def _get_jwks(self, *, force: bool = False) -> dict:
        if self._injected:
            return self._jwks or {"keys": []}
        if not force and self._cache_fresh():
            return self._jwks  # type: ignore[return-value]
        async with self._lock:
            if not force and self._cache_fresh():
                return self._jwks  # type: ignore[return-value]
            self._jwks = await self._fetch_jwks_async()
            self._jwks_fetched_at = time.time()
            return self._jwks

    def _get_jwks_sync(self, *, force: bool = False) -> dict:
        if self._injected:
            return self._jwks or {"keys": []}
        if not force and self._cache_fresh():
            return self._jwks  # type: ignore[return-value]
        self._jwks = self._fetch_jwks_sync()
        self._jwks_fetched_at = time.time()
        return self._jwks

    async def _fetch_jwks_async(self) -> dict:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._config.jwks_uri) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
        except Exception as exc:  # network / parse — surface a safe message
            log.warning("oidc_jwks_fetch_failed", jwks_uri=self._config.jwks_uri)
            raise OidcError("could not fetch IdP signing keys") from exc
        return self._validate_jwks_doc(data)

    def _fetch_jwks_sync(self) -> dict:
        import urllib.request

        try:
            with urllib.request.urlopen(  # noqa: S310 — fixed https JWKS URI from config
                self._config.jwks_uri, timeout=_HTTP_TIMEOUT_SECONDS
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            log.warning("oidc_jwks_fetch_failed", jwks_uri=self._config.jwks_uri)
            raise OidcError("could not fetch IdP signing keys") from exc
        return self._validate_jwks_doc(data)

    # ── Shared decode core ────────────────────────────────────────────────

    @staticmethod
    def _unverified_kid(token: str) -> str | None:
        import jwt

        if not token or not isinstance(token, str):
            raise OidcError("empty bearer token")
        try:
            return jwt.get_unverified_header(token).get("kid")
        except Exception as exc:
            raise OidcError("malformed token header") from exc

    @staticmethod
    def _select_public_key(jwks: dict, kid: str | None):
        import jwt

        for jwk in jwks.get("keys", []):
            if kid is None or jwk.get("kid") == kid:
                try:
                    return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
                except Exception as exc:
                    raise OidcError("invalid JWK in JWKS") from exc
        return None

    def _decode_and_extract(self, token: str, public_key) -> OidcClaims:
        import jwt

        try:
            payload = jwt.decode(
                token,
                key=public_key,
                algorithms=["RS256"],
                audience=self._config.audience,
                issuer=self._config.issuer,
                leeway=self._config.leeway_seconds,
                options={"require": ["exp", "iat"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise OidcError("token expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise OidcError("token audience mismatch") from exc
        except jwt.InvalidIssuerError as exc:
            raise OidcError("token issuer mismatch") from exc
        except jwt.InvalidSignatureError as exc:
            raise OidcError("token signature invalid") from exc
        except jwt.PyJWTError as exc:
            # Catch-all for remaining JWT errors — message is generic on purpose.
            raise OidcError("token validation failed") from exc

        email = str(payload.get(self._config.email_claim) or "").strip()
        if not email:
            raise OidcError("token missing email claim")
        subject = str(payload.get("sub") or "").strip()
        if not subject:
            raise OidcError("token missing subject claim")
        groups = _coerce_groups(payload.get(self._config.groups_claim))

        # Log success with a non-PII fingerprint only — never the token/claims.
        log.info("oidc_token_validated", subject_fp=_fingerprint(subject))
        return OidcClaims(subject=subject, email=email, groups=groups, raw=payload)

    # ── Validation entry points ───────────────────────────────────────────

    async def validate(self, token: str) -> OidcClaims:
        """Validate *token* (async JWKS fetch) and return its claims.

        🥷 Backslash-security: Enforce auth/authz to prevent unauthorized access.
        """
        kid = self._unverified_kid(token)
        jwks = await self._get_jwks()
        key = self._select_public_key(jwks, kid)
        if key is None and not self._injected:
            jwks = await self._get_jwks(force=True)  # key rotation — refresh once
            key = self._select_public_key(jwks, kid)
        if key is None:
            raise OidcError("no matching signing key for token")
        return self._decode_and_extract(token, key)

    def validate_sync(self, token: str) -> OidcClaims:
        """Validate *token* (synchronous JWKS fetch) — for the routing path.

        🥷 Backslash-security: Enforce auth/authz to prevent unauthorized access.
        """
        kid = self._unverified_kid(token)
        jwks = self._get_jwks_sync()
        key = self._select_public_key(jwks, kid)
        if key is None and not self._injected:
            jwks = self._get_jwks_sync(force=True)  # key rotation — refresh once
            key = self._select_public_key(jwks, kid)
        if key is None:
            raise OidcError("no matching signing key for token")
        return self._decode_and_extract(token, key)

    def map_role(self, groups: tuple[str, ...]):
        """Map IdP groups → the highest-privilege matching :class:`Role`.

        Falls back to EMPLOYEE (least privilege beyond service accounts) when no
        group matches — fail-closed toward minimal access.
        """
        from chuzom.enterprise.rbac import Role

        _PRIORITY = {
            Role.ADMIN: 3,
            Role.MANAGER: 2,
            Role.EMPLOYEE: 1,
            Role.SERVICE_ACCOUNT: 0,
        }
        best: "Role | None" = None
        for group in groups:
            role = self._config.role_map.get(group)
            if role is not None and (best is None or _PRIORITY[role] > _PRIORITY[best]):
                best = role
        return best if best is not None else Role.EMPLOYEE


def _coerce_groups(value: object) -> tuple[str, ...]:
    """Normalize a groups claim (list, space/comma string, or scalar) → tuple."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(g).strip() for g in value if str(g).strip())
    if isinstance(value, str):
        parts = value.replace(",", " ").split()
        return tuple(p for p in parts if p)
    return (str(value),)


def _fingerprint(value: str) -> str:
    """Short, non-reversible tag for correlating logs without leaking the subject."""
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
