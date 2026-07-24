"""North Star P4-S1: the consolidated `llm_act` front-door alias (non-breaking)."""
from __future__ import annotations

from chuzom.tools import consolidated


class _FakeMcp:
    def __init__(self):
        self.registered = []

    def tool(self, *a, **k):
        def deco(fn):
            self.registered.append(fn.__name__)
            return fn
        return deco


def test_llm_act_is_registered():
    m = _FakeMcp()
    consolidated.register(m, should_register=lambda _n: True)
    assert "llm_act" in m.registered


def test_llm_act_respects_slim_gate():
    m = _FakeMcp()
    consolidated.register(m, should_register=lambda _n: False)  # slim mode off
    assert "llm_act" not in m.registered


async def test_llm_act_delegates_to_llm_delegate(monkeypatch):
    seen = {}

    async def fake_delegate(task, budget_usd=1.0, context="", **kw):
        seen.update(task=task, budget=budget_usd, context=context)
        return '{"outcome": "complete"}'

    monkeypatch.setattr("chuzom.tools.consolidated.llm_delegate", fake_delegate)
    out = await consolidated.llm_act("fix the bug", budget_usd=2.0, context="ctx")
    assert seen == {"task": "fix the bug", "budget": 2.0, "context": "ctx"}
    assert "complete" in out
