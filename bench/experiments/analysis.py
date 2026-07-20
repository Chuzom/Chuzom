"""E-3 / E-4 / E-5 — reconciliation, counterfactual, and property checks.

All pure/offline. Baselines use the SAME latest-Opus price as production
(cost._OPUS_PRICING) so the recompute is a genuine cross-check of the aggregate,
not a second hand-tuned number.
"""
from __future__ import annotations

from dataclasses import dataclass

_EPS = 1e-6

_FREE = {"ollama", "codex", "gemini_cli"}


def _opus_rates() -> tuple[float, float]:
    from chuzom import cost

    return cost._OPUS_PRICING[cost.LATEST_OPUS_MODEL]


def opus_baseline(input_tokens: int, output_tokens: int) -> float:
    in_pm, out_pm = _opus_rates()
    return (input_tokens * in_pm + output_tokens * out_pm) / 1_000_000


def recompute_baseline_avoided(trace: list[dict]) -> float:
    """Independent recompute of baseline-avoided straight from the cassette.

    Mirrors cost.get_savings_by_period's per-row logic so that matching the
    production aggregate proves the number is reproducible from raw turns —
    the executable replacement for the retro's contradictory hand-math.
    """
    total = 0.0
    for t in trace:
        if t.get("route") == "host":
            continue  # DIRECT SKIP — no external call, nothing saved
        base = opus_baseline(int(t["input_tokens"]), int(t["output_tokens"]))
        if t["provider"] in _FREE:
            total += base
        else:
            total += max(0.0, base - float(t["cost_usd"]))
    return round(total, 4)


# ── E-3 reconciliation ──────────────────────────────────────────────────────

def check_reconciliation(measured: dict, trace: list[dict]) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    periods = measured["periods"]

    # (a) baseline_avoided aliases the legacy saved_usd in every window.
    ok = all(abs(b["baseline_avoided_usd"] - b["saved_usd"]) < _EPS for b in periods.values())
    out.append(("baseline_avoided == saved_usd (all windows)", ok, ""))

    # (b) production all-time aggregate == independent recompute from the trace.
    recomputed = recompute_baseline_avoided(trace)
    prod = periods["all_time"]["baseline_avoided_usd"]
    ok = abs(prod - recomputed) < 1e-3
    out.append(("aggregate reproducible from cassette",
                ok, f"prod=${prod:.4f} recompute=${recomputed:.4f}"))

    # (c) real dollars never exceed baseline-avoided.
    ok = all(b["real_dollars_avoided_usd"] <= b["baseline_avoided_usd"] + _EPS
             for b in periods.values())
    out.append(("real_$ <= baseline_avoided", ok, ""))
    return out


# ── E-5 properties ──────────────────────────────────────────────────────────

def check_window_nesting(measured: dict) -> tuple[str, bool, str]:
    p = measured["periods"]
    t = p["today"]["baseline_avoided_usd"]
    w = p["week"]["baseline_avoided_usd"]
    m = p["month"]["baseline_avoided_usd"]
    a = p["all_time"]["baseline_avoided_usd"]
    ok = t <= w + _EPS <= m + 2 * _EPS and m <= a + _EPS
    return ("window nesting today<=week<=month<=all", ok, f"{t:.3f}<={w:.3f}<={m:.3f}<={a:.3f}")


def check_real_zero_on_subscription(measured_sub: dict) -> tuple[str, bool, str]:
    ok = measured_sub["real_dollars_avoided_usd"] == 0.0 or measured_sub["routed"] == 0
    return ("real_$ == 0 on flat-rate subscription", ok,
            f"real=${measured_sub['real_dollars_avoided_usd']:.4f}")


# ── E-4 counterfactual dollar model ─────────────────────────────────────────

@dataclass(frozen=True)
class Counterfactual:
    baseline_avoided_usd: float   # Opus-baseline vs actual (quota/token figure)
    real_subscription_usd: float  # dollars actually avoided on a flat-rate sub
    real_metered_usd: float       # dollars avoided if the host were metered API


def counterfactual(trace: list[dict], *, cap_headroom_usd: float) -> Counterfactual:
    """Model real dollars avoided by routing, under different quota states.

    - subscription, under cap  -> $0 real (the host call was marginal-$0): M-3.
    - subscription, over cap    -> only the over-cap overage is real dollars.
    - metered API               -> the full baseline is real dollars.

    ``cap_headroom_usd`` is remaining flat-rate headroom expressed in
    host-equivalent dollars. Infinite/large headroom => unpressured => $0 real.
    """
    baseline = recompute_baseline_avoided(trace)
    real_metered = baseline
    real_subscription = max(0.0, baseline - cap_headroom_usd)
    return Counterfactual(
        baseline_avoided_usd=round(baseline, 4),
        real_subscription_usd=round(real_subscription, 4),
        real_metered_usd=round(real_metered, 4),
    )
