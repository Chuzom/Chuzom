"""Enterprise package — identity / RBAC / audit / redaction / quotas."""
from __future__ import annotations

from pathlib import Path

import pytest

from tessera.enterprise.audit import (
    AuditEvent,
    AuditEventType,
    AuditLog,
    TamperDetected,
)
from tessera.enterprise.identity import (
    IdentityConflict,
    IdentityNotFound,
    IdentityStore,
    InvalidToken,
)
from tessera.enterprise.quotas import (
    QuotaExceeded,
    QuotaPolicy,
    QuotaTracker,
)
from tessera.enterprise.rbac import (
    Permission,
    PermissionDenied,
    Role,
    has_permission,
    permissions_for_role,
    require_permission,
)
from tessera.enterprise.redaction import (
    RedactionPolicy,
    redact_prompt,
)


# ════════════════════════════════════════════════════════════════════════
# Identity + RBAC
# ════════════════════════════════════════════════════════════════════════

@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(db_path=tmp_path / "id.db")


def test_create_org_team_user_chain(store: IdentityStore):
    org = store.create_org(name="Acme")
    team = store.create_team(org_id=org.id, name="engineering",
                              monthly_budget_usd=500.0)
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="alice@acme.com", display_name="Alice",
        role=Role.EMPLOYEE,
    )
    assert user.role == Role.EMPLOYEE
    assert store.get_user_by_email("alice@acme.com").id == user.id


def test_org_name_uniqueness_enforced(store: IdentityStore):
    store.create_org(name="Acme")
    with pytest.raises(IdentityConflict):
        store.create_org(name="Acme")


def test_user_email_uniqueness_enforced(store: IdentityStore):
    org = store.create_org(name="Acme")
    team = store.create_team(org_id=org.id, name="eng")
    store.create_user(org_id=org.id, team_id=team.id,
                      email="dup@acme.com", display_name="A",
                      role=Role.EMPLOYEE)
    with pytest.raises(IdentityConflict):
        store.create_user(org_id=org.id, team_id=team.id,
                          email="dup@acme.com", display_name="B",
                          role=Role.EMPLOYEE)


def test_create_team_validates_org_exists(store: IdentityStore):
    with pytest.raises(IdentityNotFound):
        store.create_team(org_id="nonexistent", name="ghost")


def test_create_user_validates_team_exists(store: IdentityStore):
    org = store.create_org(name="Acme")
    with pytest.raises(IdentityNotFound):
        store.create_user(org_id=org.id, team_id="nonexistent",
                          email="a@acme.com", display_name="A",
                          role=Role.EMPLOYEE)


# ── Tokens ────────────────────────────────────────────────────────────

def test_issue_token_returns_plaintext_once(store: IdentityStore):
    org = store.create_org(name="Acme")
    team = store.create_team(org_id=org.id, name="eng")
    user = store.create_user(org_id=org.id, team_id=team.id,
                              email="a@acme.com", display_name="A",
                              role=Role.EMPLOYEE)
    token = store.issue_token(user.id, name="laptop")
    assert token.plaintext is not None
    assert token.plaintext.startswith("tsr_")
    assert len(token.plaintext) > 20  # high entropy
    # Hash is what's persisted; plaintext is NEVER retrievable from store
    assert token.hash_hex
    assert token.hash_hex != token.plaintext


def test_authenticate_validates_token(store: IdentityStore):
    org = store.create_org(name="Acme")
    team = store.create_team(org_id=org.id, name="eng")
    user = store.create_user(org_id=org.id, team_id=team.id,
                              email="a@acme.com", display_name="A",
                              role=Role.EMPLOYEE)
    token = store.issue_token(user.id, name="laptop")
    identity = store.authenticate(token.plaintext)
    assert identity.user.id == user.id
    assert Permission.ROUTE_PROMPT in identity.permissions


def test_authenticate_unknown_token_raises(store: IdentityStore):
    with pytest.raises(InvalidToken, match="unknown"):
        store.authenticate("tsr_completely-fake-token-doesnotexist")


def test_authenticate_malformed_prefix_raises(store: IdentityStore):
    with pytest.raises(InvalidToken, match="tsr_"):
        store.authenticate("bearer-without-prefix-12345")


