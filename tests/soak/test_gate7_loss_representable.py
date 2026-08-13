"""WP-16 item 1 — Gate 7 must assert that a LOSS survives every layer.

Gate 7's stated bar is "a defensible number exists". **A clamped zero is a
number, and it is defensible-looking.** That is how Gate 7 certified a release
carrying AUD-06 — the `max(0.0, total_base - total_cost)` clamp that rendered
overspend as "$0.00 saved". The gate asked whether a figure was produced, never
whether an unfavourable figure could survive being produced.

So the plan's WP-16 scope item 1: *"Gate 7 must now assert that a loss can be
represented and displayed."*

WHAT THIS FILE ASSERTS, AND WHY EACH LAYER SEPARATELY
-----------------------------------------------------
A loss has to survive a chain, and a clamp anywhere in it hides the loss just as
completely as a clamp at the source. `tests/economics/test_savings_sign.py` (WP-04,
immutable) pins the SOURCE arithmetic. This pins the rest of the chain — the
statistics layer, the cross-run aggregator, the report label, and the display —
because a signed subtraction feeding a clamped mean is still a lie to the user.

NOT A DUPLICATE of test_savings_sign.py: that asserts session-end's total is
signed. These assert that a negative, once produced, is not laundered into zero
by the bootstrap, the aggregator, the `savings_claim_supported` label, or the
printer.

VERIFIED TO FIRE, NOT ASSUMED. There is no clamp in this chain today, so every
assertion below passes on first write — which is exactly the state a
can't-fail test is born in. Each was checked by injecting a `max(0.0, ...)`
clamp at the layer it covers and confirming it fails; see
`evidence/wp16_gate7_loss.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from soak.ci import bootstrap_ci  # noqa: E402
from soak.report import _aggregate_headline  # noqa: E402


# ── layer 1: the statistics ──────────────────────────────────────────────────

def test_bootstrap_ci_reports_a_negative_point():
    """A period that spent more than it saved must survive the CI layer.

    If the bootstrap clamped, every downstream figure would read as break-even
    and the gate could not tell a loss from a no-op.
    """
    losses = [-0.004, -0.002, -0.006, -0.003, -0.005]
    ci = bootstrap_ci(losses)
    assert ci["point"] < 0, f"a period of pure losses reported point={ci['point']}"
    assert ci["ci95"][1] < 0, (
        f"the CI upper bound is {ci['ci95'][1]} — a confidence interval that "
        "reaches 0 or above on all-negative data has been clamped"
    )


def test_bootstrap_ci_preserves_a_mixed_period_that_nets_negative():
    """The realistic shape: some routes save, overhead swamps them. The sign of
    the TOTAL is the user-facing fact, and it must not be lost to the mixture."""
    mixed = [0.001, -0.010, 0.002, -0.008, 0.001]
    ci = bootstrap_ci(mixed)
    assert ci["point"] < 0, (
        f"net of a mixed period that loses money reported {ci['point']}"
    )


# ── layer 2: the cross-run aggregator ────────────────────────────────────────

def _run(point: float, lo: float, hi: float) -> dict:
    return {"net_realized_savings_usd": {"metered": {"point": point, "ci95": [lo, hi]}}}


def test_cross_run_aggregation_keeps_the_loss():
    """N independent soak runs that all lose money must aggregate to a loss.

    `conservative_ci_lower` is the gate's own worst-case term. If the aggregator
    floored it at 0, the WORST case would read as break-even — the one direction
    a conservative bound must never round toward.
    """
    runs = [_run(-0.005, -0.008, -0.002), _run(-0.004, -0.007, -0.001),
            _run(-0.006, -0.009, -0.003)]
    agg = _aggregate_headline(runs, "net_realized_savings_usd", "metered", round_int=False)

    assert agg["point_median"] < 0, f"median across losing runs: {agg['point_median']}"
    assert agg["conservative_ci_lower"] < 0, (
        f"conservative_ci_lower={agg['conservative_ci_lower']} — the worst-case "
        "bound of three losing runs cannot be >= 0"
    )
    assert agg["run_spread"][0] < 0


def test_aggregation_does_not_round_a_small_loss_to_zero():
    """Sub-cent losses are the ones a clamp or a round() eats silently, and
    routing losses are sub-cent by nature. -0.0001 must not become 0.0."""
    runs = [_run(-0.0001, -0.0002, -0.00005)] * 3
    agg = _aggregate_headline(runs, "net_realized_savings_usd", "metered", round_int=False)
    assert agg["point_median"] < 0, (
        f"a sub-cent loss rounded to {agg['point_median']} — at this magnitude "
        "the sign IS the finding"
    )


# ── layer 3: the label ───────────────────────────────────────────────────────

def test_the_label_rule_is_a_strict_positive_on_the_conservative_bound():
    """`savings_claim_supported` is what a reader trusts, and the gate's failure
    mode was never a wrong number — it was a favourable LABEL on an unfavourable
    one.

    SOURCE-LEVEL, and that is a real limitation worth stating: the rule lives
    inline inside the async `run_soak_n`, which runs the whole replay pipeline,
    so it cannot be called in isolation. The alternative was to re-implement the
    comparison in the test and assert on my own copy — which would exercise no
    production code at all and pass forever regardless of what ships. Reading the
    shipped expression is weaker than calling it, and stronger than testing a
    duplicate of it.
    """
    src = (_ROOT / "soak" / "report.py").read_text()
    assert 'report["savings_claim_supported"] = bool(net_lower > 0 or quota_lower > 0)' in src, (
        "the savings_claim_supported rule changed. It must stay a STRICT `> 0` on "
        "the conservative (worst-of-N) CI lower bound: `>= 0` would label a "
        "break-even period a supported saving, and any clamp on the bound would "
        "label a loss as one"
    )
    assert 'conservative_ci_lower"]' in src


# ── layer 4: the display ─────────────────────────────────────────────────────

def test_the_printer_emits_the_raw_signed_value():
    """The last place a loss can vanish is formatting. A figure that is negative
    in JSON and renders as "0.00" to the operator has still hidden the loss —
    RED2-02's "$0.00 saved" was a display-layer failure, not an arithmetic one.

    Source-level for the same reason as above (the print block sits inside a
    command that runs the soak), and with the same trade-off: this checks what
    actually ships rather than a copy of it.
    """
    src = (_ROOT / "src" / "chuzom" / "commands" / "soak.py").read_text()
    start = src.index("net_realized_savings_usd.metered.point_median")
    block = src[start:start + 300]
    assert "{net_agg['point_median']}" in block, (
        "the printer no longer interpolates point_median directly"
    )
    for hider in ("max(0", "abs(", ":.0f"):
        assert hider not in block, (
            f"the printed net figure passes through {hider!r} — a loss would be "
            "shown to the operator as break-even"
        )


# ── the guard's own guard ────────────────────────────────────────────────────

def test_the_aggregator_under_test_is_the_real_one():
    """Guards the guard. If `_aggregate_headline` were renamed or re-exported as
    a stub, the assertions above would exercise nothing while still passing.
    Import failure alone is not enough — a shim that returns its input would
    satisfy every test in this file."""
    runs = [_run(1.0, 0.5, 1.5), _run(3.0, 2.5, 3.5)]
    agg = _aggregate_headline(runs, "net_realized_savings_usd", "metered", round_int=False)
    assert agg["point_median"] == 2.0, (
        f"expected the median of [1.0, 3.0]; got {agg['point_median']} — this is "
        "not the real aggregator"
    )
    assert agg["conservative_ci_lower"] == 0.5, (
        "conservative_ci_lower must be the MINIMUM lower bound across runs"
    )
