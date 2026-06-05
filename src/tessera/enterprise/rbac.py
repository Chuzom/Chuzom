"""Role-based access control — roles, permissions, checks.

Four built-in roles map to permission bundles:

    ADMIN            — full org control (configure policy, view all
                       audit, manage users + tokens)
    MANAGER          — team-scoped (set team quotas, view team audit,
                       issue tokens to team members)
    EMPLOYEE         — route prompts, view own audit, see own usage
    SERVICE_ACCOUNT  — programmatic use; same as employee but no UI
                       privileges and tokens that don't expire by
                       default

Permissions are the atomic units checked by `has_permission(identity,
Permission.X)`. Custom roles can be supported by passing explicit
permissions to IdentityStore.issue_token() rather than relying on the
role's defaults — useful for principle-of-least-privilege carve-outs.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class Role(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"
    SERVICE_ACCOUNT = "service_account"


class Permission(str, Enum):
    # Routing
    ROUTE_PROMPT = "route_prompt"

    # Self
    VIEW_OWN_USAGE = "view_own_usage"
    VIEW_OWN_AUDIT = "view_own_audit"

    # Team
    VIEW_TEAM_USAGE = "view_team_usage"
    VIEW_TEAM_AUDIT = "view_team_audit"
    SET_TEAM_QUOTA = "set_team_quota"
    ISSUE_TEAM_TOKEN = "issue_team_token"

    # Org-wide
    VIEW_ALL_AUDIT = "view_all_audit"
    MANAGE_USERS = "manage_users"
    MANAGE_POLICY = "manage_policy"
    MANAGE_REDACTION = "manage_redaction"
    EXPORT_AUDIT = "export_audit"


# Default permission bundle per role. Keep these minimal — extra rights
# are easier to add than to revoke.
_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset({
        Permission.ROUTE_PROMPT,
        Permission.VIEW_OWN_USAGE,
        Permission.VIEW_OWN_AUDIT,
        Permission.VIEW_TEAM_USAGE,
        Permission.VIEW_TEAM_AUDIT,
        Permission.SET_TEAM_QUOTA,
        Permission.ISSUE_TEAM_TOKEN,
        Permission.VIEW_ALL_AUDIT,
        Permission.MANAGE_USERS,
        Permission.MANAGE_POLICY,
        Permission.MANAGE_REDACTION,
        Permission.EXPORT_AUDIT,
    }),
    Role.MANAGER: frozenset({
        Permission.ROUTE_PROMPT,
        Permission.VIEW_OWN_USAGE,
        Permission.VIEW_OWN_AUDIT,
        Permission.VIEW_TEAM_USAGE,
        Permission.VIEW_TEAM_AUDIT,
        Permission.SET_TEAM_QUOTA,
        Permission.ISSUE_TEAM_TOKEN,
    }),
    Role.EMPLOYEE: frozenset({
        Permission.ROUTE_PROMPT,
        Permission.VIEW_OWN_USAGE,
        Permission.VIEW_OWN_AUDIT,
    }),
    Role.SERVICE_ACCOUNT: frozenset({
        Permission.ROUTE_PROMPT,
        Permission.VIEW_OWN_USAGE,
    }),
}


def permissions_for_role(role: Role) -> frozenset[Permission]:
    """Return the default permission bundle for a role."""
    return _ROLE_PERMISSIONS[role]


def has_permission(identity: Any, permission: Permission) -> bool:
    """True iff the identity's token grants the requested permission.

    `identity` should be an Identity instance (or any object with a
    `permissions` attribute that's iterable of Permission). Failing the
    check should propagate to the caller as a structured error — the
    routing layer should NOT silently swallow auth failures.
    """
    perms = getattr(identity, "permissions", None)
    if perms is None:
        return False
    return permission in perms


class PermissionDenied(PermissionError):
    """Raised by guarded code paths when an identity lacks a permission."""

    def __init__(self, identity: Any, permission: Permission):
        self.identity = identity
        self.permission = permission
        user_email = getattr(getattr(identity, "user", None), "email", "?")
        super().__init__(
            f"User {user_email!r} lacks permission {permission.value!r}"
        )


def require_permission(identity: Any, permission: Permission) -> None:
    """Raise PermissionDenied if the identity doesn't have the permission."""
    if not has_permission(identity, permission):
        raise PermissionDenied(identity, permission)
