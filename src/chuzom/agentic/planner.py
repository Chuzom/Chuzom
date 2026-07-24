"""Hybrid planner — a model proposes the milestone breakdown, but every
acceptance check is CONSTRAINED to the objective vocabulary (cmd/lint/diff/canary)
and validated. A milestone that proposes a subjective / unknown check is rejected,
so the "a milestone is DONE only on an objective, executable check — never the
model's self-report" guarantee survives even when a model does the planning.

The planner model is injected as a callable returning a raw plan (list of dicts),
so unit tests drive it with a fake — no live model.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from chuzom.agentic.acceptance import (
    canary_check,
    cmd_check,
    diff_check,
    lint_check,
)
from chuzom.agentic.ledger import AcceptanceCheck, Milestone

# Only these acceptance types may be emitted by a planner — all objective/executable.
ALLOWED_CHECK_TYPES = frozenset({"cmd", "lint", "diff", "canary"})

# planner_model(goal) -> raw plan (list of milestone dicts), sync OR async.
# The live default planner is async (it calls chuzom routing); test fakes are sync.
PlannerModel = Callable[[str], Any]


class PlanRejected(ValueError):
    """A proposed plan/milestone lacks a valid objective acceptance check."""


def build_acceptance(spec: dict[str, Any]) -> AcceptanceCheck:
    """Map an objective check spec → an AcceptanceCheck. Rejects anything not in
    the whitelist (e.g. a model trying to sneak in a subjective 'looks_good')."""
    if not isinstance(spec, dict):
        raise PlanRejected(f"acceptance must be a spec dict, got {type(spec).__name__}")
    t = spec.get("type")
    if t not in ALLOWED_CHECK_TYPES:
        raise PlanRejected(f"non-objective / unknown acceptance type: {t!r}")
    if t == "cmd":
        return cmd_check(spec["command"], cwd=spec.get("cwd"), timeout=spec.get("timeout", 60.0))
    if t == "lint":
        return lint_check(spec["paths"], cwd=spec.get("cwd"))
    if t == "diff":
        return diff_check(files=spec.get("files", ()), symbols=spec.get("symbols", ()))
    # t == "canary"
    return canary_check(spec["marker"], field=spec.get("field", "output"))


def plan_to_milestones(plan: list[dict[str, Any]]) -> list[Milestone]:
    """Validate + build a raw plan into Milestones. Every milestone MUST carry an
    objective acceptance spec or the whole plan is rejected (fail closed)."""
    if not plan:
        raise PlanRejected("empty plan")
    milestones: list[Milestone] = []
    for item in plan:
        mid = item.get("id")
        if not mid:
            raise PlanRejected("milestone missing 'id'")
        if "acceptance" not in item:
            raise PlanRejected(f"milestone {mid!r} has no acceptance check")
        acceptance = build_acceptance(item["acceptance"])  # raises PlanRejected if subjective
        milestones.append(
            Milestone(
                id=str(mid),
                description=str(item.get("description", "")),
                acceptance=acceptance,
                deps=tuple(item.get("deps", ())),
                reversible=bool(item.get("reversible", True)),
            )
        )
    return milestones


async def hybrid_plan(goal: str, planner_model: PlannerModel) -> list[Milestone]:
    """Ask the (injected) planner model for a breakdown, then constrain + build it.

    Async so the live default planner can call chuzom routing. Tolerates a sync
    planner (test fakes) — if the result is awaitable it's awaited, otherwise used
    directly.
    """
    raw = planner_model(goal)
    if inspect.isawaitable(raw):
        raw = await raw
    if not isinstance(raw, list):
        raise PlanRejected(f"planner must return a list of milestones, got {type(raw).__name__}")
    return plan_to_milestones(raw)
