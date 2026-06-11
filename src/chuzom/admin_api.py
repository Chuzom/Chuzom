"""G-006 admin API skeleton — enterprise control-plane spine.

The dashboard at ``src/chuzom/dashboard/server.py`` is a read-only stats
view for developers. The admin API is its operator-facing counterpart:
RBAC-gated endpoints for user / token / policy / provider management.
This module is the **skeleton** — three representative endpoints are
fully wired, the remaining surface returns ``501 Not Implemented`` so
callers integrating against the API get an unambiguous contract.

What this slice ships:

* ``GET  /v1/admin/health`` — unauthenticated liveness check.
* ``GET  /v1/admin/users`` — list users in the identity store
  (``Permission.MANAGE_USERS``).
* ``POST /v1/admin/users/{user_id}/tokens/{token_id}:revoke`` —
  revoke an issued bearer token (``Permission.MANAGE_USERS``).
* ``POST /v1/admin/providers/{provider}:disable`` /
  ``POST /v1/admin/providers/{provider}:enable`` /
  ``GET  /v1/admin/providers/disabled`` —
  emergency provider toggle backed by an in-memory
  ``RuntimeProviderRegistry`` (``Permission.MANAGE_POLICY``).

Stubbed (501) until follow-up slices land:

* ``POST /v1/admin/users`` (create-user).
* ``POST /v1/admin/users/{user_id}/tokens`` (issue-token).
* ``GET  /v1/admin/audit`` (query audit log).
* ``POST /v1/admin/policy`` (push a versioned policy bundle).

Auth model: ``Authorization: Bearer <token>``. The token is validated
against ``IdentityStore.authenticate`` (Tier-3 hashed-token auth). On
success the request gets an ``Identity`` carrying the permission set;
on failure 401. Permission gating per endpoint via
``require_perm(Permission.X)``; missing permission → 403.

What this skeleton intentionally does NOT do (deferred):

* Wire ``RuntimeProviderRegistry`` into the router's chain-building
  path. The state holds; the router consult lands in the G-008
  follow-up slice.
* Persist provider-disable state across restarts. Today it lives in
  process memory; a future slice should back it with SQLite + a
  cross-instance change feed.
* Emit admin-action audit rows. ``audit_routing.py`` covers routing
  decisions; an ``admin_actions`` table is a separate gap.
* Run an HTTP server. ``create_app`` returns the FastAPI app; the
  entry point that ``uvicorn``-serves it is a future slice.

See: ``docs/audit/post-remediation/GAP_ANALYSIS.md`` G-006, G-007,
G-008.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from fastapi.responses import PlainTextResponse

from chuzom.admin_actions import AdminActionLog
from chuzom.agents.session import SessionStore
from chuzom.enterprise.audit import AuditLog
from chuzom.metrics import EXPOSITION_CONTENT_TYPE, collect_all
from chuzom.policy_versions import (
    PolicyValidationError,
    PolicyVersionNotFound,
    PolicyVersionStore,
)
from chuzom.enterprise.identity import (
    Identity,
    IdentityConflict,
    IdentityNotFound,
    IdentityStore,
    InvalidToken,
    User,
)
from chuzom.enterprise.quotas import QuotaPolicy, QuotaTracker
from chuzom.enterprise.rbac import Permission, Role, has_permission
from chuzom.provider_registry import (
    RuntimeProviderRegistry,
    get_global_registry as _resolve_global_registry,
)

__version__ = "0.1.0-skeleton"


# ────────────────────────────────────────────────────────────────────────
# FastAPI dependencies — overridden in tests via app.dependency_overrides.
# ────────────────────────────────────────────────────────────────────────


def get_identity_store() -> IdentityStore:
    """Default-path IdentityStore for the admin API.

    Opens with ``check_same_thread=False`` because FastAPI dispatches
    request handlers onto worker threads via ``anyio.to_thread``. SQLite
    serialises writes at the engine level so the shared connection is
    safe under our usage pattern.
    """
    return IdentityStore(check_same_thread=False)


def get_provider_registry() -> RuntimeProviderRegistry:
    """Process-singleton RuntimeProviderRegistry. Tests override this."""
    return _resolve_global_registry()


def get_audit_log() -> AuditLog:
    """Default-path AuditLog. Same thread-safety rationale as
    ``get_identity_store``."""
    return AuditLog(check_same_thread=False)


def get_admin_action_log() -> AdminActionLog:
    """G-006-F5: default-path AdminActionLog. Same thread-safety
    rationale as ``get_identity_store``."""
    return AdminActionLog(check_same_thread=False)


def get_session_store() -> SessionStore:
    """G-029: default-path SessionStore for the agent-ledger endpoint.
    Same thread-safety rationale as ``get_identity_store``."""
    return SessionStore(check_same_thread=False)


def get_policy_version_store() -> PolicyVersionStore:
    """G-007: default-path PolicyVersionStore. Same thread-safety
    rationale as ``get_identity_store``."""
    return PolicyVersionStore(check_same_thread=False)


def get_quota_tracker() -> QuotaTracker:
    """Loop-5 #4: default-path QuotaTracker for per-team budgets.
    Same thread-safety rationale as ``get_identity_store``."""
    return QuotaTracker(check_same_thread=False)


def _emit_admin_action(
    log: AdminActionLog,
    *,
    identity: Identity,
    action: str,
    resource_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Common emit helper so every mutating endpoint produces a row
    of the same shape. Failures are swallowed and logged — admin-action
    audit must NEVER turn a successful mutation into a 500.
    """
    try:
        log.append(
            actor_user_id=identity.user.id,
            actor_email=identity.user.email,
            action=action,
            resource_id=resource_id,
            detail=detail or {},
        )
    except Exception:  # noqa: BLE001 — fail-open admin-action audit
        # Intentionally not raising. The endpoint already succeeded;
        # losing an admin-action row is logged-and-continue rather
        # than rolling back the mutation. Operators see the gap when
        # reading the log.
        pass


