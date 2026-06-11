"""P0-2 — team budgets actually enforce at the routing chokepoint.

Team caps were settable via the RBAC-gated admin API
(``quotas.set_policy("team", ...)``) but NEVER enforced: ``quota_routing``
hardcoded the ``"user"`` scope and ``TurnIdentity`` carried no ``team_id``. So
an operator could set a team cap that had zero effect. This threads ``team_id``
onto the turn identity and adds a team-scope check/consume alongside the user
one — a team cap now bites, and it aggregates spend across every user in the
team (the whole point of a *team* budget).
"""
from __future__ import annotations

import types
from pathlib import Path

import pytest

from chuzom.enterprise.quotas import QuotaPolicy, QuotaTracker


def _identity(user_id: str, team_id: str | None):
    # quota_routing reads attributes via getattr — a SimpleNamespace is enough.
    return types.SimpleNamespace(user_id=user_id, team_id=team_id)


@pytest.fixture
def tracker(tmp_path: Path) -> QuotaTracker:
    return QuotaTracker(db_path=tmp_path / "quota.db", check_same_thread=False)


@pytest.fixture(autouse=True)
def _strict(monkeypatch):
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "strict")


# ── TurnIdentity carries team_id ─────────────────────────────────────────────

def test_turn_identity_has_team_id_field():
    from chuzom.identity import TurnIdentity

    ident = TurnIdentity(
        user_id="u1", user_email="u1@x", org_id="o1", team_id="t1",
    )
    assert ident.team_id == "t1"


def test_dev_identity_reads_team_env(monkeypatch):
    monkeypatch.delenv("CHUZOM_PROFILE", raising=False)
    monkeypatch.setenv("CHUZOM_TEAM_ID", "platform")
    from chuzom.identity import current_identity

    assert current_identity().team_id == "platform"


def test_dev_identity_team_none_when_unset(monkeypatch):
    monkeypatch.delenv("CHUZOM_PROFILE", raising=False)
    monkeypatch.delenv("CHUZOM_TEAM_ID", raising=False)
    from chuzom.identity import current_identity

    assert current_identity().team_id is None


# ── team-scope enforcement ───────────────────────────────────────────────────

def test_team_cap_breach_denies_turn(tracker):
    from chuzom.quota_routing import check_quota

    tracker.set_policy(
        "team", "t1",
        QuotaPolicy(daily_cap_usd=1.0, hard_block=True),
    )
    tracker.consume("team", "t1", 1.0)  # team already at cap

    mode, breached, info = check_quota(
        _identity("alice", "t1"), 0.50, tracker=tracker,
    )
    assert mode == "strict"
    assert breached is True
    assert info["scope"] == "team"


def test_user_under_cap_but_team_over_is_denied(tracker):
    """The user has no cap, but their team does — the team cap must bite."""
    from chuzom.quota_routing import check_quota

    tracker.set_policy("team", "t1", QuotaPolicy(daily_cap_usd=2.0, hard_block=True))
    tracker.consume("team", "t1", 2.0)

    _, breached, info = check_quota(_identity("bob", "t1"), 0.10, tracker=tracker)
    assert breached is True
    assert info["scope"] == "team"


def test_team_consumption_aggregates_across_users(tracker):
    """record_consumption charges the team accumulator, so two users in the
    same team jointly exhaust the team cap."""
    from chuzom.quota_routing import check_quota, record_consumption

    tracker.set_policy("team", "t1", QuotaPolicy(daily_cap_usd=1.0, hard_block=True))

    record_consumption(_identity("alice", "t1"), 0.60, tracker=tracker)
    record_consumption(_identity("bob", "t1"), 0.60, tracker=tracker)  # team now 1.20 > 1.0

    _, breached, info = check_quota(_identity("carol", "t1"), 0.0, tracker=tracker)
    assert breached is True
    assert info["scope"] == "team"
    assert tracker.consumed("team", "t1", "daily") == pytest.approx(1.20)


def test_no_team_id_falls_back_to_user_only(tracker):
    """Backward compatible: team_id=None → only the user scope is checked."""
    from chuzom.quota_routing import check_quota

    tracker.set_policy("user", "alice", QuotaPolicy(daily_cap_usd=1.0, hard_block=True))
    tracker.consume("user", "alice", 1.0)

    _, breached, info = check_quota(_identity("alice", None), 0.10, tracker=tracker)
    assert breached is True
    assert info["scope"] == "user"


def test_user_cap_checked_before_team(tracker):
    """Both scopes capped; the user's own breach denies first (it's the
    tightest attribution)."""
    from chuzom.quota_routing import check_quota

    tracker.set_policy("user", "alice", QuotaPolicy(daily_cap_usd=1.0, hard_block=True))
    tracker.set_policy("team", "t1", QuotaPolicy(daily_cap_usd=100.0, hard_block=True))
    tracker.consume("user", "alice", 1.0)

    _, breached, info = check_quota(_identity("alice", "t1"), 0.10, tracker=tracker)
    assert breached is True
    assert info["scope"] == "user"