def test_revoked_token_rejected(store: IdentityStore):
    org = store.create_org(name="Acme")
    team = store.create_team(org_id=org.id, name="eng")
    user = store.create_user(org_id=org.id, team_id=team.id,
                              email="a@acme.com", display_name="A",
                              role=Role.EMPLOYEE)
    token = store.issue_token(user.id, name="laptop")
    store.revoke_token(token.id)
    with pytest.raises(InvalidToken, match="revoked"):
        store.authenticate(token.plaintext)


def test_revoke_user_tokens_revokes_all(store: IdentityStore):
    org = store.create_org(name="Acme")
    team = store.create_team(org_id=org.id, name="eng")
    user = store.create_user(org_id=org.id, team_id=team.id,
                              email="a@acme.com", display_name="A",
                              role=Role.EMPLOYEE)
    t1 = store.issue_token(user.id, name="laptop")
    t2 = store.issue_token(user.id, name="phone")
    count = store.revoke_user_tokens(user.id)
    assert count == 2
    with pytest.raises(InvalidToken):
        store.authenticate(t1.plaintext)
    with pytest.raises(InvalidToken):
        store.authenticate(t2.plaintext)


def test_deactivated_user_token_rejected(store: IdentityStore):
    org = store.create_org(name="Acme")
    team = store.create_team(org_id=org.id, name="eng")
    user = store.create_user(org_id=org.id, team_id=team.id,
                              email="a@acme.com", display_name="A",
                              role=Role.EMPLOYEE)
    token = store.issue_token(user.id, name="laptop")
    store.deactivate_user(user.id)
    with pytest.raises(InvalidToken, match="deactivated"):
        store.authenticate(token.plaintext)


def test_token_for_deactivated_user_not_issuable(store: IdentityStore):
    org = store.create_org(name="Acme")
    team = store.create_team(org_id=org.id, name="eng")
    user = store.create_user(org_id=org.id, team_id=team.id,
                              email="a@acme.com", display_name="A",
                              role=Role.EMPLOYEE)
    store.deactivate_user(user.id)
    with pytest.raises(InvalidToken, match="deactivated"):
        store.issue_token(user.id, name="laptop")


# ── RBAC ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role,permission,expected", [
    (Role.EMPLOYEE, Permission.ROUTE_PROMPT, True),
    (Role.EMPLOYEE, Permission.VIEW_OWN_USAGE, True),
    (Role.EMPLOYEE, Permission.VIEW_TEAM_AUDIT, False),
    (Role.EMPLOYEE, Permission.MANAGE_USERS, False),
    (Role.MANAGER, Permission.VIEW_TEAM_AUDIT, True),
    (Role.MANAGER, Permission.SET_TEAM_QUOTA, True),
    (Role.MANAGER, Permission.MANAGE_USERS, False),
    (Role.ADMIN, Permission.MANAGE_USERS, True),
    (Role.ADMIN, Permission.VIEW_ALL_AUDIT, True),
    (Role.SERVICE_ACCOUNT, Permission.ROUTE_PROMPT, True),
    (Role.SERVICE_ACCOUNT, Permission.VIEW_OWN_AUDIT, False),
])
def test_role_permission_matrix(role, permission, expected):
    perms = permissions_for_role(role)
    assert (permission in perms) is expected


def test_require_permission_raises_on_denied():
    class Fake:
        permissions = frozenset({Permission.ROUTE_PROMPT})
    with pytest.raises(PermissionDenied, match="MANAGE_USERS|manage_users"):
        require_permission(Fake(), Permission.MANAGE_USERS)


def test_has_permission_handles_missing_attribute():
    """An object without `permissions` returns False (fail closed)."""
    assert has_permission(object(), Permission.ROUTE_PROMPT) is False


# ════════════════════════════════════════════════════════════════════════
# Audit log
# ════════════════════════════════════════════════════════════════════════

@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    return AuditLog(db_path=tmp_path / "audit.db")


def test_audit_append_returns_filled_event(audit: AuditLog):
    event = AuditEvent(
        type=AuditEventType.ROUTING_DECISION,
        actor_id="user-1", actor_email="a@x.com",
        org_id="org-1", resource="lineage:abc",
        action="created", detail={"cost": 0.01},
    )
    persisted = audit.append(event)
    assert persisted.hash_hex
    assert persisted.prev_hash == ""  # first event


def test_audit_chain_links_consecutive_events(audit: AuditLog):
    e1 = audit.append(AuditEvent(
        type="test", actor_id="u", actor_email="u@x", org_id="o",
        resource="r", action="a",
    ))
    e2 = audit.append(AuditEvent(
        type="test", actor_id="u", actor_email="u@x", org_id="o",
        resource="r", action="b",
    ))
    assert e2.prev_hash == e1.hash_hex


