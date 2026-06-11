"""Refinement #9 — ``chuzom verify-enterprise`` startup verifier.

Tests cover three layers:

* Individual checks return the right ``CheckResult`` shape for each
  pass / fail configuration.
* The orchestrator (``run_verifier``) composes them into a structured
  report whose ``all_passed`` flag matches reality.
* The CLI wrapper (``cmd_verify_enterprise``) maps that report onto
  the documented exit codes (0 / 1 / 2) and the right output format
  (text vs ``--json``).

Throughout, the checks are run against scoped fixtures so a hostile
``~/.chuzom`` on the test machine cannot leak state.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom.commands import verify_enterprise as ve
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role



# ── 1. Per-check unit tests ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_env_and_paths(monkeypatch, tmp_path: Path) -> None:
    """Each test starts with a clean env + ephemeral DB paths so
    the verifier never touches the developer's real ~/.chuzom."""
    for env in (
        "CHUZOM_PROFILE",
        "CHUZOM_TOKEN",
        "CHUZOM_RBAC_MODE",
        "CHUZOM_AUDIT_DISABLED",
        "CHUZOM_REDACTION",
        "CHUZOM_BUDGET_FORECAST_MODE",
        "CHUZOM_USER_ID",
        "CHUZOM_USER_EMAIL",
        "CHUZOM_ORG_ID",
        "CHUZOM_AGENT_ID",
        "CHUZOM_TENANT_ID",
    ):
        monkeypatch.delenv(env, raising=False)
    # Route every default DB path into the test's tmp_path. The
    # primitives all honour an env-driven override or a constructor
    # arg; the env knobs match what each store's ``__init__`` reads.
    monkeypatch.setenv("CHUZOM_IDENTITY_PATH", str(tmp_path / "identity.db"))
    monkeypatch.setenv("CHUZOM_AUDIT_PATH", str(tmp_path / "audit.db"))
    monkeypatch.setenv(
        "CHUZOM_ADMIN_ACTIONS_PATH", str(tmp_path / "admin_actions.db"),
    )
    monkeypatch.setenv(
        "CHUZOM_POLICY_STORE_PATH", str(tmp_path / "policy_versions.db"),
    )
    # Reset the cached enterprise identity-store singleton so each
    # test resolves against the test's IdentityStore, not a leaked
    # one from a previous test.
    from chuzom import identity as identity_mod
    monkeypatch.setattr(identity_mod, "_enterprise_store", None)


def test_profile_check_passes_under_enterprise(monkeypatch) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    r = ve._check_profile_set_to_enterprise()
    assert r.passed is True
    assert "enterprise" in r.status


def test_profile_check_fails_under_developer() -> None:
    r = ve._check_profile_set_to_enterprise()
    assert r.passed is False
    assert "CHUZOM_PROFILE" in r.remediation


def test_token_present_check_fails_when_empty() -> None:
    r = ve._check_token_present()
    assert r.passed is False
    assert "CHUZOM_TOKEN" in r.remediation


def test_token_present_check_passes_when_set(monkeypatch) -> None:
    monkeypatch.setenv("CHUZOM_TOKEN", "tsr_abcdef")
    r = ve._check_token_present()
    assert r.passed is True
    assert "set" in r.status.lower()


def test_token_authenticates_check_passes_with_valid_token(
    monkeypatch, tmp_path: Path
) -> None:
    """End-to-end: create a real IdentityStore, issue a real token,
    point CHUZOM_TOKEN at it, watch the check pass."""
    store = IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False,
    )
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="prod@acme", display_name="P", role=Role.EMPLOYEE,
    )
    tok = store.issue_token(user.id, name="t")
    monkeypatch.setenv("CHUZOM_TOKEN", tok.plaintext)
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    from chuzom import identity as identity_mod
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    r = ve._check_token_authenticates()
    assert r.passed is True
    assert "prod@acme" in r.status


