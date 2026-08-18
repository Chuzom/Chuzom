"""#26 — a benchmark run where nothing succeeded must not render as a result.

An invocation truncated by piping to `head` killed stdout and failed ALL 24
prompts with `BrokenPipeError`. The report still contained a full scorecard, a
Pareto frontier with a green tick, "Cost savings vs baseline: 0%" and
**"Quality delta: +0.00"**. The only hint was `Success 0/24` in one column, and
`router error: BrokenPipeError` far below the headline.

**A run in which nothing succeeded produced a quality score and a savings
figure.** That is the same defect this audit found in RED2-02 (a failed ledger
read rendering as "$0.00 saved") and AUD-06 (a loss rendering as break-even) —
here in the benchmark harness, which is the instrument release Gates 15 and 16
depend on.

The data was never missing: `RouterScorecard` already carries
`prompts_succeeded` and `prompts_attempted`. The reporter simply did not act on
them, so an average over zero successes was printed as though it were measured.

A partial run is the milder case and is covered too: `always-cheap` succeeded
9/24 in the real held-out run, and its 2.42 average was printed on the headline
row with nothing marking it as covering only the successful subset.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bench.reporter import render_report  # noqa: E402
from bench.runner import RouterScorecard  # noqa: E402


def _card(name: str, *, attempted: int, succeeded: int, q: float, cost: float) -> RouterScorecard:
    return RouterScorecard(
        router_name=name,
        prompts_attempted=attempted,
        prompts_succeeded=succeeded,
        avg_input_tokens=0.0,
        avg_output_tokens=0.0,
        avg_total_tokens=0.0,
        total_cost_usd=cost * attempted,
        avg_cost_usd=cost,
        avg_latency_ms=1.0,
        avg_judge_score=q,
        quality_preserved_pct=0.0,
    )


def test_a_total_failure_is_not_reported_as_a_quality_score():
    """The exact shape of the broken-pipe run: 0 of 24 succeeded."""
    md = render_report([], [_card("chuzom", attempted=24, succeeded=0, q=1.00, cost=0.0)])
    assert "no successful" in md.lower() or "NO DATA" in md, (
        "a router that answered nothing still renders as a measured quality "
        f"score; report said:\n{md[:600]}"
    )


def test_a_zero_success_router_is_not_on_the_pareto_frontier():
    """A router that answered nothing is not 'worth picking from'. Marking it
    with the frontier tick is an active recommendation built on no data."""
    md = render_report([], [
        _card("chuzom", attempted=24, succeeded=0, q=1.00, cost=0.0),
        _card("always-premium", attempted=24, succeeded=24, q=4.50, cost=0.0008),
    ])
    frontier_block = md.split("## 2")[1].split("## 3")[0] if "## 2" in md else md
    ticked = [ln for ln in frontier_block.splitlines() if ln.strip().startswith("✅")]
    assert not any("chuzom" in ln for ln in ticked), (
        f"a 0-success router carries the frontier tick:\n{frontier_block}"
    )


def test_a_partial_run_marks_its_aggregate():
    """always-cheap succeeded 9/24 in the real held-out run and its 2.42 average
    was printed unmarked. An average over the surviving subset is a different
    quantity from an average over the corpus."""
    md = render_report([], [
        _card("always-cheap", attempted=24, succeeded=9, q=2.42, cost=0.0),
        _card("always-premium", attempted=24, succeeded=24, q=4.50, cost=0.0008),
    ])
    assert "partial" in md.lower(), (
        f"a 9/24 run's average is presented like a complete one:\n{md[:600]}"
    )


def test_a_complete_run_is_unchanged():
    """The guard must not clutter an ordinary healthy report, or it gets removed."""
    md = render_report([], [
        _card("chuzom", attempted=24, succeeded=24, q=4.17, cost=0.00003),
        _card("always-premium", attempted=24, succeeded=24, q=4.50, cost=0.0008),
    ])
    assert "no successful" not in md.lower()
    assert "partial" not in md.lower()
    assert "4.17" in md and "4.50" in md


def test_the_savings_section_refuses_a_run_with_no_successes():
    """The single most misleading line in the broken-pipe report.

    Found by REPLAYING THE REAL ARTEFACT after the scorecard/frontier fix: the
    scorecard correctly said "no successful runs" while section 3 still printed
    "Quality delta: +0.00" and named a champion. My synthetic tests above did
    not cover it — the fix looked complete and was not.
    """
    md = render_report([], [
        _card("chuzom", attempted=24, succeeded=0, q=1.00, cost=0.0),
        _card("always-premium", attempted=24, succeeded=0, q=1.00, cost=0.0),
    ])
    sec = md.split("## 3")[1].split("## 4")[0] if "## 3" in md else ""
    assert "Quality delta" not in sec, (
        f"a savings figure is reported for a run where nothing succeeded:\n{sec}"
    )
    assert "no successful" in sec.lower(), f"section 3 does not say why it is empty:\n{sec}"


def test_the_failed_run_report_still_contains_the_per_prompt_detail():
    """The guard must not delete the evidence it points at.

    The first version of the savings guard used an early `return`, which dropped
    sections 4 and 5 — including the per-prompt detail its own message tells the
    reader to consult. Every test above still passed, because they only checked
    section 3's CONTENT. Caught by replaying the real artefact and listing the
    sections.
    """
    md = render_report([], [_card("chuzom", attempted=24, succeeded=0, q=1.0, cost=0.0)])
    heads = [ln for ln in md.splitlines() if ln.startswith("## ")]
    assert any("Per-prompt detail" in h for h in heads), (
        f"the failed-run report has no per-prompt detail section: {heads}"
    )