def test_audit_verify_chain_on_clean_log_passes(audit: AuditLog):
    for i in range(5):
        audit.append(AuditEvent(
            type="test", actor_id=f"u{i}", actor_email=f"u{i}@x",
            org_id="o", resource=f"r{i}", action="created",
        ))
    assert audit.verify_chain() is True


def test_audit_verify_chain_detects_tampering(audit: AuditLog, tmp_path):
    """Directly mutating a row's `action` column must break the chain."""
    import sqlite3

    for i in range(3):
        audit.append(AuditEvent(
            type="test", actor_id="u", actor_email="u@x",
            org_id="o", resource=f"r{i}", action="created",
        ))
    audit.close()

    conn = sqlite3.connect(str(tmp_path / "audit.db"))
    conn.execute(
        "UPDATE audit_events SET action = 'tampered' "
        "WHERE resource = 'r1'"
    )
    conn.commit()
    conn.close()

    tampered = AuditLog(db_path=tmp_path / "audit.db")
    with pytest.raises(TamperDetected):
        tampered.verify_chain()


def test_audit_recent_filters_by_org(audit: AuditLog):
    audit.append(AuditEvent(
        type="t", actor_id="u", actor_email="u@a", org_id="org-A",
        resource="r", action="a",
    ))
    audit.append(AuditEvent(
        type="t", actor_id="u", actor_email="u@b", org_id="org-B",
        resource="r", action="a",
    ))
    org_a_events = audit.recent(org_id="org-A")
    assert len(org_a_events) == 1
    assert org_a_events[0]["org_id"] == "org-A"


def test_audit_by_actor_returns_user_events(audit: AuditLog):
    audit.append(AuditEvent(
        type="t", actor_id="alice", actor_email="a@x", org_id="o",
        resource="r", action="a",
    ))
    audit.append(AuditEvent(
        type="t", actor_id="bob", actor_email="b@x", org_id="o",
        resource="r", action="a",
    ))
    assert len(audit.by_actor("alice")) == 1
    assert len(audit.by_actor("bob")) == 1


def test_audit_export_cef_emits_one_line_per_event(audit: AuditLog):
    for i in range(3):
        audit.append(AuditEvent(
            type=AuditEventType.ROUTING_DECISION,
            actor_id="u", actor_email="u@x", org_id="o",
            resource=f"r{i}", action="created",
        ))
    cef = audit.export_cef()
    lines = [ln for ln in cef.splitlines() if ln]
    assert len(lines) == 3
    for line in lines:
        assert line.startswith("CEF:0|Tessera|")


def test_audit_export_json_round_trip(audit: AuditLog):
    import json

    audit.append(AuditEvent(
        type="t", actor_id="u", actor_email="u@x", org_id="o",
        resource="r", action="a", detail={"k": "v"},
    ))
    parsed = json.loads(audit.export_json())
    assert len(parsed) == 1
    assert parsed[0]["actor_id"] == "u"


# ════════════════════════════════════════════════════════════════════════
# Redaction
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("prompt,expected_pattern", [
    ("My OPENAI_API_KEY=sk-proj-abcdefghij1234567890ABCDEFGHIJ",
     "openai_key"),
    ("ANTHROPIC=sk-ant-DONOTLEAKabcdefghijklmnopqrst",
     "anthropic_key"),
    ("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
     "aws_access_key"),
    ("token: ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJ",
     "github_token"),
    ("My email is alice.smith+test@example.com",
     "email"),
    ("SSN: 123-45-6789",
     "us_ssn"),
    ("Call me at +1 415-555-1234",
     "us_phone"),
])
def test_redaction_catches_default_patterns(prompt, expected_pattern):
    result = redact_prompt(prompt)
    assert result.any_redactions
    assert expected_pattern in result.counts
    assert f"[REDACTED:{expected_pattern}]" in result.text


def test_redaction_preserves_safe_content():
    result = redact_prompt("how does a foreign key constraint work")
    assert not result.any_redactions
    assert result.text == "how does a foreign key constraint work"


def test_redaction_luhn_validates_credit_cards():
    # Valid test card (passes Luhn): 4111-1111-1111-1111
    result = redact_prompt("card 4111 1111 1111 1111")
    assert "credit_card" in result.counts
    assert "[REDACTED:credit_card]" in result.text


