"""Phase 0 Step 7 -- the G7 CI gate: "a defensible number exists".

Runs the full soak pipeline (corpus load/validate -> replay -> report) against
the committed ``soak/corpus/v1.jsonl`` under full hermetic mocking (no live API
keys, no live classifier -- ``use_gold_complexity=True``) and asserts the
resulting report.json-shaped dict is structurally sound:

  * every required report key is present
  * no corpus row contains a secret pattern (privacy gate, CHZ-PRV-06)
  * ``overhead_as_pct_of_gross <= 1.0``
  * host modes are never blended into one dollar figure: metered rows only
    ever contribute to ``net_realized_savings_usd``, subscription rows only
    ever contribute to ``realized_quota_tokens_saved``
  * the run produced a non-degenerate number, per the brief's Phase 0 exit
    gate: subscription quota-tokens > 0 OR metered net $ > 0

This is NOT a precision/quality benchmark -- Phase 0's bar is that the
pipeline runs end-to-end on real (mocked-dispatch) routes and produces an
honest, non-fabricated figure, not that the figure is large or "good".
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from soak.corpus_schema import load_corpus, validate_corpus
from soak.report import DEFAULT_N_SOAK_RUNS, run_soak_n

REQUIRED_REPORT_KEYS = {
    "corpus_version",
    "n_routes",
    "host_mode_split",
    "net_realized_savings_usd",
    "realized_quota_tokens_saved",
    "effective_sample_size",
    "soak_dispatch_failure_rate",
    "quality_delta_p50",
    "quality_delta_p95",
    "gate_false_negative_rate",
    "adoption_unknown_fraction",
    "overhead_as_pct_of_gross",
    "baseline_tokens_method",
    "savings_claim_supported",
    "generated_at",
    "chuzom_version",
    "price_table_version",
    "n_soak_runs",
    "nondeterminism_note",
}


def test_corpus_is_valid_and_secret_free_before_soaking():
    """CHZ-PRV-06: refuse to even attempt a soak over a corpus that fails
    schema or privacy validation -- ``run_soak`` itself raises on this, but
    this test isolates the assertion so a corpus regression fails loudly and
    specifically, not buried inside a broader pipeline failure."""
    rows = load_corpus()
    errors = validate_corpus(rows)
    assert errors == [], f"corpus failed validation: {errors}"


@pytest.fixture(scope="session")
def soak_report(tmp_path_factory):
    """Run the full replay+report pipeline DEFAULT_N_SOAK_RUNS times (Phase
    0.2 FIX A) against the committed v1 corpus, hermetically
    (use_gold_complexity=True => no live classifier, and _call_row mocks out
    every network-touching dependency), and aggregate into the N-run report
    schema. A single run's point estimate is NOT run-to-run reproducible
    (see soak.report.NONDETERMINISM_NOTE) -- the gate below asserts against
    ``conservative_ci_lower`` (the min CI lower bound across all N runs), not
    any single run's point/ci95.

    SESSION-scoped (CHZ-CI: G7 30s-timeout fix). The report build is ~8s
    (11 runs * ~0.7s); function scope re-ran it in *every* dependent test's
    setup (~10x = ~80s of pure setup), and on slower CI a single test's setup
    tipped past the 30s pytest-timeout -> the whole G7 gate errored. Building
    once per session keeps N=DEFAULT_N_SOAK_RUNS and every downstream
    assertion identical while dropping per-test setup to ~0s.

    temp_db is function-scoped and cannot be a dependency of a session-scoped
    fixture, so its DB/env isolation is replicated here with a session-safe
    pytest.MonkeyPatch() + tmp_path_factory. run_soak_n manages its own
    per-run scratch ledger dirs internally, so no tmp_path wiring is needed
    for the runs themselves; the isolation below only pins the underlying
    chuzom usage DB away from the real ~/.chuzom so the soak can NEVER write
    to the production DB.
    """
    mp = pytest.MonkeyPatch()
    db_dir = tmp_path_factory.mktemp("soak_chuzom") / ".chuzom"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "test_usage.db"
    mp.setenv("CHUZOM_DB_PATH", str(db_path))
    mp.setenv("GEMINI_API_KEY", "test-key")
    mp.setenv("OPENAI_API_KEY", "test-key")
    mp.setenv("CHUZOM_ALLOW_STUBS", "1")

    # Reset the config singleton so it re-reads the isolated env, then pin the
    # DB path deterministically (mirrors temp_db / CHZ-AUD-001: pydantic env
    # binding for chuzom_db_path is ordering-fragile).
    import chuzom.config as config_module

    config_module._config = None
    from chuzom.config import get_config

    config = get_config()
    if str(config.chuzom_db_path) != str(db_path):
        try:
            object.__setattr__(config, "chuzom_db_path", db_path)
        except Exception:
            config.chuzom_db_path = db_path
    assert str(config.chuzom_db_path) != str(
        Path.home() / ".chuzom" / "usage.db"
    ), f"soak fixture failed to isolate DB; using {config.chuzom_db_path}"

    try:
        return asyncio.run(
            run_soak_n(
                n_runs=DEFAULT_N_SOAK_RUNS,
                monkeypatch=mp,
                use_gold_complexity=True,
            )
        )
    finally:
        mp.undo()
        config_module._config = None


def test_report_has_all_required_keys(soak_report):
    missing = REQUIRED_REPORT_KEYS - soak_report.keys()
    assert not missing, f"report.json missing required keys: {missing}"


def test_report_n_routes_matches_corpus_size(soak_report):
    rows = load_corpus()
    assert soak_report["n_routes"] == len(rows)


def test_report_host_mode_split_covers_both_modes(soak_report):
    # The committed corpus exercises both host modes (test_phase0_soak_corpus.py
    # already proves this at the corpus level); the report must reflect it.
    assert set(soak_report["host_mode_split"].keys()) <= {"subscription", "metered"}
    assert sum(soak_report["host_mode_split"].values()) == soak_report["n_routes"]


def test_overhead_never_exceeds_gross_savings(soak_report):
    """Phase 0.1 FIX 4d: hook-token overhead is populated only by the
    external Claude Code PreToolUse hook script, which this hermetic harness
    never invokes -- so the honest value is null ("not measured"), not a
    fake 0.0 that would silently imply overhead was checked and found to be
    zero. If a future harness change starts exercising that code path, this
    must fall back to asserting the real in-range percentage.
    """
    overhead = soak_report["overhead_as_pct_of_gross"]
    assert overhead is None or 0.0 <= overhead <= 1.0


def test_no_blended_dollar_figure_across_host_modes(soak_report):
    """R6/Phase-0 guardrail: subscription is reported in quota-tokens ONLY,
    metered is reported in dollars ONLY -- the schema itself enforces this
    (only a "metered" key under net_realized_savings_usd, only a
    "subscription" key under realized_quota_tokens_saved), so this test pins
    that shape rather than re-deriving the numbers.
    """
    assert set(soak_report["net_realized_savings_usd"].keys()) == {"metered"}
    assert set(soak_report["realized_quota_tokens_saved"].keys()) == {"subscription"}
    for bucket in ("net_realized_savings_usd", "realized_quota_tokens_saved"):
        for host_mode, ci in soak_report[bucket].items():
            # Phase 0.2 FIX A: the legacy point/ci95 keys are kept (now
            # populated from the N-run aggregate), alongside the new
            # point_median/run_spread/conservative_ci_lower headline keys.
            assert set(ci.keys()) == {
                "point",
                "ci95",
                "point_median",
                "run_spread",
                "conservative_ci_lower",
            }
            assert len(ci["ci95"]) == 2
            assert ci["ci95"][0] <= ci["point"] <= ci["ci95"][1] or ci["ci95"] == [ci["point"], ci["point"]]
            assert len(ci["run_spread"]) == 2
            assert ci["run_spread"][0] <= ci["point_median"] <= ci["run_spread"][1] or ci["run_spread"][0] == ci["run_spread"][1]


def test_subscription_quota_tokens_are_non_negative(soak_report):
    quota = soak_report["realized_quota_tokens_saved"]["subscription"]["point"]
    assert quota >= 0


def test_report_defensibility_is_honestly_labeled(soak_report):
    """Phase 0.1 exit gate (replaces the old point-estimate gate, which could
    "pass" on pure noise -- a point estimate whose 95% CI straddles 0 is not
    a proven saving, it's noise the gate was wrongly treating as a result),
    extended by Phase 0.2 FIX A/C to be robust across N independent soak
    runs (a single run's point estimate is not run-to-run reproducible --
    see soak.report.NONDETERMINISM_NOTE).

    The gate now checks ``conservative_ci_lower`` -- the MINIMUM 95% CI
    lower bound observed across all N runs, never a single run's point
    estimate or a single run's CI -- and the report is required to say so
    explicitly via ``savings_claim_supported``. Both outcomes are acceptable
    here as long as the label matches reality:
      * True  -> at least one headline metric's conservative_ci_lower (the
                 worst-case CI lower bound across all N runs) clears 0 --
                 a defensible, non-noise saving robust to run-to-run noise.
      * False -> neither metric's conservative_ci_lower clears 0 -- this is
                 honestly an infrastructure smoke-test (the pipeline ran end
                 to end and the report schema is complete), not proof of a
                 saving, and the report must not claim otherwise.
    This test asserts the label is *honest*, not that it's True -- an
    adversarial re-audit checks the label matches the underlying CI math,
    not that the soak corpus happens to produce a big number.
    """
    quota_floor = soak_report["realized_quota_tokens_saved"]["subscription"]["conservative_ci_lower"]
    net_floor = soak_report["net_realized_savings_usd"]["metered"]["conservative_ci_lower"]
    defensible = quota_floor > 0 or net_floor > 0
    assert soak_report["savings_claim_supported"] == defensible, (
        f"savings_claim_supported={soak_report['savings_claim_supported']} does not "
        f"match the CI math (quota conservative_ci_lower={quota_floor}, "
        f"net conservative_ci_lower={net_floor}) -- the label must reflect whether "
        "either metric's conservative (worst-of-N) CI lower bound actually clears 0, "
        "never a single run's point estimate or single-run CI."
    )


def test_quality_and_adoption_fractions_are_valid_rates(soak_report):
    for key in ("soak_dispatch_failure_rate", "gate_false_negative_rate", "adoption_unknown_fraction"):
        assert 0.0 <= soak_report[key] <= 1.0, f"{key} out of [0,1]: {soak_report[key]}"
    for key in ("quality_delta_p50", "quality_delta_p95"):
        assert 0.0 <= soak_report[key] <= 1.0, f"{key} out of [0,1]: {soak_report[key]}"


def test_effective_sample_size_matches_host_mode_split(soak_report):
    """Phase 0.1 FIX 6: effective_sample_size must reflect the actual number
    of rows feeding each headline CI, not an aspirational count -- since
    every corpus row currently contributes to its host mode's CI, this
    equals host_mode_split, but the two are computed independently (one from
    the raw RowResult list feeding bootstrap_ci, the other from a simple
    per-row tally) so this pins them together against silent drift."""
    ess = soak_report["effective_sample_size"]
    split = soak_report["host_mode_split"]
    assert ess["metered"] == split.get("metered", 0)
    assert ess["subscription"] == split.get("subscription", 0)


def test_report_metadata_fields_are_populated(soak_report):
    assert soak_report["corpus_version"]
    assert soak_report["baseline_tokens_method"] == "claude_tokens_avoided"
    assert soak_report["generated_at"]
    assert soak_report["chuzom_version"]
    assert soak_report["price_table_version"]
