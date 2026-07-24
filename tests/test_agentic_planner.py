"""P4b(planner) — Hybrid planner: model proposes, objective checks enforced."""
from __future__ import annotations

import sys

import pytest

from chuzom.agentic.delegate import delegate
from chuzom.agentic.engine import AgentRunResult, Outcome
from chuzom.agentic.ledger import Milestone
from chuzom.agentic.planner import (
    PlanRejected,
    build_acceptance,
    hybrid_plan,
    plan_to_milestones,
)


def test_build_acceptance_objective_types():
    assert build_acceptance({"type": "canary", "marker": "OBJ_CANARY"})({"output": "OBJ_CANARY"}).ok
    assert build_acceptance({"type": "diff", "files": ["a.py"]})({"files": ["a.py"]}).ok
    ok = build_acceptance({"type": "cmd", "command": [sys.executable, "-c", "pass"]})
    assert ok({}).ok


def test_build_acceptance_rejects_subjective_and_unknown():
    for bad in ({"type": "looks_good"}, {"type": "model_says_done"}, {"type": None}, {}):
        with pytest.raises(PlanRejected):
            build_acceptance(bad)


def test_plan_to_milestones_builds_and_validates():
    plan = [
        {"id": "M1", "description": "scaffold",
         "acceptance": {"type": "diff", "files": ["m.py"]}},
        {"id": "M2", "description": "impl", "deps": ["M1"],
         "acceptance": {"type": "canary", "marker": "M2_CANARY"}},
    ]
    ms = plan_to_milestones(plan)
    assert [m.id for m in ms] == ["M1", "M2"]
    assert ms[1].deps == ("M1",)
    assert ms[0].acceptance({"files": ["m.py"]}).ok


def test_plan_rejected_when_milestone_has_no_objective_check():
    # a milestone with a subjective acceptance sinks the whole plan (fail closed)
    plan = [{"id": "M1", "acceptance": {"type": "vibes"}}]
    with pytest.raises(PlanRejected):
        plan_to_milestones(plan)
    # ...and one with no acceptance at all
    with pytest.raises(PlanRejected):
        plan_to_milestones([{"id": "M1", "description": "x"}])


async def test_hybrid_plan_with_fake_model_feeds_delegate():
    def fake_planner(goal):
        assert "build widget" in goal
        return [{"id": "M1", "description": "make it",
                 "acceptance": {"type": "canary", "marker": "WIDGET_OK"}}]

    ms = await hybrid_plan("build widget", fake_planner)
    assert isinstance(ms[0], Milestone)

    class Agent0:
        tier = 0

        def run(self, milestone, frozen_context, budget_left):
            return AgentRunResult({"output": "WIDGET_OK"}, 0.01)

    res = delegate("build widget", ms, {0: Agent0()}, baseline_cost_per_milestone=0.2)
    assert res.outcome is Outcome.COMPLETE


async def test_hybrid_plan_rejects_non_list_and_empty():
    with pytest.raises(PlanRejected):
        await hybrid_plan("g", lambda _g: {"not": "a list"})
    with pytest.raises(PlanRejected):
        await hybrid_plan("g", lambda _g: [])


async def test_hybrid_plan_awaits_async_planner():
    async def async_planner(goal):
        return [{"id": "M1", "description": "x", "acceptance": {"type": "canary", "marker": "ASYNC_CANARY"}}]

    ms = await hybrid_plan("g", async_planner)
    assert ms[0].id == "M1"
