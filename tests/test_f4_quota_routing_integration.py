"""F4 integration: an over-cap user is refused by route_and_call before dispatch.

The strict quota gate raises before any reservation/redaction/provider call, so
this exercises the real router path without needing live providers.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom import quota_routing
from chuzom.enterprise.quotas import QuotaExceeded, QuotaPolicy, QuotaTracker
from chuzom.identity import TurnIdentity
from chuzom.router import route_and_call
from chuzom.types import TaskType


def _over_cap_tracker(tmp_path: Path) -> QuotaTracker:
    t = QuotaTracker(db_path=tmp_path / "quotas.db", check_same_thread=False)
    t.set_policy("user", "u1", QuotaPolicy(daily_cap_usd=1.0))
    t.consume("user", "u1", 5.0)  # already 5x over the daily cap
    return t


async def test_strict_over_cap_refused_before_dispatch(tmp_path, monkeypatch):
    tracker = _over_cap_tracker(tmp_path)
    monkeypatch.setattr(quota_routing, "_tracker", tracker)
    monkeypatch.setenv("CHUZOM_QUOTA_MODE", "strict")  # gate fires explicitly
    # Keep RBAC off and RouterConfig happy: deployment profile stays developer
    # (CHUZOM_PROFILE is the routing-config field, NOT the deployment profile).
    monkeypatch.delenv("CHUZOM_DEPLOYMENT_PROFILE", raising=False)
    monkeypatch.delenv("CHUZOM_RBAC_MODE", raising=False)
    ident = TurnIdentity(user_id="u1", user_email="u1@acme.com", org_id="o1")

    with pytest.raises(QuotaExceeded) as exc:
        await route_and_call(TaskType.QUERY, "hello world", identity=ident)
    assert exc.value.scope == "user" and exc.value.identifier == "u1"
    tracker.close()

# Under-cap behaviour (gate lets the turn through) is covered without live
# providers by tests/test_f4_quota_routing.py::test_under_cap_not_breached.
