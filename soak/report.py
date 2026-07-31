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

Phase 0.2 FIX A: a single replay run is NOT run-to-run reproducible --
headline point estimates swing materially between invocations despite the
seeded RNG in ``soak/replay.py`` (see ``NONDETERMINISM_NOTE`` below for what
was ruled in/out chasing the exact source). Quoting one run's point figure
as precise is false precision. ``run_soak_n`` runs the full pipeline
``n_soak_runs`` independent times and aggregates into a stable, honestly
labeled figure: ``point_median`` (the citeable number) and
``conservative_ci_lower`` (the minimum 95% CI lower bound observed across
all N runs -- the most defensible floor). ``savings_claim_supported`` is
derived from ``conservative_ci_lower`` across all N runs, never a single
run's CI. This is now what ``chuzom soak`` (the CLI) and the G7 gate use;
the single-run ``build_report``/``run_soak`` remain as the per-run building
block ``run_soak_n`` calls N times, and stay directly usable for anyone who
explicitly wants one hermetic pass.
"""

from __future__ import annotations

import json
import statistics
import tempfile
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

# Phase 0.2 FIX A: the G7 gate and the `chuzom soak` CLI both default to this
# many independent replay runs when aggregating a citeable headline figure.
DEFAULT_N_SOAK_RUNS = 11

# Phase 0.2 FIX B: honest disclosure of the non-determinism investigation.
# Multiple sessions of direct instrumentation ruled out several concrete
# hypotheses but did NOT fully isolate the root cause -- so this report
# relies on FIX A's median-of-N + conservative floor (MITIGATE) rather than
# a single deterministic run (PIN). See the brief's explicit allowance for
# this outcome ("If you CANNOT fully pin it after honest effort, document
# the identified source(s)... and rely on FIX A's median-of-N").
NONDETERMINISM_NOTE = (
    "Phase 0.2: a single soak run is not run-to-run reproducible despite the "
    "seeded RNG (random.Random(seed=0) in soak/replay.py). Ruled OUT as sole "
    "causes, via direct instrumentation of the real (non-mocked) route_and_call "
    "dispatch path: PYTHONHASHSEED / hash-ordering; correlation_id- or "
    "session_id-derived branching; the P2 quality-gated escalation path (its "
    "outer guard `attempt < len(models_to_try)` is always False against the "
    "soak's single-element mocked model chain, so it can never fire); OKF alone "
    "(A/B tested with CHUZOM_OKF=off, difference persisted); concurrent or "
    "out-of-order row dispatch (rows are replayed strictly sequentially); "
    "corpus row ordering (load_corpus reads deterministically); and -- "
    "decisively, via direct monkeypatching of chuzom.router._call_text and "
    "chuzom.router.run_gates -- a contract-gate failure triggering a same-model "
    "or emergency-fallback retry that re-invokes _call_text for the same row "
    "(measured: _call_text is invoked exactly once per row across all 40 rows "
    "in every run, even in runs where real, content-dependent gate failures "
    "occurred). Remaining, unconfirmed suspects: chuzom.quality_feedback's "
    "process-global _quality_store (confirmed written on every successful "
    "dispatch via record_quality/score_response in the P2 escalation-scoring "
    "code path, but not confirmed as the leak); and _spawn_bg/store_receipt "
    "background-task timing. Conclusion: MITIGATE, not PIN -- rely on "
    "point_median + conservative_ci_lower across n_soak_runs independent runs "
    "as the citeable figure, never a single run's point estimate."
)


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


def _aggregate_headline(
    per_run_reports: list[dict[str, Any]],
    bucket: str,
    host_mode: str,
    *,
    round_int: bool = False,
) -> dict[str, Any]:
    """Aggregate one headline metric (e.g. net_realized_savings_usd.metered)
    across N independent per-run report dicts into a stable, honestly-labeled
    figure: ``point_median`` (the citeable number -- median of the N per-run
    points), ``run_spread`` ([p10, p90] of the raw per-run points), and
    ``conservative_ci_lower`` (the MINIMUM 95% CI lower bound observed across
    all N runs -- the most defensible floor a re-audit can cite). The legacy
    ``point``/``ci95`` keys are kept, populated from the same N-run aggregate
    (never a single run's noisy point), for any consumer still reading them.

    ``round_int``: True for the quota-tokens bucket (counts, not fractional
    dollars -- mirrors ``build_report``'s existing int-rounding of quota
    figures), False for the dollar bucket.
    """
    points = [r[bucket][host_mode]["point"] for r in per_run_reports]
    ci_los = [r[bucket][host_mode]["ci95"][0] for r in per_run_reports]
    ci_his = [r[bucket][host_mode]["ci95"][1] for r in per_run_reports]

    def _r(x: float) -> float:
        return round(x) if round_int else round(x, 6)

    point_median = _r(statistics.median(points))
    conservative_ci_lower = _r(min(ci_los))
    conservative_ci_upper = _r(max(ci_his))
    run_spread = [_r(_percentile(points, 10)), _r(_percentile(points, 90))]

    return {
        "point": point_median,
        "ci95": [conservative_ci_lower, conservative_ci_upper],
        "point_median": point_median,
        "run_spread": run_spread,
        "conservative_ci_lower": conservative_ci_lower,
    }


def _aggregate_secondary(
    report: dict[str, Any], per_run_reports: list[dict[str, Any]], key: str
) -> None:
    """Mutate ``report`` in place: replace the scalar secondary metric at
    ``key`` with the median across the N runs (still a float in [0, 1], so
    existing range assertions on this key keep working unchanged), add a
    ``f"{key}_spread"`` sibling field ([p10, p90] across runs), and record in
    ``report["variable_across_runs"]`` whether this metric was genuinely
    variable run-to-run (min != max across the N runs) -- so a metric that
    happens to be perfectly stable isn't dressed up with a misleading spread,
    and one that IS noisy is disclosed rather than hidden behind one point.
    """
    values = [r[key] for r in per_run_reports]
    median = round(statistics.median(values), 6)
    spread = [round(_percentile(values, 10), 6), round(_percentile(values, 90), 6)]
    report[key] = median
    report[f"{key}_spread"] = spread
    report["variable_across_runs"][key] = min(values) != max(values)


async def run_soak_n(
    *,
    n_runs: int = DEFAULT_N_SOAK_RUNS,
    corpus_path: Path | None = None,
    monkeypatch=None,
    use_gold_complexity: bool = True,
) -> dict[str, Any]:
    """Phase 0.2 FIX A: run the full hermetic replay+report pipeline
    ``n_runs`` independent times (each against its own fresh scratch ledger
    via a ``tempfile.TemporaryDirectory``, so no state leaks between runs)
    and aggregate the per-run reports into a single, honestly-labeled
    report. The citeable headline is ``point_median`` (median of the N point
    estimates) plus ``conservative_ci_lower`` (the minimum CI lower bound
    observed across all N runs -- the most defensible floor), never a single
    run's noisy point estimate. See ``NONDETERMINISM_NOTE`` for why a single
    run isn't reproducible despite the seeded RNG in ``soak/replay.py``, and
    what was ruled in/out chasing the root cause during the Phase 0.2 FIX B
    investigation.

    ``monkeypatch``, when provided (e.g. from a pytest fixture), is reused
    across all N runs -- it only patches process-global env vars/attributes,
    which is safe to share; each run still gets its own fresh ledger.
    """
    if n_runs < 1:
        raise ValueError(f"n_runs must be >= 1, got {n_runs}")

    per_run_reports: list[dict[str, Any]] = []
    for _ in range(n_runs):
        with tempfile.TemporaryDirectory(prefix="chuzom-soak-run-") as tmp:
            tmp_path = Path(tmp)
            ledger_path = tmp_path / "soak_ledger.db"
            routing_ledger_dir = tmp_path / "routing_ledger"
            routing_ledger_dir.mkdir(parents=True, exist_ok=True)
            run_report = await run_soak(
                corpus_path=corpus_path,
                ledger_path=ledger_path,
                routing_ledger_dir=routing_ledger_dir,
                monkeypatch=monkeypatch,
                use_gold_complexity=use_gold_complexity,
            )
            per_run_reports.append(run_report)

    base = per_run_reports[0]
    report: dict[str, Any] = {
        "corpus_version": base["corpus_version"],
        "n_routes": base["n_routes"],
        "host_mode_split": base["host_mode_split"],
        "net_realized_savings_usd": {
            "metered": _aggregate_headline(
                per_run_reports, "net_realized_savings_usd", "metered", round_int=False
            ),
        },
        "realized_quota_tokens_saved": {
            "subscription": _aggregate_headline(
                per_run_reports, "realized_quota_tokens_saved", "subscription", round_int=True
            ),
        },
        "effective_sample_size": base["effective_sample_size"],
        "variable_across_runs": {},
        "overhead_as_pct_of_gross": base["overhead_as_pct_of_gross"],
        "baseline_tokens_method": base["baseline_tokens_method"],
        "n_soak_runs": n_runs,
        "nondeterminism_note": NONDETERMINISM_NOTE,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chuzom_version": base["chuzom_version"],
        "price_table_version": base["price_table_version"],
    }

    # Secondary metrics: median stays in the original scalar key (still a
    # valid [0,1] rate for existing range assertions), plus a spread sibling
    # and a variable_across_runs flag -- honest disclosure without silently
    # presenting one noisy run's point as the whole story.
    for key in (
        "soak_dispatch_failure_rate",
        "quality_delta_p50",
        "quality_delta_p95",
        "gate_false_negative_rate",
        "adoption_unknown_fraction",
    ):
        _aggregate_secondary(report, per_run_reports, key)

    # Phase 0.1 FIX 3, extended to N runs: the exit gate must never assert a
    # saving on noise. Robust-across-N means the CI lower bound cleared 0 in
    # EVERY one of the N runs (conservative_ci_lower is the min across all of
    # them) -- a strictly stronger bar than any single run's CI.
    net_lower = report["net_realized_savings_usd"]["metered"]["conservative_ci_lower"]
    quota_lower = report["realized_quota_tokens_saved"]["subscription"]["conservative_ci_lower"]
    report["savings_claim_supported"] = bool(net_lower > 0 or quota_lower > 0)

    # Sanity guard: the corpus/host-mode split is a structural property of
    # the (deterministic) corpus + gold-complexity config, not something FIX
    # A expects to vary across runs. If it ever does, that's a NEW finding
    # worth flagging rather than silently averaging over.
    for r in per_run_reports[1:]:
        if r["n_routes"] != base["n_routes"] or r["host_mode_split"] != base["host_mode_split"]:
            report["nondeterminism_note"] += (
                " WARNING: structural fields (n_routes/host_mode_split) differed across "
                "runs in this report -- that is unexpected and was not previously "
                "observed; treat n_routes/host_mode_split above as from the first run "
                "only and investigate."
            )
            break

    return report


def write_report(report: dict[str, Any], path: Path | None = None) -> Path:
    out = path or DEFAULT_REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