def test_token_authenticates_check_fails_with_missing_token(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    # No CHUZOM_TOKEN, so authentication can't even start.
    r = ve._check_token_authenticates()
    assert r.passed is False
    assert "Permission.ROUTE_PROMPT" in r.remediation or "token" in r.remediation.lower()


def test_rbac_strict_check_passes_under_enterprise(monkeypatch) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    r = ve._check_rbac_strict()
    assert r.passed is True
    assert "strict" in r.status


def test_rbac_strict_check_fails_under_developer() -> None:
    """Developer profile default is ``off`` — verifier surfaces it."""
    r = ve._check_rbac_strict()
    assert r.passed is False
    assert "off" in r.status.lower() or "warn" in r.status.lower()


def test_audit_active_check_under_enterprise(monkeypatch) -> None:
    """Even with CHUZOM_AUDIT_DISABLED=1 set, enterprise ignores it
    and the check should still pass with a note."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_AUDIT_DISABLED", "1")
    r = ve._check_audit_not_disabled()
    assert r.passed is True
    assert "ignored under enterprise" in r.status


def test_audit_active_check_under_developer_with_disable_env(
    monkeypatch,
) -> None:
    """Under developer profile the env DOES disable; the verifier
    surfaces that as a failure for the dev-self-check path."""
    monkeypatch.setenv("CHUZOM_AUDIT_DISABLED", "1")
    r = ve._check_audit_not_disabled()
    assert r.passed is False
    assert "unset" in r.remediation.lower()


def test_redaction_check_under_enterprise(monkeypatch) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    r = ve._check_redaction_on()
    assert r.passed is True


def test_redaction_check_under_developer() -> None:
    """Pre-G-012 default: redaction off. Verifier surfaces it as
    failing for the strict path; this is the test that pins the
    developer-vs-enterprise asymmetry."""
    r = ve._check_redaction_on()
    assert r.passed is False
    assert "CHUZOM_REDACTION" in r.remediation


# ── 2. DB-reachability checks ──────────────────────────────────────────────


def test_identity_db_check_passes_against_writable_tmp() -> None:
    r = ve._check_identity_db_reachable()
    assert r.passed is True


def test_audit_db_check_passes_against_writable_tmp() -> None:
    assert ve._check_audit_db_reachable().passed is True


def test_admin_actions_db_check_passes_against_writable_tmp() -> None:
    assert ve._check_admin_actions_db_reachable().passed is True


def test_policy_store_check_passes_against_writable_tmp() -> None:
    assert ve._check_policy_store_reachable().passed is True


def test_db_check_fails_on_unwritable_path(monkeypatch, tmp_path: Path) -> None:
    """Point the identity DB at a directory that doesn't exist AND
    cannot be created (deeply nested under a non-writable root). The
    helper must catch the OSError and report a useful status."""
    bad = "/proc/cant-create-here/identity.db"
    monkeypatch.setenv("CHUZOM_IDENTITY_PATH", bad)
    r = ve._check_identity_db_reachable()
    assert r.passed is False
    assert "open failed" in r.status or "probe failed" in r.status


# ── 3. Orchestrator + report ───────────────────────────────────────────────


def test_run_verifier_enterprise_returns_full_check_list() -> None:
    report = ve.run_verifier(enterprise=True)
    assert report.profile == "enterprise"
    assert len(report.results) == len(ve.ENTERPRISE_CHECKS)
    # Without any env setup the enterprise verifier MUST report
    # failures (profile not set, token missing, etc.) — the
    # all_passed flag must reflect that.
    assert report.all_passed is False


def test_run_verifier_developer_returns_lighter_check_list() -> None:
    report = ve.run_verifier(enterprise=False)
    assert report.profile == "developer"
    assert len(report.results) == len(ve.DEVELOPER_CHECKS)
    # Developer-mode checks are only DB reachability; in the tmp
    # path environment those all pass.
    assert report.all_passed is True


def test_report_to_dict_round_trip() -> None:
    report = ve.run_verifier(enterprise=False)
    d = report.to_dict()
    assert d["profile"] == "developer"
    assert "all_passed" in d
    assert isinstance(d["checks"], list)
    for r, dr in zip(report.results, d["checks"]):
        assert dr["name"] == r.name
        assert dr["passed"] == r.passed


# ── 4. CLI wrapper ─────────────────────────────────────────────────────────


def test_cli_help_returns_zero(capsys) -> None:
    assert ve.cmd_verify_enterprise(["--help"]) == 0
    out = capsys.readouterr().out
    assert "verify-enterprise" in out
    assert "--enterprise" in out or "--developer" in out


def test_cli_unknown_flag_returns_two(capsys) -> None:
    assert ve.cmd_verify_enterprise(["--bogus"]) == 2
    err = capsys.readouterr().err
    assert "Unknown flag" in err


def test_cli_default_is_enterprise_returns_one_when_misconfigured(
    capsys,
) -> None:
    """With no env setup the enterprise default fails fast — exit 1.
    This is THE test that proves the verifier serves its purpose as
    a readiness probe."""
    rc = ve.cmd_verify_enterprise([])
    assert rc == 1
    out = capsys.readouterr().out
    # The red checklist must surface at least one ✗.
    assert "✗" in out


def test_cli_developer_check_passes_in_clean_env(capsys) -> None:
    rc = ve.cmd_verify_enterprise(["--developer"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "All checks passed" in out


def test_cli_json_output_is_machine_readable(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")  # but no token etc.
    rc = ve.cmd_verify_enterprise(["--json"])
    assert rc == 1
    out = capsys.readouterr().out.strip()
    import json
    parsed = json.loads(out)
    assert parsed["profile"] == "enterprise"
    assert parsed["all_passed"] is False
    assert any(c["name"] == "token_present" for c in parsed["checks"])
