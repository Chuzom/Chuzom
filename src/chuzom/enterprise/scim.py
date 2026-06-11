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


def parse_role_map(raw: str) -> dict:
    """Parse ``"manager-grp=manager,Admin=admin"`` → {attr_value: Role}.

    Mirrors :func:`chuzom.enterprise.oidc._parse_role_map` so SCIM and OIDC
    share one configuration idiom. Unknown role names are skipped (logged by
    callers if desired) rather than crashing config. Matching is exact and
    case-sensitive on the attribute value; role names are case-insensitive.
    """
    from chuzom.enterprise.rbac import Role

    mapping: dict = {}
    for pair in (raw or "").split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        attr_value, _, role_name = pair.partition("=")
        attr_value = attr_value.strip()
        try:
            mapping[attr_value] = Role(role_name.strip().lower())
        except ValueError:
            continue
    return mapping


def extract_role(payload: dict, role_map: dict):
    """Map a SCIM User's ``roles``/``title`` attribute to a chuzom ``Role``.

    SCIM 2.0 carries authorization signals in the multi-valued ``roles``
    attribute (``[{"value": "...", "primary": true}]``) and the singular
    ``title``. We try each candidate value against ``role_map`` (primary role
    first, then other roles, then title) and fall back to EMPLOYEE — so an IdP
    that doesn't send a mapped attribute provisions a least-privilege user
    rather than failing, while a configured map promotes managers/admins.
    """
    from chuzom.enterprise.rbac import Role

    candidates: list[str] = []
    roles = payload.get("roles") or []
    if isinstance(roles, list):
        primary = [r for r in roles if isinstance(r, dict) and r.get("primary")]
        rest = [r for r in roles if r not in primary]
        for r in (*primary, *rest):
            if isinstance(r, dict) and r.get("value"):
                candidates.append(str(r["value"]).strip())
            elif isinstance(r, str) and r.strip():
                candidates.append(r.strip())
    title = (payload.get("title") or "").strip()
    if title:
        candidates.append(title)
    for value in candidates:
        if value in role_map:
            return role_map[value]
    return Role.EMPLOYEE


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
