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
    """SIMPLE/BUDGET must stay free-local even when the broker offers codex
    (the re-assert is premium-only, preserving cheap-first)."""
    sb._provider_cache = None
    monkeypatch.setenv("CHUZOM_DISABLE_SUBPROCESS_BACKENDS", "codex,gemini_cli")
    with patch("chuzom.session_broker.broker_providers",
               new=AsyncMock(return_value=frozenset({"codex"}))):
        chain = await _build_and_filter_chain(
            TaskType.QUERY, RoutingProfile.BUDGET, None, "simple", Complexity.SIMPLE, _cfg()
        )
    assert chain
    assert not chain[0].startswith("codex/"), \
        f"simple route must not front codex (cheap-first), got {chain[:3]}"


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
