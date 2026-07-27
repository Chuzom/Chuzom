"""#5 / Gates 15-17 — the control-group savings verdict, on synthetic paired rows.

No API calls: these lock the *analysis*, so that once a real run produces rows the
gate judgements are honest and reproducible. The sign of the real result is
empirical and NOT asserted here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from bench.routers import claude_host_router, control_group_routers
from bench.savings import evaluate_savings


@dataclass(frozen=True)
class Row:
    """Minimal RunRow-compatible record for the analysis under test."""
    corpus_id: str
    router_name: str
    model_chosen: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    judge_score: int
    notes: dict = field(default_factory=dict)


def _pair(cid, *, host_cost, chuzom_cost, host_model="anthropic/claude-host",
          chuzom_model="ollama/qwen3.5:latest", host_q=5, chuzom_q=5,
          chuzom_notes=None):
    return [
        Row(cid, "always-claude-host", host_model, 100, 100, host_cost, host_q),
        Row(cid, "chuzom", chuzom_model, 100, 100, chuzom_cost, chuzom_q,
            notes=chuzom_notes or {}),
    ]


def test_positive_net_savings_and_non_inferior_quality_passes_all_gates():
    rows = []
    for i in range(5):
        rows += _pair(f"p{i}", host_cost=0.05, chuzom_cost=0.0)  # host pays, chuzom free
    v = evaluate_savings(rows)
    assert v.net_savings_usd == pytest.approx(0.25)
    assert v.gate15_positive_net_savings
    assert v.gate16_quality_non_inferior  # equal quality
    assert v.gate17_no_unclassified_spend
    assert v.all_gates_pass
    # Pin every reported field — these feed the human-readable verdict and must
    # not silently go wrong (each Row is 100↑/100↓ tokens).
    assert v.n_prompts == 5
    assert v.control_cost_usd == pytest.approx(0.25)
    assert v.chuzom_cost_usd == pytest.approx(0.0)
    assert v.control_tokens == 1000 and v.chuzom_tokens == 1000
    assert v.control_quality == pytest.approx(5.0)
    assert v.chuzom_quality == pytest.approx(5.0)


def test_failure_and_exhausted_rows_are_not_unclassified_spend():
    """A router that failed / exhausted its chain carries no spend to classify —
    model_chosen '' or '<exhausted>' at $0 must NOT count as unclassified (Gate 17)."""
    rows = _pair("p0", host_cost=0.05, chuzom_cost=0.0, chuzom_model="<exhausted>")
    rows += _pair("p1", host_cost=0.05, chuzom_cost=0.0, chuzom_model="")
    v = evaluate_savings(rows)
    assert v.unclassified_events == []
    assert v.gate17_no_unclassified_spend


def test_default_non_inferiority_margin_bites():
    """With the DEFAULT margin (0.5), a 1.0-point quality drop must fail Gate 16 —
    pins the default so it can't be loosened silently."""
    rows = _pair("p0", host_cost=0.05, chuzom_cost=0.0, host_q=5, chuzom_q=4)  # delta −1.0
    v = evaluate_savings(rows)  # no margin arg → default 0.5
    assert v.non_inferiority_margin == 0.5
    assert v.quality_delta == pytest.approx(-1.0)
    assert not v.gate16_quality_non_inferior


def test_missing_chuzom_arm_raises():
    rows = [Row("p0", "always-claude-host", "anthropic/claude-host", 10, 10, 0.05, 5)]
    with pytest.raises(ValueError, match="Chuzom arm"):
        evaluate_savings(rows)


def test_routing_overhead_is_netted_out_of_savings():
    rows = _pair("p0", host_cost=0.05, chuzom_cost=0.01,
                 chuzom_notes={"routing_overhead_usd": 0.005})
    v = evaluate_savings(rows)
    # net = host(0.05) − chuzom(0.01) − overhead(0.005) = 0.035
    assert v.routing_overhead_usd == pytest.approx(0.005)
    assert v.net_savings_usd == pytest.approx(0.035)


def test_non_numeric_overhead_is_treated_as_zero_not_crashed():
    """A garbage routing_overhead_usd must degrade to $0 (honest, never fabricated
    or exploding) — pins the except path."""
    rows = _pair("p0", host_cost=0.05, chuzom_cost=0.01,
                 chuzom_notes={"routing_overhead_usd": "not-a-number"})
    v = evaluate_savings(rows)
    assert v.routing_overhead_usd == pytest.approx(0.0)
    assert v.net_savings_usd == pytest.approx(0.04)


def test_negative_savings_fails_gate15_honestly():
    # Chuzom more expensive than the host baseline → Gate 15 must FAIL, not be masked.
    rows = _pair("p0", host_cost=0.01, chuzom_cost=0.05)
    v = evaluate_savings(rows)
    assert v.net_savings_usd < 0
    assert not v.gate15_positive_net_savings
    assert not v.all_gates_pass


def test_quality_regression_beyond_margin_fails_gate16():
    rows = _pair("p0", host_cost=0.05, chuzom_cost=0.0, host_q=5, chuzom_q=3)
    v = evaluate_savings(rows, non_inferiority_margin=0.5)
    assert v.quality_delta == pytest.approx(-2.0)
    assert not v.gate16_quality_non_inferior


def test_quality_within_margin_passes_gate16():
    rows = _pair("p0", host_cost=0.05, chuzom_cost=0.0, host_q=5, chuzom_q=5)
    rows += _pair("p1", host_cost=0.05, chuzom_cost=0.0, host_q=5, chuzom_q=4)
    v = evaluate_savings(rows, non_inferiority_margin=0.5)
    # mean host 5.0 vs mean chuzom 4.5 → delta −0.5, exactly at the margin → passes
    assert v.quality_delta == pytest.approx(-0.5)
    assert v.gate16_quality_non_inferior


def test_paid_model_priced_zero_is_unclassified_spend_gate17():
    # A non-free model reported at $0 → price unknown → unclassified spend.
    rows = _pair("p0", host_cost=0.05, chuzom_cost=0.0,
                 chuzom_model="openai/gpt-4o")  # paid model, cost 0.0
    v = evaluate_savings(rows)
    assert v.unclassified_events == ["p0"]
    assert not v.gate17_no_unclassified_spend


def test_local_model_zero_cost_is_classified_not_unclassified():
    rows = _pair("p0", host_cost=0.05, chuzom_cost=0.0,
                 chuzom_model="ollama/qwen3.5:latest")
    v = evaluate_savings(rows)
    assert v.unclassified_events == []
    assert v.gate17_no_unclassified_spend


def test_unpaired_arms_raise():
    rows = [
        Row("p0", "chuzom", "ollama/x", 10, 10, 0.0, 5),
        Row("p1", "always-claude-host", "anthropic/claude-host", 10, 10, 0.05, 5),
    ]
    with pytest.raises(ValueError, match="unpaired") as exc:
        evaluate_savings(rows)
    # The message must name the actually-differing prompts (symmetric difference),
    # so the failure is diagnosable — not a bare "unpaired".
    assert "p0" in str(exc.value) and "p1" in str(exc.value)


def test_missing_control_arm_raises():
    rows = [Row("p0", "chuzom", "ollama/x", 10, 10, 0.0, 5)]
    with pytest.raises(ValueError, match="control arm"):
        evaluate_savings(rows)


def test_control_group_lineup_is_chuzom_plus_host():
    names = {r.name for r in control_group_routers()}
    assert names == {"chuzom", "always-claude-host"}
    assert claude_host_router().model == "anthropic/claude-host"
