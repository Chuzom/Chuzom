"""SCIM 2.0 provisioning endpoint (FastAPI).

Lets an IdP create / read / update / deactivate chuzom users so deprovisioning
actually revokes access. Mountable into the admin API or run standalone via
:func:`create_scim_app`.

Auth: a single bearer secret (``CHUZOM_SCIM_TOKEN``) compared in constant time.
Enabled only when ``CHUZOM_SCIM_ENABLED`` is affirmative AND a token is set.

🥷 Backslash-Security: using vibe-coding rules for secured Authentication & Authorization
"""
from __future__ import annotations

import hmac
import os

import structlog
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response

from chuzom.enterprise import scim
from chuzom.enterprise.identity import (
    IdentityConflict,
    IdentityNotFound,
    IdentityStore,
)
from chuzom.enterprise.rbac import Role

log = structlog.get_logger(__name__)

_DEFAULT_ORG = (os.environ.get("CHUZOM_OIDC_DEFAULT_ORG") or "default").strip() or "default"
_DEFAULT_TEAM = (os.environ.get("CHUZOM_OIDC_DEFAULT_TEAM") or "default").strip() or "default"


def scim_enabled() -> bool:
    """True when SCIM is switched on and a provisioning secret is configured."""
    flag = (os.environ.get("CHUZOM_SCIM_ENABLED") or "").strip().lower()
    token = (os.environ.get("CHUZOM_SCIM_TOKEN") or "").strip()
    return flag in {"on", "1", "true", "yes"} and bool(token)


def _require_scim_auth(expected_token: str):
    """Build a FastAPI dependency enforcing the SCIM bearer secret."""

    async def _dep(authorization: str = Header(default="")) -> None:
        parts = authorization.strip().split(None, 1)
        presented = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else ""
        # Constant-time compare — never branch on a prefix of the secret.
        if not presented or not hmac.compare_digest(presented, expected_token):
            log.warning("scim_auth_failed")
            raise HTTPException(status_code=401, detail="unauthorized")

    return _dep


def create_scim_app(
    *,
    store: IdentityStore | None = None,
    scim_token: str | None = None,
) -> FastAPI:
    """Build a standalone SCIM FastAPI app.

    Tests inject ``store`` (tmp DB) and ``scim_token``. In production both come
    from the process IdentityStore and ``CHUZOM_SCIM_TOKEN``.
    """
    store = store or IdentityStore(check_same_thread=False)
    scim_token = scim_token or (os.environ.get("CHUZOM_SCIM_TOKEN") or "").strip()
    if not scim_token:
        raise RuntimeError("CHUZOM_SCIM_TOKEN must be set to enable SCIM")

    app = FastAPI(title="chuzom SCIM 2.0", docs_url=None, redoc_url=None)
    router = APIRouter(prefix="/scim/v2", dependencies=[Depends(_require_scim_auth(scim_token))])

    def _default_org_team() -> tuple[str, str]:
        org = store.get_or_create_org(_DEFAULT_ORG)
        team = store.get_or_create_team(org.id, _DEFAULT_TEAM)
        return org.id, team.id

    @router.post("/Users", status_code=201)
    async def create_user(request: Request) -> Response:
        body = await request.json()
        fields = scim.extract_user_fields(body)
        if not fields["email"]:
            raise HTTPException(status_code=400, detail="userName/email is required")
        org_id, team_id = _default_org_team()
        try:
            user = store.get_or_create_by_external_id(
                external_id=fields["external_id"] or fields["email"],
                email=fields["email"],
                display_name=fields["display_name"],
                role=Role.EMPLOYEE,
                org_id=org_id,
                team_id=team_id,
            )
        except IdentityConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        log.info("scim_user_provisioned", user_id=user.id)
        return _json(scim.user_to_scim(user), status_code=201)

    @router.get("/Users/{user_id}")
    async def get_user(user_id: str) -> Response:
        try:
            user = store.get_user(user_id)
        except IdentityNotFound:
            raise HTTPException(status_code=404, detail="user not found")
        return _json(scim.user_to_scim(user))

    @router.get("/Users")
    async def list_users(filter: str | None = None) -> Response:  # noqa: A002 (SCIM param name)
        users = []
        # Minimal filter support: userName eq "x" (the common provisioning probe).
        if filter and "userName" in filter and " eq " in filter:
            value = filter.split(" eq ", 1)[1].strip().strip('"')
            try:
                users = [store.get_user_by_email(value)]
            except IdentityNotFound:
                users = []
        return _json(scim.list_response(users))

    @router.patch("/Users/{user_id}")
    async def patch_user(user_id: str, request: Request) -> Response:
        try:
            user = store.get_user(user_id)
        except IdentityNotFound:
            raise HTTPException(status_code=404, detail="user not found")
        body = await request.json()
        if scim.patch_sets_inactive(body):
            # Deprovision: deactivate AND revoke tokens so access stops now.
            store.deactivate_user(user.id)
            store.revoke_user_tokens(user.id)
            log.info("scim_user_deprovisioned", user_id=user.id)
            user = store.get_user(user.id)
        return _json(scim.user_to_scim(user))

    @router.delete("/Users/{user_id}", status_code=204)
    async def delete_user(user_id: str) -> Response:
        try:
            store.get_user(user_id)
        except IdentityNotFound:
            raise HTTPException(status_code=404, detail="user not found")
        # Soft delete: deactivate + revoke. We never hard-delete audit subjects.
        store.deactivate_user(user_id)
        store.revoke_user_tokens(user_id)
        log.info("scim_user_deleted", user_id=user_id)
        return Response(status_code=204)

    app.include_router(router)
    return app


def _json(payload: dict, *, status_code: int = 200) -> Response:
    import json

    return Response(
        content=json.dumps(payload),
        media_type="application/scim+json",
        status_code=status_code,
    )