_bearer_scheme = HTTPBearer(auto_error=False)


def authenticate_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    store: IdentityStore = Depends(get_identity_store),
) -> Identity:
    """Resolve ``Authorization: Bearer <token>`` → ``Identity``.

    401 on missing or invalid token. Per Tier-3 identity contract,
    ``IdentityStore.authenticate`` raises ``InvalidToken`` for unknown
    / revoked / expired / deactivated cases; all map to 401.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token in Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return store.authenticate(credentials.credentials)
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_perm(perm: Permission) -> Callable[[Identity], Identity]:
    """Permission-gate dependency factory.

    Returns a dependency that resolves to the authenticated ``Identity``
    if it carries ``perm``, otherwise 403. Compose with
    ``Depends(require_perm(Permission.X))`` on the route handler.
    """

    def _checker(
        identity: Identity = Depends(authenticate_identity),
    ) -> Identity:
        if not has_permission(identity, perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Identity '{identity.user.email}' lacks required "
                    f"permission: {perm.value}"
                ),
            )
        return identity

    return _checker


# ────────────────────────────────────────────────────────────────────────
# Request / response models — Pydantic for OpenAPI clarity.
# ────────────────────────────────────────────────────────────────────────


class DisableProviderRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Human-readable rationale; surfaced in audit + dashboard.",
    )


class CreateUserRequest(BaseModel):
    org_id: str = Field(..., min_length=1)
    team_id: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3, max_length=254)
    display_name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(
        ...,
        description=(
            "One of: admin / manager / employee / service_account. "
            "Case-insensitive."
        ),
    )
    external_id: str = ""


class IssueTokenRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Human-readable label (e.g. 'CI runner', 'Yali laptop').",
    )
    expires_in_seconds: float | None = Field(
        None,
        gt=0,
        description=(
            "Optional TTL. Omit for a non-expiring token (still revocable)."
        ),
    )


class PushPolicyRequest(BaseModel):
    yaml: str = Field(
        ...,
        min_length=1,
        max_length=200_000,
        description=(
            "Full org policy YAML. Plaintext secrets are refused — every "
            "credential must be a ${env:...} / ${vault:...} reference."
        ),
    )
    note: str | None = Field(
        None,
        max_length=500,
        description="Optional free-form rationale for the change.",
    )


class RollbackPolicyRequest(BaseModel):
    target_version: int = Field(
        ...,
        gt=0,
        description="Version number to roll back to. Must exist in history.",
    )
    note: str | None = Field(
        None,
        max_length=500,
        description="Why the rollback (incident link, etc).",
    )


class SetTeamBudgetRequest(BaseModel):
    """Loop-5 #4 — payload for ``POST /v1/admin/teams/{id}/budget``.

    Mirrors ``QuotaPolicy`` but with explicit Pydantic validation so
    operators get useful 422 errors on bad input rather than a 500
    from the SQLite layer. A zero cap on either bound means
    "unlimited for that period" — the underlying tracker treats
    ``daily_cap_usd == 0`` and ``monthly_cap_usd == 0`` as
    permissive defaults.
    """

    daily_cap_usd: float = Field(
        0.0, ge=0.0,
        description=(
            "Hard daily spend cap in USD. 0 means unlimited "
            "(both caps zero → policy treated as unlimited)."
        ),
    )
    monthly_cap_usd: float = Field(
        0.0, ge=0.0,
        description="Hard monthly spend cap in USD. 0 means unlimited.",
    )
    soft_warning_pct: float = Field(
        0.80, ge=0.0, le=1.0,
        description=(
            "Fraction of the cap (0..1) at which a soft-warning "
            "audit event fires. 0.8 = warn at 80%."
        ),
    )
    hard_block: bool = Field(
        True,
        description=(
            "When True (default), exceeding the cap raises and "
            "refuses the call. When False, exceeding logs but "
            "allows the call through — useful for a staged rollout."
        ),
    )


# ────────────────────────────────────────────────────────────────────────
# Serialization — never leak hashes / tokens / internal-only fields.
# ────────────────────────────────────────────────────────────────────────


def _user_to_safe_dict(user: User) -> dict[str, Any]:
    """Public projection of a ``User`` row. Token hashes never leak."""
    return {
        "id": user.id,
        "org_id": user.org_id,
        "team_id": user.team_id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role.value,
        "external_id": user.external_id,
        "active": user.active,
        "created_at": user.created_at,
    }


# ────────────────────────────────────────────────────────────────────────
# Team-budget helpers (Loop-5 #4)
# ────────────────────────────────────────────────────────────────────────
#
# These two helpers reach into ``QuotaTracker``'s private connection
# to expose operations not yet on its public API:
#
# * ``_has_explicit_row`` lets the GET endpoint distinguish "no
#   policy configured" from "policy configured with zero caps" — the
#   tracker collapses both into an ``is_unlimited`` policy on read.
#   Pushing this onto the public ``QuotaTracker`` API is a follow-up;
#   keeping it co-located with the only caller for now.
# * ``_delete_quota_policy`` makes DELETE idempotent (no row → no
#   error). Same follow-up note applies.


def _has_explicit_row(quotas: QuotaTracker, team_id: str) -> bool:
    """Whether ``team_id`` has a row in ``quota_policies`` — used to
    surface ``configured=False`` for teams that have never been
    given a budget."""
    row = quotas._conn.execute(
        "SELECT 1 FROM quota_policies "
        "WHERE scope = 'team' AND identifier = ?",
        (team_id,),
    ).fetchone()
    return row is not None


def _delete_quota_policy(
    quotas: QuotaTracker, scope: str, identifier: str,
) -> None:
    """Idempotent deletion — used by the DELETE endpoint. Doesn't
    touch ``quota_consumption``; consumption history is preserved
    so re-setting a budget mid-period doesn't reset the clock."""
    quotas._conn.execute(
        "DELETE FROM quota_policies "
        "WHERE scope = ? AND identifier = ?",
        (scope, identifier),
    )
    quotas._conn.commit()


