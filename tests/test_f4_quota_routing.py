"""F4: per-identity quota bridge (quota_routing) — modes, gate, consume."""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom import quota_routing
from chuzom.enterprise.quotas import QuotaExceeded, QuotaPolicy, QuotaTracker
from chuzom.identity import TurnIdentity


@pytest.fixture
def tracker(tmp_path: Path) -> QuotaTracker:
    t = QuotaTracker(db_path=tmp_path / "quotas.db")
    yield t
    t.close()


def _ident(user_id="u1") -> TurnIdentity:
    return TurnIdentity(user_id=user_id, user_email="u1@acme.com", org_id="o1")


# ── Mode resolution (mirrors rbac_routing) ────────────────────────────────────

def test_mode_off_by_default_in_developer(monkeypatch):
    monkeypatch.delenv("CHUZOM_QUOTA_MODE", raising=False)
    monkeypatch.setenv("CHUZOM_PROFILE", "developer")
    assert quota_routing._resolve_mode() == "off"


def test_mode_strict_by_default_in_enterprise(monkeypatch):
    monkeypatch.delenv("CHUZOM_QUOTA_MODE", raising=False)
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    assert quota_routing._resolve_mode() == "strict"


def test_explicit_mode_wins(monkeypatch):
    monkeypatch.setenv("CHUZOM_PROFILE", "enterprise")
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "warn")
    assert quota_routing._resolve_mode() == "warn"
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "off")
    assert quota_routing._resolve_mode() == "off"


# ── Gate ──────────────────────────────────────────────────────────────────────

def test_off_mode_is_noop(monkeypatch, tracker):
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "off")
    tracker.set_policy("user", "u1", QuotaPolicy(daily_cap_usd=1.0))
    tracker.consume("user", "u1", 5.0)  # way over
    mode, breached, _ = quota_routing.check_quota(_ident(), tracker=tracker)
    assert mode == "off" and breached is False


def test_under_cap_not_breached(monkeypatch, tracker):
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "strict")
    tracker.set_policy("user", "u1", QuotaPolicy(daily_cap_usd=10.0))
    tracker.consume("user", "u1", 2.0)
    mode, breached, _ = quota_routing.check_quota(_ident(), tracker=tracker)
    assert mode == "strict" and breached is False


def test_over_cap_breached_strict(monkeypatch, tracker):
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "strict")
    tracker.set_policy("user", "u1", QuotaPolicy(daily_cap_usd=1.0))
    tracker.consume("user", "u1", 1.5)  # over daily cap
    mode, breached, info = quota_routing.check_quota(_ident(), tracker=tracker)
    assert mode == "strict" and breached is True
    assert info["period"] == "daily" and info["cap_usd"] == 1.0


def test_prospective_cost_pushes_over(monkeypatch, tracker):
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "strict")
    tracker.set_policy("user", "u1", QuotaPolicy(daily_cap_usd=1.0))
    tracker.consume("user", "u1", 0.9)
    # 0.9 consumed + 0.5 prospective = 1.4 > 1.0 → breach
    _, breached, _ = quota_routing.check_quota(_ident(), 0.5, tracker=tracker)
    assert breached is True


def test_unlimited_policy_never_breaches(monkeypatch, tracker):
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "strict")
    tracker.consume("user", "u1", 9999.0)  # no policy set → unlimited
    _, breached, _ = quota_routing.check_quota(_ident(), tracker=tracker)
    assert breached is False


def test_raise_quota_denied_builds_exception():
    info = {"scope": "user", "identifier": "u1", "period": "monthly",
            "cap_usd": 50.0, "consumed_usd": 60.0, "proposed_usd": 0.0}
    exc = quota_routing.raise_quota_denied(info)
    assert isinstance(exc, QuotaExceeded)
    assert exc.period == "monthly" and exc.cap_usd == 50.0


# ── Consumption ───────────────────────────────────────────────────────────────

def test_record_consumption_advances_accumulator(monkeypatch, tracker):
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "strict")
    tracker.set_policy("user", "u1", QuotaPolicy(daily_cap_usd=1.0))
    quota_routing.record_consumption(_ident(), 0.6, tracker=tracker)
    quota_routing.record_consumption(_ident(), 0.6, tracker=tracker)  # total 1.2 > 1.0
    _, breached, _ = quota_routing.check_quota(_ident(), tracker=tracker)
    assert breached is True


def test_record_consumption_noop_off_mode(monkeypatch, tracker):
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "off")
    quota_routing.record_consumption(_ident(), 5.0, tracker=tracker)
    assert tracker.consumed("user", "u1", "daily") == 0.0


def test_record_consumption_noop_zero_cost(monkeypatch, tracker):
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "strict")
    quota_routing.record_consumption(_ident(), 0.0, tracker=tracker)
    assert tracker.consumed("user", "u1", "daily") == 0.0
