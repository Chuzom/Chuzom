"""Identity model + API tokens with hashed-at-rest secrets.

Three-level hierarchy: Org → Team → User. Each User can have multiple
APITokens scoped to specific permissions. Tokens are issued once with
a plaintext secret that the user records; the store only persists
SHA-256 hashes so a database leak yields no usable credentials.

Designed to integrate with external IdPs later (OIDC, SAML) without
schema changes: the User can carry an `external_id` referencing the
upstream identity provider's user ID.

SQLite-backed at ~/.tessera/identity.db. The schema is forward-compatible
with multi-tenancy — every row carries an org_id so the same database
could host multiple orgs, but v0.0.2 assumes single-org deployments.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from tessera.enterprise.rbac import Permission, Role


# ────────────────────────────────────────────────────────────────────────
# Dataclasses
# ────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Org:
    """Top-level tenant (a company)."""

    id: str
    name: str
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Team:
    """A group within an Org (e.g. 'engineering', 'data-science')."""

    id: str
    org_id: str
    name: str
    monthly_budget_usd: float = 0.0  # 0 means unlimited (use with care)
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class User:
    """A person who routes prompts through Tessera."""

    id: str
    org_id: str
    team_id: str
    email: str
    display_name: str
    role: Role
    external_id: str = ""  # set when OIDC/SAML federation is wired
    active: bool = True
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class APIToken:
    """A bearer credential issued to a User.

    plaintext is non-None ONLY when the token is freshly issued — the
    store never reads it back, so once the caller closes the session
    that holds it the plaintext is gone forever.
    """

    id: str
    user_id: str
    hash_hex: str  # SHA-256 of the plaintext
    name: str  # human-readable label (e.g. "Yali's laptop")
    permissions: tuple[Permission, ...]
    issued_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    revoked_at: float | None = None
    last_used_at: float | None = None
    plaintext: str | None = None  # set on issue only

    @property
    def is_active(self) -> bool:
        if self.revoked_at:
            return False
        if self.expires_at and self.expires_at < time.time():
            return False
        return True


@dataclass(frozen=True)
class Identity:
    """A validated principal carrying the User + their effective permissions.

    Returned by IdentityStore.authenticate() — this is what the routing
    layer attaches to each request for downstream RBAC checks.
    """

    user: User
    token: APIToken
    permissions: frozenset[Permission]


class IdentityNotFound(KeyError):
    """Raised when a user / token / team doesn't exist."""


class InvalidToken(ValueError):
    """Raised when a presented token is unknown, revoked, or expired."""


class IdentityConflict(ValueError):
    """Raised when an identity invariant is violated (duplicate email, etc.)."""


# ────────────────────────────────────────────────────────────────────────
# SQLite schema
# ────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES orgs(id),
    name TEXT NOT NULL,
    monthly_budget_usd REAL NOT NULL DEFAULT 0.0,
    created_at REAL NOT NULL,
    UNIQUE(org_id, name)
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES orgs(id),
    team_id TEXT NOT NULL REFERENCES teams(id),
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    external_id TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    hash_hex TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    permissions TEXT NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL,
    revoked_at REAL,
    last_used_at REAL
);

