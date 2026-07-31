"""Phase 0 Step 7 -- assemble ``soak/report.json`` from a corpus replay.

Pulls the headline $/quota-token figures from
``chuzom.execution_ledger.get_period_accounting`` (the ONLY cost totals
surface per INV-COST-004), and computes the remaining report keys
(``soak_dispatch_failure_rate``, ``quality_delta_p50/p95``,
``gate_false_negative_rate``, ``adoption_unknown_fraction``,
``host_mode_split``) directly from the raw per-row ``RowResult`` list, since
those have no ``Accounting`` field -- they are soak-harness-level QA
metrics, not ledger accounting.

Phase 0.1 FIX 6: ``mis_route_rate`` was renamed to
``soak_dispatch_failure_rate`` -- the old name collided in meaning with
``chuzom.routing_quality``'s ``mis_route_rate_inferred`` (a *ledger-derived*
routing-quality signal computed from real production traffic), even though
this harness's figure is a much narrower thing: the fraction of corpus rows
where the mocked dispatch chain itself failed to produce an accepted route.
The rename makes clear this is a soak-harness dispatch-failure rate, not a
claim about routing quality in general.

Phase 0.1 FIX 3: ``savings_claim_supported`` is the exit-gate verdict --
True only if at least one headline metric's 95% CI LOWER BOUND clears 0.
Gating on the point estimate alone (the pre-Phase-0.1 behaviour) can "pass"
on pure noise when the CI straddles 0; this field makes that distinction
explicit and machine-checkable instead of silently asserting a saving the
data doesn't actually support. When False, treat the run as an
infrastructure smoke-test (the pipeline executed and the report schema is
complete) -- not as proof of a saving.

Phase 0.1 FIX 4d: ``overhead_as_pct_of_gross`` is ``null`` in this harness's
reports, not a fake ``0.0`` -- hook-token overhead is only ever populated by
the external Claude Code PreToolUse hook script, which the soak harness
never invokes (``route_and_call`` is driven directly). See the inline note
in ``build_report`` for the full reasoning.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from chuzom import __version__ as _chuzom_version
from chuzom.execution_ledger import get_period_accounting
from chuzom.router import _price_table_version

from soak.ci import bootstrap_ci
from soak.corpus_schema import load_corpus, validate_corpus
from soak.replay import EnvPatcher, ReplayRun, replay_corpus

DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "report.json"

# Phase 0.1: the subscription quota figure is no longer a baseline-minus-actual
# delta (see execution_ledger.py's _aggregate Gap-2 reframe) -- it's the sum of
# tokens actually served by a non-Claude model on a realized, adopted route.
BASELINE_TOKENS_METHOD = "claude_tokens_avoided"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    idx = pct / 100.0 * (len(s) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def build_report(run: ReplayRun) -> dict[str, Any]:
    """Pure function: ReplayRun -> report.json-shaped dict. No I/O."""
    results = run.results
    n_routes = len(results)

    host_mode_split: dict[str, int] = {}
    for r in results:
        host_mode_split[r.host_mode] = host_mode_split.get(r.host_mode, 0) + 1

    dispatch_failures = sum(1 for r in results if r.dispatch_failed)
    soak_dispatch_failure_rate = (dispatch_failures / n_routes) if n_routes else 0.0

    quality_deltas = [r.quality_delta for r in results if not r.dispatch_failed]
    quality_delta_p50 = round(_percentile(quality_deltas, 50), 6)
    quality_delta_p95 = round(_percentile(quality_deltas, 95), 6)

    gate_evaluable = [r for r in results if not r.dispatch_failed]
    gate_false_negative_rate = (
        sum(1 for r in gate_evaluable if r.gate_false_negative) / len(gate_evaluable)
        if gate_evaluable else 0.0
    )

    adoption_unknown_fraction = (
        sum(1 for r in results if r.realization_status == "unknown") / n_routes
        if n_routes else 0.0
    )

    period_acc = get_period_accounting(run.period_start_ts, run.period_end_ts, path=run.ledger_path)

    # Phase 0.1 FIX 4d: hook_input_tokens/hook_output_tokens (and therefore
    # overhead_as_pct_of_gross, which is derived from them by the ledger's
    # own _aggregate -- untouched here) are populated ONLY by the external
    # Claude Code PreToolUse hook script (chuzom/hooks/auto-route.py),
    # which the soak harness never invokes -- route_and_call is called
    # directly, bypassing that hook entirely. That means this figure isn't
    # "measured and found to be zero overhead"; it structurally CANNOT be
    # anything but 0 in this hermetic harness, because the code path that
    # would populate it never runs. Reporting 0.0 here would silently imply
    # a real measurement ("we checked, there's no overhead") when the truth
    # is "we never checked" -- exactly the fake-0 pattern the brief calls
    # out. Report null/not-measured instead, unless a future harness change
    # actually starts exercising that code path (the `> 0` guard below then
    # falls through to the ledger's real computed value).
    overhead_measured = bool(period_acc.hook_input_tokens or period_acc.hook_output_tokens)
    overhead_as_pct_of_gross = (
        period_acc.overhead_as_pct_of_gross if overhead_measured else None
    )

    metered_net_values = [r.net_realized_savings_usd for r in results if r.host_mode == "metered"]
    subscription_quota_values = [
        float(r.realized_quota_tokens_saved) for r in results if r.host_mode == "subscription"
    ]

    # Phase 0.1 FIX 6: how many data points actually fed each headline CI --
    # a CI computed from a handful of rows deserves less trust than one from
    # dozens, and this makes that visible instead of implying uniform
    # confidence across both host modes' figures.
    effective_sample_size = {
        "metered": len(metered_net_values),
        "subscription": len(subscription_quota_values),
    }

    net_metered_ci = bootstrap_ci(metered_net_values)
    quota_subscription_ci = bootstrap_ci(subscription_quota_values)
    # Quota tokens are counts, not fractional dollars -- round the CI/point
    # back to ints for readability without losing the underlying float math.
    quota_subscription_ci = {
        "point": round(quota_subscription_ci["point"]),
        "ci95": [round(quota_subscription_ci["ci95"][0]), round(quota_subscription_ci["ci95"][1])],
    }

    # Phase 0.1 FIX 3: the exit gate must never assert a saving on a point
    # estimate whose confidence interval includes 0 -- that's noise, not a
    # proven number (the "North Star" failure mode this fixes). A headline
    # metric is only defensible if its 95% CI LOWER BOUND clears 0. If
    # neither metric clears it, the honest thing to report is that this run
    # is an infrastructure smoke-test (pipeline ran, schema is complete) and
    # NOT a proof of savings -- never silently pass on noise.
    subscription_ci_lower = quota_subscription_ci["ci95"][0]
    metered_ci_lower = net_metered_ci["ci95"][0]
    savings_claim_supported = subscription_ci_lower > 0 or metered_ci_lower > 0

    return {
        "corpus_version": run.corpus_version,
        "n_routes": n_routes,
        "host_mode_split": host_mode_split,
        "net_realized_savings_usd": {"metered": net_metered_ci},
        "realized_quota_tokens_saved": {"subscription": quota_subscription_ci},
        "effective_sample_size": effective_sample_size,
        "soak_dispatch_failure_rate": round(soak_dispatch_failure_rate, 6),
        "quality_delta_p50": quality_delta_p50,
        "quality_delta_p95": quality_delta_p95,
        "gate_false_negative_rate": round(gate_false_negative_rate, 6),
        "adoption_unknown_fraction": round(adoption_unknown_fraction, 6),
        "overhead_as_pct_of_gross": overhead_as_pct_of_gross,
        "baseline_tokens_method": BASELINE_TOKENS_METHOD,
        "savings_claim_supported": savings_claim_supported,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chuzom_version": _chuzom_version,
        "price_table_version": _price_table_version(),
    }


async def run_soak(
    *,
    corpus_path: Path | None = None,
    ledger_path: Path,
    routing_ledger_dir: Path,
    monkeypatch=None,
    use_gold_complexity: bool = True,
) -> dict[str, Any]:
    """End-to-end: load + validate corpus, replay it, build the report dict.
    Does NOT write to disk -- callers (the CLI, the pytest gate) decide that.

    ``monkeypatch``: pass pytest's fixture from a test. Omit it (the CLI path,
    Step 8) and an internal ``soak.replay.EnvPatcher`` is used and restored
    automatically -- it exposes the same ``setenv``/``delenv`` surface.
    """
    rows = load_corpus(corpus_path)
    errors = validate_corpus(rows)
    if errors:
        raise ValueError(f"corpus failed validation, refusing to soak: {errors}")

    owns_patcher = monkeypatch is None
    patcher = monkeypatch or EnvPatcher()
    try:
        run = await replay_corpus(
            rows,
            ledger_path=ledger_path,
            routing_ledger_dir=routing_ledger_dir,
            monkeypatch=patcher,
            use_gold_complexity=use_gold_complexity,
        )
        return build_report(run)
    finally:
        if owns_patcher:
            patcher.undo()


def write_report(report: dict[str, Any], path: Path | None = None) -> Path:
    out = path or DEFAULT_REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
