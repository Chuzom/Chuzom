"""Enterprise features — identity, RBAC, audit, redaction, quotas.

This subpackage adds the controls organizations need to deploy Chuzom
as a shared LLM router across employees:

    identity   - User/Team/Org model + API token issuance + revocation
    rbac       - Role-based access control (admin/manager/employee/service)
    audit      - Immutable hash-chained audit log; CEF + JSON export
    redaction  - Prompt PII scrubbing before logging
    quotas     - Per-user/team daily + monthly spend caps

Designed so a small org can adopt any subset incrementally.
"""
from chuzom.enterprise.audit import AuditEvent, AuditLog
from chuzom.enterprise.identity import (
    APIToken, Identity, IdentityStore, Org, Team, User,
)
from chuzom.enterprise.quotas import QuotaExceeded, QuotaPolicy, QuotaTracker
from chuzom.enterprise.rbac import Permission, Role, has_permission
from chuzom.enterprise.redaction import RedactionPolicy, redact_prompt

__all__ = [
    "APIToken", "Identity", "IdentityStore", "Org", "Team", "User",
    "Permission", "Role", "has_permission",
    "AuditEvent", "AuditLog",
    "RedactionPolicy", "redact_prompt",
    "QuotaExceeded", "QuotaPolicy", "QuotaTracker",
]