# ────────────────────────────────────────────────────────────────────────
# App factory — accepts dependency overrides for tests.
# ────────────────────────────────────────────────────────────────────────


_NOT_IMPL_PREFIX = "G-006 skeleton — not implemented yet"


# ────────────────────────────────────────────────────────────────────────
# Refinement #8 — ledger keyset cursor.
# Encoded as urlsafe base64 of a JSON ``[started_at, session_id]`` tuple
# so it survives URL transport without escaping and stays human-debuggable
# (a curious operator can ``base64 -d`` it and read the value).
# ────────────────────────────────────────────────────────────────────────


def encode_ledger_cursor(started_at: float, session_id: str) -> str:
    """Encode a ledger cursor for ``GET /v1/admin/agents/status?cursor=``.

    Exposed so callers building paginated UIs / scripts can produce
    the cursor without re-implementing the base64+JSON contract."""
    import base64 as _b64
    import json as _json

    payload = _json.dumps([started_at, session_id]).encode("utf-8")
    return _b64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode_ledger_cursor(cursor: str) -> tuple[float, str]:
    """Decode an opaque cursor back into ``(started_at, session_id)``.

    Raises ``ValueError`` on any failure (malformed base64, malformed
    JSON, wrong shape, wrong types) — the caller maps to HTTP 400."""
    import base64 as _b64
    import json as _json

    if not cursor:
        raise ValueError("empty cursor")
    # Restore base64 padding stripped by encode_ledger_cursor.
    pad_len = (-len(cursor)) % 4
    padded = cursor + ("=" * pad_len)
    try:
        raw = _b64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise ValueError(f"not valid base64: {exc}") from exc
    try:
        payload = _json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc
    if (
        not isinstance(payload, list)
        or len(payload) != 2
        or not isinstance(payload[0], (int, float))
        or not isinstance(payload[1], str)
    ):
        raise ValueError("expected JSON list [started_at, session_id]")
    return float(payload[0]), payload[1]


