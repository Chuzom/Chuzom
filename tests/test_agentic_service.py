"""P4b — delegation service serialization + llm_delegate MCP tool (fake backends)."""
from __future__ import annotations

import json

from chuzom.agentic.engine import AgentRunResult
from chuzom.agentic.ledger import AcceptanceResult, Milestone
from chuzom.agentic.service import run_delegation


class _Agent:
    def __init__(self, tier, out="OK"):
        self.tier = tier
        self.out = out

    def run(self, milestone, frozen_context, budget_left):
        return AgentRunResult({"output": self.out, "tier": self.tier}, 0.0)


def _canary(marker):
    return lambda a: AcceptanceResult(marker in str(a.get("output", "")))


def test_run_delegation_returns_json_serializable_bundle():
    ms = [Milestone("M1", "do", _canary("OK"))]
    out = run_delegation("goal", ms, {1: _Agent(1)}, baseline_cost_per_milestone=0.2)
    # fully JSON-serializable (MCP tools return strings)
    json.dumps(out)
    assert out["outcome"] == "complete" and out["ok"] is True
    assert out["milestones"][0]["status"] == "done"
    assert out["events"][0]["kind"] == "plan" and out["events"][-1]["kind"] == "complete"
    assert out["savings"]["saved_usd"] > 0


# ── the MCP tool ────────────────────────────────────────────────────────────
def _fake_planner_factory():
    def pm(_goal):
        return [{"id": "M1", "description": "do", "acceptance": {"type": "canary", "marker": "OK"}}]
    return pm


def _fake_adapters_factory():
    return {1: _Agent(1)}


async def test_llm_delegate_tool_with_injected_backends(monkeypatch):
    import chuzom.tools.agentic as tool
    monkeypatch.setattr(tool, "planner_factory", _fake_planner_factory)
    monkeypatch.setattr(tool, "adapters_factory", _fake_adapters_factory)
    out = json.loads(await tool.llm_delegate("build the thing"))
    assert out["outcome"] == "complete" and out["ok"] is True


async def test_llm_delegate_default_planner_fails_closed():
    """No injected planner → fail closed with an honest 'planning failed', never fabricate."""
    import chuzom.tools.agentic as tool
    out = json.loads(await tool.llm_delegate("x"))
    assert out["ok"] is False and "planning failed" in out["reason"]


def test_register_attaches_llm_delegate_tool():
    import chuzom.tools.agentic as tool
    names: list[str] = []

    class FakeMCP:
        def tool(self):
            def deco(fn):
                names.append(fn.__name__)
                return fn
            return deco

    tool.register(FakeMCP())
    assert "llm_delegate" in names
