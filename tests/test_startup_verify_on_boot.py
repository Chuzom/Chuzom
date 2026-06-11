"""Refinement #11 — enterprise verifier wired into MCP server startup.

``chuzom.server._startup_verify_or_die`` runs the verifier at the
top of ``main()`` under ``CHUZOM_PROFILE=enterprise`` and exits
with code 1 if any check fails. Developer-profile boot is unchanged.
Operators can bypass for emergency debug via
``CHUZOM_SKIP_STARTUP_VERIFY=on``.

These tests pin the four control-flow paths so the boot contract
is enforced regardless of future refactors:

* Developer profile → no-op (don't even import the verifier).
* Enterprise profile + clean config → no-op (verifier passes).
* Enterprise profile + broken config → ``SystemExit(1)`` with a
  remediation list on stderr.
* Enterprise profile + skip env → no-op + visible warning on stderr.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom import server as srv
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role



@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path: Path) -> None:
    """Each test starts with a clean env + ephemeral DB paths."""
    for env in (
        "CHUZOM_PROFILE",
        "CHUZOM_TOKEN",
        "CHUZOM_RBAC_MODE",
        "CHUZOM_AUDIT_DISABLED",
        "CHUZOM_REDACTION",
        "CHUZOM_SKIP_STARTUP_VERIFY",
        "CHUZOM_USER_ID",
        "CHUZOM_USER_EMAIL",
        "CHUZOM_ORG_ID",
    ):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv(
        "CHUZOM_IDENTITY_PATH", str(tmp_path / "identity.db")
    )
    monkeypatch.setenv(
        "CHUZOM_AUDIT_PATH", str(tmp_path / "audit.db")
    )
    monkeypatch.setenv(
        "CHUZOM_ADMIN_ACTIONS_PATH",
        str(tmp_path / "admin_actions.db"),
    )
    monkeypatch.setenv(
        "CHUZOM_POLICY_STORE_PATH",
        str(tmp_path / "policy_versions.db"),
    )
    from chuzom import identity as identity_mod
    monkeypatch.setattr(identity_mod, "_enterprise_store", None)


def test_developer_profile_skips_verifier() -> None:
    """Pre-refinement-#11 behaviour: no profile → verifier never
    runs. Pinning so a future "always verify" tweak doesn't break
    every developer install."""
    # No SystemExit raised → function returns cleanly.
    srv._startup_verify_or_die()


def test_enterprise_clean_config_passes(
    monkeypatch, tmp_path: Path,
) -> None:
    """Enterprise profile + a valid token + all the safety defaults
    that come with the profile → verifier passes, no exit."""
    store = IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False,
    )
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="ops@acme", display_name="Ops", role=Role.EMPLOYEE,
    )
    tok = store.issue_token(user.id, name="t")
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_TOKEN", tok.plaintext)
    from chuzom import identity as identity_mod
    monkeypatch.setattr(identity_mod, "_enterprise_store", store)
    # Should not raise.
    srv._startup_verify_or_die()


def test_enterprise_missing_token_refuses_to_start(
    monkeypatch, capsys,
) -> None:
    """The headline test. Enterprise profile + no CHUZOM_TOKEN →
    SystemExit(1) with remediation on stderr. This is the friction
    we want to surface BEFORE any routed call fails inscrutably at
    the MCP transport layer (OP-1 / OP-4 territory)."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    with pytest.raises(SystemExit) as excinfo:
        srv._startup_verify_or_die()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "FAILED" in err
    assert "token_present" in err
    assert "CHUZOM_TOKEN" in err


def test_enterprise_skip_env_bypasses_with_warning(
    monkeypatch, capsys,
) -> None:
    """Emergency debug escape hatch — boot proceeds but a loud
    warning fires on stderr so it cannot be silent."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_SKIP_STARTUP_VERIFY", "on")
    srv._startup_verify_or_die()
    err = capsys.readouterr().err
    assert "CHUZOM_SKIP_STARTUP_VERIFY" in err
    assert "degraded" in err.lower() or "skipping" in err.lower()


@pytest.mark.parametrize(
    "skip_value", ["on", "1", "true", "yes", "ON", "True"],
)
def test_skip_env_truthy_variants(
    monkeypatch, capsys, skip_value: str,
) -> None:
    """The skip env follows the standard chuzom truthy convention."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_SKIP_STARTUP_VERIFY", skip_value)
    srv._startup_verify_or_die()


@pytest.mark.parametrize(
    "skip_value", ["off", "0", "false", "no", "anything"],
)
def test_skip_env_falsy_values_still_run_verifier(
    monkeypatch, skip_value: str,
) -> None:
    """Typos and explicit-off must NOT silently skip — they go
    through normal verification (which then fails because no token
    is configured)."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_SKIP_STARTUP_VERIFY", skip_value)
    with pytest.raises(SystemExit):
        srv._startup_verify_or_die()


def test_main_calls_verify_then_runs(monkeypatch) -> None:
    """``main()`` calls the verifier BEFORE binding the MCP server.
    Pin the order — a misconfigured deployment must refuse to start
    instead of binding and serving inscrutable transport errors."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_SKIP_STARTUP_VERIFY", "on")
    calls: list[str] = []
    monkeypatch.setattr(srv.mcp, "run", lambda: calls.append("run"))
    srv.main()
    # Order matters: verifier first (skipped here), then mcp.run().
    assert calls == ["run"]


def test_main_refuses_to_run_when_verifier_fails(monkeypatch) -> None:
    """Critical: the MCP transport must NOT bind if the verifier
    detects a misconfigured enterprise deployment."""
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    # No CHUZOM_TOKEN → verifier fails.
    calls: list[str] = []
    monkeypatch.setattr(srv.mcp, "run", lambda: calls.append("run"))
    with pytest.raises(SystemExit):
        srv.main()
    # mcp.run() was never called — startup was refused.
    assert calls == []