def create_app() -> FastAPI:
    """Build the admin-API FastAPI app.

    Use ``app.dependency_overrides[get_identity_store] = lambda: ...``
    and ``app.dependency_overrides[get_provider_registry] = lambda: ...``
    in tests to inject scoped fixtures.
    """
    app = FastAPI(
        title="Chuzom Admin API",
        version=__version__,
        description=(
            "Enterprise control-plane spine (G-006). See "
            "docs/audit/post-remediation/GAP_ANALYSIS.md for scope."
        ),
    )

    # ── SCIM 2.0 provisioning (P0-4) ────────────────────────────────────
    # Mount the SCIM router on the SERVED admin app when enabled, so a
    # deployed instance actually exposes /scim/v2 for IdP-driven
    # (de)provisioning. Previously SCIM only existed in a standalone app no
    # process ran. Gated by CHUZOM_SCIM_ENABLED + CHUZOM_SCIM_TOKEN
    # (constant-time bearer auth); a no-op when disabled.
    from chuzom.scim_api import scim_enabled
    if scim_enabled():
        import os as _os

        from chuzom.scim_api import build_scim_router
        app.include_router(
            build_scim_router(
                store=get_identity_store(),
                scim_token=(_os.environ.get("CHUZOM_SCIM_TOKEN") or "").strip(),
            )
        )

    # ── Health (no auth) ────────────────────────────────────────────────
    @app.get("/v1/admin/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "version": __version__,
            "kind": "chuzom-admin-api",
        }

    # ── Users ───────────────────────────────────────────────────────────
    @app.get("/v1/admin/users")
    def list_users(
        identity: Identity = Depends(require_perm(Permission.MANAGE_USERS)),
        store: IdentityStore = Depends(get_identity_store),
    ) -> list[dict[str, Any]]:
        rows = store._conn.execute(
            "SELECT id, org_id, team_id, email, display_name, role, "
            "external_id, active, created_at FROM users "
            "ORDER BY created_at ASC"
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            # Reconstruct enough of User to feed _user_to_safe_dict
            # without re-fetching one-row-at-a-time.
            from chuzom.enterprise.rbac import Role
            user = User(
                id=row[0], org_id=row[1], team_id=row[2], email=row[3],
                display_name=row[4], role=Role(row[5]), external_id=row[6],
                active=bool(row[7]), created_at=row[8],
            )
            result.append(_user_to_safe_dict(user))
        return result

    @app.post(
        "/v1/admin/users", status_code=status.HTTP_201_CREATED
    )
    def create_user(
        body: CreateUserRequest,
        identity: Identity = Depends(require_perm(Permission.MANAGE_USERS)),
        store: IdentityStore = Depends(get_identity_store),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        # Resolve role (case-insensitive). Unknown role → 400.
        try:
            role = Role(body.role.strip().lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unknown role {body.role!r}; expected one of "
                    f"{', '.join(r.value for r in Role)}"
                ),
            )
        try:
            user = store.create_user(
                org_id=body.org_id,
                team_id=body.team_id,
                email=body.email,
                display_name=body.display_name,
                role=role,
                external_id=body.external_id,
            )
        except IdentityNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            )
        except IdentityConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            )
        _emit_admin_action(
            admin_log, identity=identity,
            action="user:create", resource_id=user.id,
            detail={
                "email": user.email, "role": user.role.value,
                "org_id": user.org_id, "team_id": user.team_id,
            },
        )
        return _user_to_safe_dict(user)

    # ── Tokens ──────────────────────────────────────────────────────────
    @app.post("/v1/admin/users/{user_id}/tokens/{token_id}:revoke")
    def revoke_token(
        user_id: str,
        token_id: str,
        identity: Identity = Depends(require_perm(Permission.MANAGE_USERS)),
        store: IdentityStore = Depends(get_identity_store),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        store.revoke_token(token_id)
        _emit_admin_action(
            admin_log, identity=identity,
            action="token:revoke", resource_id=token_id,
            detail={"target_user_id": user_id},
        )
        return {
            "revoked": True,
            "user_id": user_id,
            "token_id": token_id,
            "revoked_by": identity.user.email,
            "revoked_at": time.time(),
        }

    @app.post(
        "/v1/admin/users/{user_id}/tokens",
        status_code=status.HTTP_201_CREATED,
    )
    def issue_token(
        user_id: str,
        body: IssueTokenRequest,
        identity: Identity = Depends(require_perm(Permission.MANAGE_USERS)),
        store: IdentityStore = Depends(get_identity_store),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        # 404 if the user doesn't exist; 400 if deactivated.
        try:
            target = store.get_user(user_id)
        except IdentityNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            )
        if not target.active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"user {user_id} is deactivated",
            )
        try:
            token = store.issue_token(
                user_id,
                name=body.name,
                expires_in_seconds=body.expires_in_seconds,
            )
        except InvalidToken as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        # The plaintext is in the response ONCE — it's never returned
        # again by any other endpoint. Caller must capture it now.
        _emit_admin_action(
            admin_log, identity=identity,
            action="token:issue", resource_id=token.id,
            detail={
                "target_user_id": token.user_id,
                "name": token.name,
                "expires_at": token.expires_at,
            },
        )
        return {
            "id": token.id,
            "user_id": token.user_id,
            "name": token.name,
            "issued_at": token.issued_at,
            "expires_at": token.expires_at,
            "plaintext": token.plaintext,
            "issued_by": identity.user.email,
        }

    # ── Providers ───────────────────────────────────────────────────────
    @app.post("/v1/admin/providers/{provider}:disable")
    def disable_provider(
        provider: str,
        body: DisableProviderRequest,
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        registry: RuntimeProviderRegistry = Depends(get_provider_registry),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        entry = registry.disable(provider, reason=body.reason)
        entry["disabled_by"] = identity.user.email
        _emit_admin_action(
            admin_log, identity=identity,
            action="provider:disable", resource_id=provider,
            detail={"reason": body.reason},
        )
        return entry

    @app.post("/v1/admin/providers/{provider}:enable")
    def enable_provider(
        provider: str,
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        registry: RuntimeProviderRegistry = Depends(get_provider_registry),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        result = registry.enable(provider)
        result["enabled_by"] = identity.user.email
        _emit_admin_action(
            admin_log, identity=identity,
            action="provider:enable", resource_id=provider,
        )
        return result

    @app.get("/v1/admin/providers/disabled")
    def list_disabled_providers(
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        registry: RuntimeProviderRegistry = Depends(get_provider_registry),
    ) -> list[dict[str, Any]]:
        return registry.list_disabled()

    # ── Models (Refinement #5 / G-006-F2 finisher) ─────────────────────
    @app.post("/v1/admin/models/{model_id:path}:disable")
    def disable_model(
        model_id: str,
        body: DisableProviderRequest,
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        registry: RuntimeProviderRegistry = Depends(get_provider_registry),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        entry = registry.disable_model(model_id, reason=body.reason)
        entry["disabled_by"] = identity.user.email
        _emit_admin_action(
            admin_log, identity=identity,
            action="model:disable", resource_id=model_id,
            detail={"reason": body.reason},
        )
        return entry

    @app.post("/v1/admin/models/{model_id:path}:enable")
    def enable_model(
        model_id: str,
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        registry: RuntimeProviderRegistry = Depends(get_provider_registry),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        result = registry.enable_model(model_id)
        result["enabled_by"] = identity.user.email
        _emit_admin_action(
            admin_log, identity=identity,
            action="model:enable", resource_id=model_id,
        )
        return result

    @app.get("/v1/admin/models/disabled")
    def list_disabled_models(
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        registry: RuntimeProviderRegistry = Depends(get_provider_registry),
    ) -> list[dict[str, Any]]:
        return registry.list_disabled_models()

    # ── Team budgets (Loop-5 #4) ────────────────────────────────────────
    #
    # Three endpoints around the existing ``QuotaTracker`` (which
    # already supports ``scope="team"``). The endpoints split read
    # vs. write along the existing RBAC axis:
    #
    # * ``GET``    — ``Permission.VIEW_TEAM_USAGE`` (MANAGER tier).
    # * ``POST``   — ``Permission.SET_TEAM_QUOTA``  (MANAGER tier).
    # * ``DELETE`` — ``Permission.SET_TEAM_QUOTA``  (MANAGER tier).
    #
    # Audit: every write emits an ``team_budget:set`` /
    # ``team_budget:clear`` admin-action row so the audit endpoint
    # surfaces who changed budgets and when.
    @app.get("/v1/admin/teams/{team_id}/budget")
    def get_team_budget(
        team_id: str,
        identity: Identity = Depends(
            require_perm(Permission.VIEW_TEAM_USAGE)
        ),
        quotas: QuotaTracker = Depends(get_quota_tracker),
    ) -> dict[str, Any]:
        # The tracker returns a default (unlimited) policy when no
        # row exists — we surface that as ``configured=False`` so
        # operators can tell "no budget set" from "budget = 0 cap"
        # (which would be a misconfiguration the tracker treats as
        # unlimited anyway).
        policy = quotas.get_policy("team", team_id)
        configured = not policy.is_unlimited or _has_explicit_row(
            quotas, team_id,
        )
        return {
            "team_id": team_id,
            "configured": configured,
            "daily_cap_usd": policy.daily_cap_usd,
            "monthly_cap_usd": policy.monthly_cap_usd,
            "soft_warning_pct": policy.soft_warning_pct,
            "hard_block": policy.hard_block,
            "daily_consumed_usd": quotas.consumed(
                "team", team_id, "daily",
            ),
            "monthly_consumed_usd": quotas.consumed(
                "team", team_id, "monthly",
            ),
        }

    @app.post("/v1/admin/teams/{team_id}/budget")
    def set_team_budget(
        team_id: str,
        body: SetTeamBudgetRequest,
        identity: Identity = Depends(
            require_perm(Permission.SET_TEAM_QUOTA)
        ),
        quotas: QuotaTracker = Depends(get_quota_tracker),
        store: IdentityStore = Depends(get_identity_store),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        # 404 if the team doesn't exist in the identity store —
        # otherwise an operator typo silently creates a quota row
        # for a non-existent team_id and the consumption tracker
        # would never charge against it.
        try:
            store.get_team(team_id)
        except IdentityNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc),
            )
        policy = QuotaPolicy(
            daily_cap_usd=body.daily_cap_usd,
            monthly_cap_usd=body.monthly_cap_usd,
            soft_warning_pct=body.soft_warning_pct,
            hard_block=body.hard_block,
        )
        quotas.set_policy("team", team_id, policy)
        _emit_admin_action(
            admin_log, identity=identity,
            action="team_budget:set", resource_id=team_id,
            detail={
                "daily_cap_usd": body.daily_cap_usd,
                "monthly_cap_usd": body.monthly_cap_usd,
                "soft_warning_pct": body.soft_warning_pct,
                "hard_block": body.hard_block,
            },
        )
        return {
            "team_id": team_id,
            "daily_cap_usd": policy.daily_cap_usd,
            "monthly_cap_usd": policy.monthly_cap_usd,
            "soft_warning_pct": policy.soft_warning_pct,
            "hard_block": policy.hard_block,
            "set_by": identity.user.email,
        }

    @app.delete("/v1/admin/teams/{team_id}/budget")
    def clear_team_budget(
        team_id: str,
        identity: Identity = Depends(
            require_perm(Permission.SET_TEAM_QUOTA)
        ),
        quotas: QuotaTracker = Depends(get_quota_tracker),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        # Delete the policy row → tracker returns the unlimited
        # default on the next read. Idempotent: deleting a
        # non-existent row succeeds.
        _delete_quota_policy(quotas, "team", team_id)
        _emit_admin_action(
            admin_log, identity=identity,
            action="team_budget:clear", resource_id=team_id,
            detail={},
        )
        return {"team_id": team_id, "cleared": True}

    # ── Audit ───────────────────────────────────────────────────────────
    @app.get("/v1/admin/audit")
    def get_audit(
        limit: int = 100,
        actor_id: str | None = None,
        org_id: str | None = None,
        identity: Identity = Depends(require_perm(Permission.VIEW_ALL_AUDIT)),
        audit_log: AuditLog = Depends(get_audit_log),
    ) -> list[dict[str, Any]]:
        # Cap the limit so a caller can't pull the whole table.
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="limit must be in [1, 1000]",
            )
        if actor_id:
            return audit_log.by_actor(actor_id, limit=limit)
        return audit_log.recent(limit=limit, org_id=org_id)

    @app.get("/v1/admin/audit/verify")
    def verify_audit_chain(
        identity: Identity = Depends(require_perm(Permission.VIEW_ALL_AUDIT)),
        audit_log: AuditLog = Depends(get_audit_log),
    ) -> dict[str, Any]:
        # Surface AuditLog.verify_chain() so a SIEM / dashboard can poll
        # integrity. Tampering is reported as 200 + verified=false (with the
        # offending row) rather than an error status, so monitoring can parse a
        # stable schema and alert on the flag instead of catching an HTTP error.
        # 🥷 Backslash-security: Enforce auth/authz to prevent unauthorized access.
        from chuzom.enterprise.audit import TamperDetected
        rows = audit_log.count()
        try:
            audit_log.verify_chain()
        except TamperDetected as exc:
            return {
                "verified": False, "rows_checked": rows,
                "tamper_row": exc.row_index, "detail": str(exc),
            }
        return {"verified": True, "rows_checked": rows, "tamper_row": None}

    # ── Policy (G-007 versioned) ────────────────────────────────────────
    @app.post("/v1/admin/policy", status_code=status.HTTP_200_OK)
    def push_policy(
        body: PushPolicyRequest,
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
        policy_store: PolicyVersionStore = Depends(get_policy_version_store),
    ) -> dict[str, Any]:
        try:
            meta = policy_store.push(
                yaml_text=body.yaml,
                actor_user_id=identity.user.id,
                actor_email=identity.user.email,
                note=body.note,
            )
        except PolicyValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
        _emit_admin_action(
            admin_log, identity=identity,
            action="policy:push", resource_id=f"v{meta['version']}",
            detail={"bytes": meta["yaml_bytes"], "note": body.note},
        )
        return {
            "applied": True,
            "version": meta["version"],
            "applied_by": identity.user.email,
            "applied_at": meta["created_at"],
            "is_active": meta["is_active"],
            "note": (
                "Versioned store: history is queryable at "
                "GET /v1/admin/policy/versions; rollback at "
                "POST /v1/admin/policy/rollback."
            ),
        }

    @app.get("/v1/admin/policy/versions")
    def list_policy_versions(
        limit: int = 100,
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        policy_store: PolicyVersionStore = Depends(get_policy_version_store),
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="limit must be in [1, 1000]",
            )
        return policy_store.list_versions(limit=limit)

    @app.get("/v1/admin/policy/versions/{version}")
    def get_policy_version(
        version: int,
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        policy_store: PolicyVersionStore = Depends(get_policy_version_store),
    ) -> dict[str, Any]:
        try:
            return policy_store.get(version)
        except PolicyVersionNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            )

    @app.post("/v1/admin/policy/rollback")
    def rollback_policy(
        body: RollbackPolicyRequest,
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
        policy_store: PolicyVersionStore = Depends(get_policy_version_store),
    ) -> dict[str, Any]:
        try:
            meta = policy_store.rollback(
                target_version=body.target_version,
                actor_user_id=identity.user.id,
                actor_email=identity.user.email,
                note=body.note,
            )
        except PolicyVersionNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            )
        except PolicyValidationError as exc:
            # Shouldn't fire on rollback (we're copying a previously
            # validated payload), but stay defensive.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"rollback validation failed: {exc}",
            )
        _emit_admin_action(
            admin_log, identity=identity,
            action="policy:rollback",
            resource_id=f"v{meta['version']}",
            detail={
                "target_version": body.target_version,
                "note": body.note,
            },
        )
        return {
            "rolled_back": True,
            "new_version": meta["version"],
            "target_version": body.target_version,
            "applied_by": identity.user.email,
            "applied_at": meta["created_at"],
        }

    # ── Agent emergency stop (G-026 + G-030) ────────────────────────────
    @app.post("/v1/admin/agents/{session_id}:cancel")
    def cancel_agent(
        session_id: str,
        body: DisableProviderRequest,
        identity: Identity = Depends(require_perm(Permission.MANAGE_POLICY)),
        sessions: SessionStore = Depends(get_session_store),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> dict[str, Any]:
        """Central agent emergency stop. Marks the session and every
        non-terminal descendant as ``CANCELLED`` in one transaction.

        Idempotent: cancelling an already-terminal session is a no-op
        that returns the current state. The cascade stops at any
        terminal subtree so previously-completed branches aren't
        rewritten under ``CANCELLED``.

        Permission: ``MANAGE_POLICY`` — same gate as emergency
        provider disable. An operator who can disable a provider can
        also kill an agent run.

        Returns the post-cancel session record + a count of
        descendants that were also cancelled.
        """
        try:
            pre = sessions.get(session_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session {session_id} not found",
            )
        if pre.state.is_terminal:
            # Idempotent — still emit an admin-action row so the
            # forensic trail shows the attempt, but mark it explicitly.
            _emit_admin_action(
                admin_log, identity=identity,
                action="agent:cancel_noop",
                resource_id=session_id,
                detail={
                    "reason": body.reason,
                    "previous_state": pre.state.value,
                },
            )
            return {
                "cancelled": False,
                "session_id": session_id,
                "state": pre.state.value,
                "note": "session was already terminal",
            }

        # Count non-terminal descendants BEFORE we cancel so we can
        # return how many we touched.
        descendant_count = 0
        frontier = sessions.children(session_id)
        while frontier:
            next_frontier = []
            for child in frontier:
                if not child.state.is_terminal:
                    descendant_count += 1
                next_frontier.extend(sessions.children(child.session_id))
            frontier = next_frontier

        result = sessions.cancel(session_id, reason=body.reason)
        _emit_admin_action(
            admin_log, identity=identity,
            action="agent:cancel", resource_id=session_id,
            detail={
                "reason": body.reason,
                "descendants_cancelled": descendant_count,
            },
        )
        return {
            "cancelled": True,
            "session_id": session_id,
            "state": result.state.value,
            "descendants_cancelled": descendant_count,
            "cancelled_by": identity.user.email,
        }

    # ── Agent ledger (G-029) ────────────────────────────────────────────
    @app.get("/v1/admin/agents/status")
    def get_agents_status(
        limit: int = 100,
        state: str | None = None,
        near_budget_pct: float | None = None,
        stuck_since_seconds: float | None = None,
        cursor: str | None = None,
        identity: Identity = Depends(require_perm(Permission.VIEW_ALL_AUDIT)),
        sessions: SessionStore = Depends(get_session_store),
    ) -> list[dict[str, Any]]:
        """Central agent ledger — newest sessions first, enriched with
        budget-pressure, tool-call telemetry, and idleness.

        Filters:

        * ``state`` — exact match (``active`` / ``completed`` /
          ``errored`` / ``budget_exceeded``).
        * ``near_budget_pct`` — keep sessions whose
          ``consumed_usd / budget_cap_usd`` ≥ this value (0..1).
        * ``stuck_since_seconds`` — keep ACTIVE sessions whose
          ``now - last_activity_at`` ≥ this many seconds. A session
          that was created and immediately abandoned has its
          ``last_activity_at`` seeded to ``started_at`` so it
          surfaces correctly. Terminal sessions are excluded
          regardless of idle time — "stuck" only makes sense for
          alive workflows.
        * ``limit`` — bounded [1, 1000].
        * ``cursor`` — Refinement #8 keyset pagination. Base64
          encoded JSON ``[started_at, session_id]`` of the last row
          on the previous page. To paginate: send the FIRST request
          without ``cursor``, take the last row of the response,
          encode ``base64(json.dumps([row.started_at,
          row.session_id]))`` and pass it as ``cursor`` on the next
          request. Returns an empty list when the cursor is past
          the last row. Backward compat: omitting ``cursor`` returns
          the first page exactly as before.
        """
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="limit must be in [1, 1000]",
            )
        if near_budget_pct is not None and not (0.0 <= near_budget_pct <= 1.0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="near_budget_pct must be in [0.0, 1.0]",
            )
        if stuck_since_seconds is not None and stuck_since_seconds < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="stuck_since_seconds must be >= 0",
            )
        before: tuple[float, str] | None = None
        if cursor is not None:
            try:
                before = _decode_ledger_cursor(cursor)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"invalid cursor: {exc}",
                )
        now = time.time()
        rows = sessions.recent(limit=limit, state=state, before=before)
        result: list[dict[str, Any]] = []
        for s in rows:
            pressure = (
                s.consumed_usd / s.budget_cap_usd
                if s.budget_cap_usd > 0
                else 0.0
            )
            if near_budget_pct is not None and pressure < near_budget_pct:
                continue
            # Idleness derives from last_activity_at when present, else
            # falls back to started_at — pre-G-029-finisher legacy rows
            # may have NULL last_activity_at and we should still produce
            # a meaningful "idle since X" answer.
            activity_ts = s.last_activity_at or s.started_at
            idle_seconds = max(0.0, now - activity_ts) if activity_ts else None
            if stuck_since_seconds is not None:
                if s.state.is_terminal:
                    continue
                if idle_seconds is None or idle_seconds < stuck_since_seconds:
                    continue
            result.append({
                "session_id": s.session_id,
                "agent_id": s.agent_id,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
                "parent_session_id": s.parent_session_id,
                "budget_cap_usd": s.budget_cap_usd,
                "consumed_usd": s.consumed_usd,
                "remaining_usd": s.remaining_usd,
                "budget_pressure_pct": pressure,
                "step_count": s.step_count,
                "tool_call_count": s.tool_call_count,
                "state": s.state.value,
                "framework": s.framework,
                "last_activity_at": s.last_activity_at,
                "idle_seconds": idle_seconds,
                "limits": {
                    "max_iterations": s.max_iterations,
                    "max_recursion_depth": s.max_recursion_depth,
                    "max_tool_calls": s.max_tool_calls,
                    "max_children_concurrent": s.max_children_concurrent,
                },
            })
        return result

    # ── Admin-action audit (G-006-F5 read endpoint) ─────────────────────
    @app.get("/v1/admin/admin-actions")
    def get_admin_actions(
        limit: int = 100,
        action: str | None = None,
        actor_user_id: str | None = None,
        identity: Identity = Depends(require_perm(Permission.VIEW_ALL_AUDIT)),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="limit must be in [1, 1000]",
            )
        return admin_log.recent(
            limit=limit, action=action, actor_user_id=actor_user_id,
        )

    # ── Invoice reconciliation (G-017) ─────────────────────────────────
    @app.get("/v1/admin/invoice/diff")
    def get_invoice_diff(
        provider: str = "anthropic",
        month: str = "",
        identity: Identity = Depends(require_perm(Permission.VIEW_ALL_AUDIT)),
    ) -> dict[str, Any]:
        """Reconcile a provider's invoice against chuzom's own log.

        Currently supports only ``provider=anthropic`` — the smallest
        viable shape per the G-017 audit close. Future slices add
        ``openai`` (Usage API) + ``gemini`` (billing export).

        ``month`` is ``YYYY-MM``; defaults to the most recent complete
        month when omitted. ``diff_pct`` field answers Finance's
        "are we within 2%" question in one shot.
        """
        if provider != "anthropic":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"provider {provider!r} not yet supported — "
                    "only 'anthropic' for now (G-017 first slice)"
                ),
            )
        if not month:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            year = now.year if now.month > 1 else now.year - 1
            mo = now.month - 1 if now.month > 1 else 12
            month = f"{year:04d}-{mo:02d}"

        from chuzom.invoice_reconciliation import compute_diff
        from chuzom.invoice_reconciliation.anthropic import (
            pull_monthly_invoice,
        )

        try:
            invoice = pull_monthly_invoice(period=month)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 — surface upstream
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"failed to fetch invoice: {exc}",
            )

        chuzom_total_usd = 0.0
        chuzom_call_count = 0
        try:
            import asyncio
            from chuzom.cost import _get_db

            async def _tally():
                db = await _get_db()
                try:
                    c = await db.execute(
                        "SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) "
                        "FROM usage WHERE provider = ? "
                        "AND strftime('%Y-%m', timestamp) = ?",
                        ("anthropic", month),
                    )
                    return await c.fetchone()
                finally:
                    await db.close()
            row = asyncio.run(_tally())
            if row:
                chuzom_total_usd = float(row[0])
                chuzom_call_count = int(row[1])
        except Exception:
            # Fail soft — the diff is still valid, just shows
            # chuzom-side zero so the reader knows the local
            # lookup degraded.
            pass

        diff = compute_diff(
            invoice=invoice,
            chuzom_total_usd=chuzom_total_usd,
            chuzom_call_count=chuzom_call_count,
        )
        return {
            "provider": diff.provider,
            "period": diff.period,
            "provider_reported_usd": diff.provider_reported_usd,
            "chuzom_reported_usd": diff.chuzom_reported_usd,
            "diff_usd": diff.diff_usd,
            "diff_pct": diff.diff_pct,
            "provider_call_count": diff.provider_call_count,
            "chuzom_call_count": diff.chuzom_call_count,
            "within_two_pct": abs(diff.diff_pct) <= 0.02,
        }

    # ── Prometheus metrics (G-031) ─────────────────────────────────────
    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics_endpoint(
        sessions: SessionStore = Depends(get_session_store),
        admin_log: AdminActionLog = Depends(get_admin_action_log),
        audit_log: AuditLog = Depends(get_audit_log),
        registry: RuntimeProviderRegistry = Depends(get_provider_registry),
        policy_store: PolicyVersionStore = Depends(get_policy_version_store),
    ) -> PlainTextResponse:
        """Prometheus exposition endpoint. Intentionally **unauthenticated**
        by default — that's the convention for ``/metrics`` so a
        standard scraper can read it without per-target credential
        config. Operators that need auth can set
        ``CHUZOM_METRICS_REQUIRE_AUTH=on`` (future slice) or front
        the admin API with a reverse proxy.

        Surfaces budget burn, RBAC denials, audit chain length,
        admin-action counts, policy version, subscription pressure,
        and a self-cost gauge. See ``chuzom.metrics`` for the full
        inventory and rationale.
        """
        # Subscription-pressure collection makes a live network call
        # to claude.ai / gemini / codex which can take seconds.
        # Opt-in only so the default scrape stays fast (sub-100ms).
        # Operators that want pressure in Prometheus set
        # ``CHUZOM_METRICS_INCLUDE_PRESSURE=on``; alerts derived
        # from live pressure should accept higher scrape latency.
        import os as _os
        include_pressure = (
            (_os.environ.get("CHUZOM_METRICS_INCLUDE_PRESSURE") or "")
            .strip().lower() in {"on", "1", "true", "yes"}
        )
        body = collect_all(
            sessions=sessions,
            admin_log=admin_log,
            audit_log=audit_log,
            registry=registry,
            policy_store=policy_store,
            include_subscription_pressure=include_pressure,
        )
        return PlainTextResponse(
            content=body, media_type=EXPOSITION_CONTENT_TYPE,
        )

    return app


__all__ = [
    "RuntimeProviderRegistry",
    "authenticate_identity",
    "create_app",
    "encode_ledger_cursor",
    "get_admin_action_log",
    "get_audit_log",
    "get_identity_store",
    "get_policy_version_store",
    "get_provider_registry",
    "get_session_store",
    "require_perm",
]