def test_redaction_rejects_non_luhn_digit_strings():
    result = redact_prompt("ticket 1234 5678 9012 3456 reference number")
    assert "credit_card" not in result.counts


def test_redaction_disabled_passes_through():
    policy = RedactionPolicy.disabled()
    result = redact_prompt("my key sk-proj-DEFINITELYNOTACTUAL12345678",
                           policy=policy)
    assert not result.any_redactions
    assert "sk-proj-DEFINITELYNOTACTUAL" in result.text


def test_redaction_with_custom_patterns():
    policy = RedactionPolicy.default().with_patterns([
        ("employee_id", r"\bE\d{6}\b"),
    ])
    result = redact_prompt("user E123456 logged in", policy=policy)
    assert "employee_id" in result.counts
    assert "[REDACTED:employee_id]" in result.text


def test_redaction_counts_multiple_hits():
    result = redact_prompt(
        "alice@x.com and bob@y.com both have ssn 111-22-3333"
    )
    assert result.counts.get("email") == 2
    assert result.counts.get("us_ssn") == 1


# ════════════════════════════════════════════════════════════════════════
# Quotas
# ════════════════════════════════════════════════════════════════════════

@pytest.fixture
def quotas(tmp_path: Path) -> QuotaTracker:
    return QuotaTracker(db_path=tmp_path / "q.db")


def test_quota_unlimited_by_default(quotas: QuotaTracker):
    breached, info = quotas.would_exceed("user", "alice", 100.0)
    assert breached is False
    assert info.get("unlimited") is True


def test_quota_set_and_check_daily(quotas: QuotaTracker):
    quotas.set_policy("user", "alice",
                       QuotaPolicy(daily_cap_usd=10.0))
    breached, _ = quotas.would_exceed("user", "alice", 5.0)
    assert breached is False
    breached, info = quotas.would_exceed("user", "alice", 15.0)
    assert breached is True
    assert info["period"] == "daily"
    assert info["cap_usd"] == 10.0


def test_quota_consume_accumulates(quotas: QuotaTracker):
    quotas.set_policy("user", "alice", QuotaPolicy(daily_cap_usd=10.0))
    quotas.consume("user", "alice", 3.0)
    quotas.consume("user", "alice", 2.0)
    assert quotas.consumed("user", "alice", "daily") == pytest.approx(5.0)


def test_quota_breach_raises_with_full_context(quotas: QuotaTracker):
    quotas.set_policy("user", "alice", QuotaPolicy(daily_cap_usd=1.0))
    quotas.consume("user", "alice", 0.50)
    with pytest.raises(QuotaExceeded) as ctx:
        quotas.raise_if_would_exceed("user", "alice", 0.60)
    exc = ctx.value
    assert exc.scope == "user"
    assert exc.identifier == "alice"
    assert exc.cap_usd == 1.0
    assert exc.consumed_usd == pytest.approx(0.50)


def test_quota_hard_block_false_allows_overage(quotas: QuotaTracker):
    quotas.set_policy("user", "alice",
                       QuotaPolicy(daily_cap_usd=1.0, hard_block=False))
    quotas.consume("user", "alice", 0.99)
    breached, info = quotas.would_exceed("user", "alice", 10.0)
    # hard_block=False means even at 1000% overage, no breach
    assert breached is False


def test_quota_soft_warning_emitted(quotas: QuotaTracker):
    quotas.set_policy("user", "alice",
                       QuotaPolicy(daily_cap_usd=10.0,
                                   soft_warning_pct=0.5))
    quotas.consume("user", "alice", 4.0)
    _, info = quotas.would_exceed("user", "alice", 2.0)
    # 4 + 2 = 6, which is >50% of 10 → soft hit
    assert "soft_hits" in info


def test_quota_team_scope_independent_of_user(quotas: QuotaTracker):
    quotas.set_policy("team", "engineering",
                       QuotaPolicy(monthly_cap_usd=100.0))
    quotas.set_policy("user", "alice",
                       QuotaPolicy(daily_cap_usd=5.0))
    # Team monthly under cap; user daily over → user-scope breaches
    user_breached, _ = quotas.would_exceed("user", "alice", 10.0)
    team_breached, _ = quotas.would_exceed("team", "engineering", 50.0)
    assert user_breached is True
    assert team_breached is False
