"""P1 tuning regression: headless complex routes reach broker-backed Codex first.

The headless gateway daemon disables local Codex/Gemini subprocess backends. When
a session broker offers them, the complex chain must place broker-backed Codex at
the FRONT (the capable free path) so it isn't buried behind unreachable Claude and
slow local reasoning models. Simple/BUDGET routes must stay free-local.
"""

from unittest.mock import AsyncMock, patch

import pytest

import chuzom.session_broker as sb
from chuzom.router import _build_and_filter_chain
from chuzom.types import Complexity, RoutingProfile, TaskType


def _cfg():
    from chuzom.config import get_config
    return get_config()


@pytest.mark.asyncio
async def test_headless_complex_puts_broker_codex_first(mock_env, monkeypatch):
    """Premium/complex + broker offers codex → codex is the first candidate."""
    sb._provider_cache = None
    monkeypatch.setenv("CHUZOM_DISABLE_SUBPROCESS_BACKENDS", "codex,gemini_cli")
    with patch("chuzom.session_broker.broker_providers",
               new=AsyncMock(return_value=frozenset({"codex"}))):
        chain = await _build_and_filter_chain(
            TaskType.ANALYZE, RoutingProfile.PREMIUM, None, "complex", Complexity.COMPLEX, _cfg()
        )
    assert chain, "chain should not be empty"
    assert chain[0].startswith("codex/"), \
        f"expected broker-backed codex first, got {chain[:3]}"


@pytest.mark.asyncio
async def test_headless_simple_keeps_local_first(mock_env, monkeypatch):
    """SIMPLE/BUDGET keeps a local model ahead of codex even when the broker
    offers codex — the re-assert is premium-only, so cheap-first is preserved.

    The base chain is pinned to include a local Ollama model so the assertion is
    env-independent (CI has no live Ollama, which would otherwise drop it)."""
    sb._provider_cache = None
    monkeypatch.setenv("CHUZOM_DISABLE_SUBPROCESS_BACKENDS", "codex,gemini_cli")
    base = ["ollama/qwen2.5-coder:7b", "openai/gpt-4o-mini"]
    with patch("chuzom.router.get_model_chain", return_value=list(base)), \
         patch("chuzom.router.get_dynamic_chain", return_value=None, create=True), \
         patch("chuzom.session_broker.broker_providers",
               new=AsyncMock(return_value=frozenset({"codex"}))):
        chain = await _build_and_filter_chain(
            TaskType.QUERY, RoutingProfile.BUDGET, None, "simple", Complexity.SIMPLE, _cfg()
        )
    assert chain
    # Codex may be injected (it's free), but the premium-only re-assert must NOT
    # fire for BUDGET, so the local model stays ahead of it.
    assert chain[0].startswith("ollama/"), \
        f"simple route must keep a local model first (cheap-first), got {chain[:3]}"


@pytest.mark.asyncio
async def test_no_broker_no_codex_front(mock_env, monkeypatch):
    """With no broker offering codex, the premium chain is not codex-fronted."""
    sb._provider_cache = None
    monkeypatch.setenv("CHUZOM_DISABLE_SUBPROCESS_BACKENDS", "codex,gemini_cli")
    with patch("chuzom.session_broker.broker_providers",
               new=AsyncMock(return_value=frozenset())):
        chain = await _build_and_filter_chain(
            TaskType.ANALYZE, RoutingProfile.PREMIUM, None, "complex", Complexity.COMPLEX, _cfg()
        )
    assert chain
    assert not chain[0].startswith("codex/"), \
        f"no broker → codex must not be fronted, got {chain[:3]}"
