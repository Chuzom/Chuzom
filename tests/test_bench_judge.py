"""H1 — bench judge degrades gracefully without an API key.

A subscription-only environment has no ANTHROPIC/OPENAI key, so the default
LLM-judge (anthropic/claude-3.5-sonnet via litellm) raises AuthenticationError.
Previously that crashed the entire benchmark run on the first subjective prompt.
The judge must instead fall back to a local model, and only if every judge is
unreachable return a neutral, clearly-labelled score.
"""
from __future__ import annotations

import types

import pytest

from bench.judge import JudgeResult, grade_objective, grade_subjective


def _fake_completion(content: str):
    """Build a fake litellm.acompletion returning `content`."""
    async def _acompletion(model, messages, **kwargs):  # noqa: ANN001
        msg = types.SimpleNamespace(content=content)
        choice = types.SimpleNamespace(message=msg)
        return types.SimpleNamespace(choices=[choice])
    return _acompletion


ENTRY = {"kind": "subjective", "prompt": "explain X", "judge_criteria": "be correct"}


@pytest.mark.asyncio
async def test_primary_judge_used_when_available(monkeypatch):
    import litellm
    monkeypatch.setattr(litellm, "acompletion",
                        _fake_completion('{"score": 5, "rationale": "great"}'))
    r = await grade_subjective("resp", ENTRY, judge_model="anthropic/claude-3.5-sonnet")
    assert r.score == 5
    assert r.judge_model == "anthropic/claude-3.5-sonnet"


@pytest.mark.asyncio
async def test_falls_back_to_local_judge_on_auth_error(monkeypatch):
    import litellm

    async def _acompletion(model, messages, **kwargs):  # noqa: ANN001
        if model == "anthropic/claude-3.5-sonnet":
            raise RuntimeError("AuthenticationError: Missing Anthropic API Key")
        # local fallback succeeds
        msg = types.SimpleNamespace(content='{"score": 4, "rationale": "ok via local"}')
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(litellm, "acompletion", _acompletion)
    monkeypatch.setenv("CHUZOM_BENCH_JUDGE_FALLBACK", "ollama/qwen2.5:7b")
    r = await grade_subjective("resp", ENTRY, judge_model="anthropic/claude-3.5-sonnet")
    assert r.score == 4
    assert r.judge_model == "ollama/qwen2.5:7b"  # fell back, did not crash


@pytest.mark.asyncio
async def test_all_judges_unreachable_returns_labeled_neutral(monkeypatch):
    import litellm

    async def _always_fail(model, messages, **kwargs):  # noqa: ANN001
        raise RuntimeError("AuthenticationError: no key")

    monkeypatch.setattr(litellm, "acompletion", _always_fail)
    monkeypatch.setenv("CHUZOM_BENCH_JUDGE_FALLBACK", "ollama/qwen2.5:7b")
    r = await grade_subjective("resp", ENTRY, judge_model="anthropic/claude-3.5-sonnet")
    # Run survives (no exception), score is neutral and clearly marked unavailable.
    assert isinstance(r, JudgeResult)
    assert r.score == 3
    assert r.judge_model == "unavailable"
    assert "judge unavailable" in r.rationale


def test_objective_grading_needs_no_judge():
    # Objective path never touches litellm — deterministic, key-free.
    r = grade_objective("Paris", {"expected_contains": ["Paris"], "kind": "objective"})
    assert r.score == 5 and r.judge_model == ""
