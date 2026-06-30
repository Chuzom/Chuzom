"""P2 #6: session summary reports NET savings (baseline − actual), not notional.

A wasteful paid draft can make a session a net loss; the summary must show that
in the red, not bury it behind a notional free-tier "saved" figure.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "src" / "chuzom" / "hooks" / "session-end.py"


def _load():
    cached = sys.modules.get("session_end_net_test")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location("session_end_net_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    sys.modules["session_end_net_test"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def se():
    return _load()


def _strip(s: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", s or "")


def test_net_positive_reports_saved(se):
    free = [{"input_tokens": 2000, "output_tokens": 1000, "cost_usd": 0.0}]
    line = _strip(se._net_session_line(free, []))
    assert "Net saved" in line
    assert "baseline" in line and "paid" in line


def test_net_negative_reports_loss_not_hidden(se):
    # The user's case: a $0.10 paid draft on tiny work → net loss.
    free = [{"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.0}]
    paid = [{"input_tokens": 1500, "output_tokens": 0, "cost_usd": 0.10}]
    line = _strip(se._net_session_line(free, paid))
    assert "NET LOSS" in line
    assert "-$0.07" in line  # negative, not clamped to 0
    assert "wasteful paid routing" in line


def test_net_subtracts_actual_paid_across_tiers(se):
    free = [{"input_tokens": 10000, "output_tokens": 5000, "cost_usd": 0.0}]
    paid = [{"input_tokens": 1000, "output_tokens": 500, "cost_usd": 0.02}]
    line = _strip(se._net_session_line(free, paid))
    # baseline includes BOTH tiers' tokens; actual subtracts only paid cost.
    assert "Net saved" in line
    # baseline for 11k in + 5.5k out at $15/$75 per-M ≈ 0.165+0.4125 = ~0.578; net ≈ 0.558
    assert "$0.5" in line


def test_net_line_none_when_no_rows(se):
    assert se._net_session_line([], []) is None
