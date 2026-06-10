"""SCIM 2.0 ⇄ IdentityStore mapping.

Pure serialization + field-extraction helpers shared by the SCIM HTTP router
(:mod:`chuzom.scim_api`). Kept separate from transport so it unit-tests without
a web server.

Supported resource: User (RFC 7643 core schema, the subset IdPs actually send).
Group → Team mapping is intentionally deferred to a later slice.
"""
from __future__ import annotations

from datetime import datetime, timezone

from chuzom.enterprise.identity import User

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


def user_to_scim(user: User) -> dict:
    """Serialize a chuzom :class:`User` as a SCIM User resource."""
    created = datetime.fromtimestamp(user.created_at, tz=timezone.utc).isoformat()
    return {
        "schemas": [USER_SCHEMA],
        "id": user.id,
        "externalId": user.external_id or None,
        "userName": user.email,
        "name": {"formatted": user.display_name},
        "displayName": user.display_name,
        "emails": [{"value": user.email, "primary": True}],
        "active": user.active,
        "meta": {
            "resourceType": "User",
            "created": created,
            "location": f"/scim/v2/Users/{user.id}",
        },
    }


def list_response(users: list[User], *, start_index: int = 1) -> dict:
    """Wrap users in a SCIM ListResponse envelope."""
    resources = [user_to_scim(u) for u in users]
    return {
        "schemas": [LIST_SCHEMA],
        "totalResults": len(resources),
        "startIndex": start_index,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


def error_response(detail: str, status: int) -> dict:
    """SCIM error envelope."""
    return {"schemas": [ERROR_SCHEMA], "detail": detail, "status": str(status)}


def extract_user_fields(payload: dict) -> dict:
    """Pull (email, display_name, external_id, active) from a SCIM User body.

    Resolves email from ``userName`` first, then the primary/first ``emails``
    entry. Returns a dict with whatever was present; callers validate required
    fields. Raises ValueError when no email can be determined on create.
    """
    email = (payload.get("userName") or "").strip()
    emails = payload.get("emails") or []
    if not email and isinstance(emails, list) and emails:
        primary = next(
            (e for e in emails if isinstance(e, dict) and e.get("primary")),
            emails[0] if isinstance(emails[0], dict) else None,
        )
        if primary:
            email = str(primary.get("value") or "").strip()

    name = payload.get("name") or {}
    display_name = (
        (payload.get("displayName") or "").strip()
        or (name.get("formatted") if isinstance(name, dict) else "")
        or email
    )
    external_id = (payload.get("externalId") or "").strip()
    active = payload.get("active", True)

    return {
        "email": email,
        "display_name": display_name,
        "external_id": external_id,
        "active": bool(active),
    }


def patch_sets_inactive(payload: dict) -> bool:
    """True iff a SCIM PatchOp body replaces ``active`` with a falsey value.

    Handles both the path form ``{"op":"replace","path":"active","value":false}``
    and the value-object form ``{"op":"replace","value":{"active":false}}``.
    """
    for op in payload.get("Operations", []) or []:
        if not isinstance(op, dict):
            continue
        if (op.get("op") or "").lower() != "replace":
            continue
        path = (op.get("path") or "").strip().lower()
        value = op.get("value")
        if path == "active" and _is_false(value):
            return True
        if isinstance(value, dict) and "active" in value and _is_false(value["active"]):
            return True
    return False


def _is_false(value: object) -> bool:
    if isinstance(value, bool):
        return value is False
    if isinstance(value, str):
        return value.strip().lower() in {"false", "0", "no"}
    return value == 0
