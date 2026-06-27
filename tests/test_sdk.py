"""1c — the in-process SDK: ``from chuzom import route``."""
import pytest

import chuzom
from chuzom import RouteResult, RoutingError, route


def test_route_is_exported():
    assert callable(chuzom.route)
    assert "route" in chuzom.__all__


def test_route_result_total_tokens():
    r = RouteResult(text="hi", model="ollama/x", provider="ollama",
                    input_tokens=10, output_tokens=5, latency_ms=100)
    assert r.total_tokens == 15


def test_empty_prompt_raises():
    with pytest.raises(ValueError):
        route("   ")


def test_chain_exhausted_raises(monkeypatch):
    # Force the router to fail → RoutingError so callers can fall back.
    monkeypatch.setattr("chuzom.hooks.chain_builder.get_current_pressure",
                        lambda: ("green", 5))
    monkeypatch.setattr("chuzom.hooks.chain_builder.build_chain",
                        lambda *a, **k: [])
    monkeypatch.setattr("chuzom.hooks.direct_executor.execute_chain",
                        lambda *a, **k: None)
    with pytest.raises(RoutingError):
        route("hello world, a non-empty prompt")