CREATE INDEX IF NOT EXISTS idx_tokens_hash ON api_tokens(hash_hex);
CREATE INDEX IF NOT EXISTS idx_tokens_user ON api_tokens(user_id);
"""


# ────────────────────────────────────────────────────────────────────────
# Token formatting + hashing
# ────────────────────────────────────────────────────────────────────────

_TOKEN_PREFIX = "tsr_"  # makes leaked tokens grep-able in logs/repos


def _generate_token_plaintext() -> str:
    """Produce a new opaque bearer token. 32 bytes of entropy."""
    return _TOKEN_PREFIX + secrets.token_urlsafe(32)


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────────────────
# Store
# ────────────────────────────────────────────────────────────────────────

class IdentityStore:
    """SQLite-backed identity store.

    Default location: ~/.tessera/identity.db. Override via the
    TESSERA_IDENTITY_PATH env var.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path(
            os.environ.get("TESSERA_IDENTITY_PATH")
            or (Path.home() / ".tessera" / "identity.db")
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── Orgs ──────────────────────────────────────────────────────────

    def create_org(self, name: str) -> Org:
        org = Org(id=str(uuid.uuid4()), name=name)
        try:
            self._conn.execute(
                "INSERT INTO orgs (id, name, created_at) VALUES (?, ?, ?)",
                (org.id, org.name, org.created_at),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise IdentityConflict(f"org name {name!r} already exists") from exc
        return org

    def get_org(self, org_id: str) -> Org:
        row = self._conn.execute(
            "SELECT id, name, created_at FROM orgs WHERE id = ?", (org_id,)
        ).fetchone()
        if not row:
            raise IdentityNotFound(f"org {org_id!r}")
        return Org(*row)

    # ── Teams ─────────────────────────────────────────────────────────

    def create_team(
        self, org_id: str, name: str, *, monthly_budget_usd: float = 0.0
    ) -> Team:
        # Validate org exists
        self.get_org(org_id)
        team = Team(
            id=str(uuid.uuid4()), org_id=org_id, name=name,
            monthly_budget_usd=monthly_budget_usd,
        )
        try:
            self._conn.execute(
                "INSERT INTO teams (id, org_id, name, monthly_budget_usd, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (team.id, team.org_id, team.name,
                 team.monthly_budget_usd, team.created_at),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise IdentityConflict(
                f"team name {name!r} already exists in org {org_id}"
            ) from exc
        return team

    def get_team(self, team_id: str) -> Team:
        row = self._conn.execute(
            "SELECT id, org_id, name, monthly_budget_usd, created_at "
            "FROM teams WHERE id = ?", (team_id,)
        ).fetchone()
        if not row:
            raise IdentityNotFound(f"team {team_id!r}")
        return Team(*row)

    # ── Users ─────────────────────────────────────────────────────────

    def create_user(
        self,
        *,
        org_id: str,
        team_id: str,
        email: str,
        display_name: str,
        role: Role,
        external_id: str = "",
    ) -> User:
        # Validate references
        self.get_org(org_id)
        self.get_team(team_id)
        user = User(
            id=str(uuid.uuid4()), org_id=org_id, team_id=team_id,
            email=email, display_name=display_name, role=role,
            external_id=external_id,
        )
        try:
            self._conn.execute(
                "INSERT INTO users (id, org_id, team_id, email, display_name, "
                "role, external_id, active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user.id, user.org_id, user.team_id, user.email,
                 user.display_name, user.role.value, user.external_id,
                 1 if user.active else 0, user.created_at),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise IdentityConflict(
                f"user with email {email!r} already exists"
            ) from exc
        return user

    def get_user(self, user_id: str) -> User:
        row = self._conn.execute(
            "SELECT id, org_id, team_id, email, display_name, role, "
            "external_id, active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            raise IdentityNotFound(f"user {user_id!r}")
        return User(
            id=row[0], org_id=row[1], team_id=row[2], email=row[3],
            display_name=row[4], role=Role(row[5]), external_id=row[6],
            active=bool(row[7]), created_at=row[8],
        )

    def get_user_by_email(self, email: str) -> User:
        row = self._conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not row:
            raise IdentityNotFound(f"user with email {email!r}")
        return self.get_user(row[0])

    def deactivate_user(self, user_id: str) -> None:
        """Soft-disable: existing tokens stay valid until they expire/are
        revoked. To kill access immediately, revoke all of the user's
        tokens via revoke_user_tokens."""
        self._conn.execute(
            "UPDATE users SET active = 0 WHERE id = ?", (user_id,)
        )
        self._conn.commit()

    # ── Tokens ────────────────────────────────────────────────────────

    def issue_token(
        self,
        user_id: str,
        *,
        name: str,
        permissions: tuple[Permission, ...] | None = None,
        expires_in_seconds: float | None = None,
    ) -> APIToken:
        """Create a new bearer token. The returned object has `plaintext`
        set to the raw token string — record it now; the store NEVER
        keeps a copy. permissions defaults to the user's role's grants."""
        from tessera.enterprise.rbac import permissions_for_role

        user = self.get_user(user_id)
        if not user.active:
            raise InvalidToken(
                f"cannot issue token for deactivated user {user_id}"
            )
        if permissions is None:
            permissions = tuple(sorted(
                permissions_for_role(user.role), key=lambda p: p.value
            ))
        plaintext = _generate_token_plaintext()
        token = APIToken(
            id=str(uuid.uuid4()), user_id=user_id,
            hash_hex=_hash_token(plaintext),
            name=name,
            permissions=tuple(permissions),
            expires_at=(
                time.time() + expires_in_seconds
                if expires_in_seconds else None
            ),
            plaintext=plaintext,
        )
        self._conn.execute(
            "INSERT INTO api_tokens (id, user_id, hash_hex, name, permissions, "
            "issued_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (token.id, token.user_id, token.hash_hex, token.name,
             ",".join(p.value for p in token.permissions),
             token.issued_at, token.expires_at),
        )
        self._conn.commit()
        return token

    def revoke_token(self, token_id: str) -> None:
        self._conn.execute(
            "UPDATE api_tokens SET revoked_at = ? WHERE id = ?",
            (time.time(), token_id),
        )
        self._conn.commit()

    def revoke_user_tokens(self, user_id: str) -> int:
        """Revoke every token belonging to a user. Returns count revoked."""
        cursor = self._conn.execute(
            "UPDATE api_tokens SET revoked_at = ? "
            "WHERE user_id = ? AND revoked_at IS NULL",
            (time.time(), user_id),
        )
        self._conn.commit()
        return cursor.rowcount

    def authenticate(self, presented_token: str) -> Identity:
        """Validate a presented bearer token. Raises InvalidToken on any
        failure (unknown / revoked / expired / deactivated user).

        Updates last_used_at on success for audit purposes.
        """
        if not presented_token or not presented_token.startswith(_TOKEN_PREFIX):
            raise InvalidToken("token must start with 'tsr_'")
        hash_hex = _hash_token(presented_token)
        row = self._conn.execute(
            "SELECT id, user_id, name, permissions, issued_at, expires_at, "
            "revoked_at, last_used_at FROM api_tokens WHERE hash_hex = ?",
            (hash_hex,),
        ).fetchone()
        if not row:
            raise InvalidToken("unknown token")
        token = APIToken(
            id=row[0], user_id=row[1], hash_hex=hash_hex,
            name=row[2],
            permissions=tuple(
                Permission(p) for p in row[3].split(",") if p
            ),
            issued_at=row[4], expires_at=row[5],
            revoked_at=row[6], last_used_at=row[7],
        )
        if not token.is_active:
            raise InvalidToken(
                "revoked" if token.revoked_at else "expired"
            )
        user = self.get_user(token.user_id)
        if not user.active:
            raise InvalidToken("user deactivated")
        # Touch last_used_at
        self._conn.execute(
            "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
            (time.time(), token.id),
        )
        self._conn.commit()
        return Identity(
            user=user, token=token,
            permissions=frozenset(token.permissions),
        )

    def close(self) -> None:
        self._conn.close()
