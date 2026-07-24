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


def test_llm_is_registered():
    m = _FakeMcp()
    consolidated.register(m, should_register=lambda _n: True)
    assert "llm" in m.registered and "llm_act" in m.registered


async def test_llm_dispatches_by_task(monkeypatch):
    calls = {}

    def _fake(name, has_complexity=True):
        async def f(prompt, ctx, complexity=None, system_prompt=None, context=None, **kw):
            calls[name] = {"prompt": prompt, "complexity": complexity, "context": context}
            return f"[{name}]"
        return f

    async def _fake_research(prompt, ctx, system_prompt=None, max_tokens=None, context=None, **kw):
        calls["research"] = {"prompt": prompt, "context": context}
        return "[research]"

    monkeypatch.setattr("chuzom.tools.consolidated.llm_query", _fake("query"))
    monkeypatch.setattr("chuzom.tools.consolidated.llm_analyze", _fake("analyze"))
    monkeypatch.setattr("chuzom.tools.consolidated.llm_code", _fake("code"))
    monkeypatch.setattr("chuzom.tools.consolidated.llm_generate", _fake("generate"))
    monkeypatch.setattr("chuzom.tools.consolidated.llm_research", _fake_research)

    assert await consolidated.llm("x", ctx=None, task="code") == "[code]"
    assert await consolidated.llm("x", ctx=None, task="research") == "[research]"
    assert await consolidated.llm("x", ctx=None, task="auto") == "[query]"          # auto -> query
    assert await consolidated.llm("x", ctx=None, task="generate", tier="best") == "[generate]"
    assert calls["code"]["complexity"] == "moderate"                                # balanced tier
    assert calls["generate"]["complexity"] == "complex"                             # best tier
    assert "complexity" not in calls["research"]                                    # research has none
