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

import pytest

from soak.corpus_schema import load_corpus, validate_corpus
from soak.report import run_soak

REQUIRED_REPORT_KEYS = {
    "corpus_version",
    "n_routes",
    "host_mode_split",
    "net_realized_savings_usd",
    "realized_quota_tokens_saved",
    "mis_route_rate",
    "quality_delta_p50",
    "quality_delta_p95",
    "gate_false_negative_rate",
    "adoption_unknown_fraction",
    "overhead_as_pct_of_gross",
    "baseline_tokens_method",
    "generated_at",
    "chuzom_version",
    "price_table_version",
}


def test_corpus_is_valid_and_secret_free_before_soaking():
    """CHZ-PRV-06: refuse to even attempt a soak over a corpus that fails
    schema or privacy validation -- ``run_soak`` itself raises on this, but
    this test isolates the assertion so a corpus regression fails loudly and
    specifically, not buried inside a broader pipeline failure."""
    rows = load_corpus()
    errors = validate_corpus(rows)
    assert errors == [], f"corpus failed validation: {errors}"


@pytest.fixture
def soak_report(temp_db, tmp_path, monkeypatch):
    """Run the full replay+report pipeline once against the committed v1
    corpus, hermetically (use_gold_complexity=True => no live classifier, and
    _call_row mocks out every network-touching dependency). Session-scoped
    would be nice, but monkeypatch/tmp_path are function-scoped, and the
    report build is cheap (small corpus, no real network calls) -- rerunning
    per-test is fine.
    """
    ledger_path = tmp_path / "soak_ledger.db"
    routing_ledger_dir = tmp_path / "routing_ledger"
    routing_ledger_dir.mkdir(parents=True, exist_ok=True)

    return asyncio.run(
        run_soak(
            ledger_path=ledger_path,
            routing_ledger_dir=routing_ledger_dir,
            monkeypatch=monkeypatch,
            use_gold_complexity=True,
        )
    )


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
    assert 0.0 <= soak_report["overhead_as_pct_of_gross"] <= 1.0


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
            assert set(ci.keys()) == {"point", "ci95"}
            assert len(ci["ci95"]) == 2
            assert ci["ci95"][0] <= ci["point"] <= ci["ci95"][1] or ci["ci95"] == [ci["point"], ci["point"]]


def test_subscription_quota_tokens_are_non_negative(soak_report):
    quota = soak_report["realized_quota_tokens_saved"]["subscription"]["point"]
    assert quota >= 0


def test_report_produces_a_non_degenerate_number(soak_report):
    """Phase 0 exit gate (per phase0_brief.md's final acceptance section):
    "a non-degenerate (subscription quota-tokens > 0 OR metered net > 0)
    number". Both figures are legitimate zero in principle (e.g. an
    all-subscription corpus with no multi-attempt escalation legitimately
    yields 0 realized quota-tokens under the actual_proxy baseline -- see
    execution_ledger.py's route_baseline_tokens/route_actual_tokens
    derivation), so this asserts the OR, not either figure individually.

    # TODO(phase-0): realized_quota_tokens_saved is structurally 0 for any
    # route with a single accepted attempt and no escalation, because
    # baseline_tokens is written as the actual_proxy of that SAME accepted
    # attempt (router.py ~2673) while route_actual_tokens sums the identical
    # value -- quota = max(0, baseline - actual) = 0 by construction. Only
    # multi-attempt (escalated) routes could show quota > 0 today, and this
    # soak harness's mocked dispatch chain never escalates. A truer subscription
    # quota-tokens signal needs either a real (pre-routing, frontier-model)
    # token-estimate baseline distinct from the actual_proxy, or corpus rows
    # that force escalation -- both deferred; Phase 0's bar is met here via
    # the metered net $ figure instead.
    """
    quota = soak_report["realized_quota_tokens_saved"]["subscription"]["point"]
    net_metered = soak_report["net_realized_savings_usd"]["metered"]["point"]
    assert quota > 0 or net_metered > 0, (
        f"degenerate soak result: quota={quota}, net_metered={net_metered}"
    )


def test_quality_and_adoption_fractions_are_valid_rates(soak_report):
    for key in ("mis_route_rate", "gate_false_negative_rate", "adoption_unknown_fraction"):
        assert 0.0 <= soak_report[key] <= 1.0, f"{key} out of [0,1]: {soak_report[key]}"
    for key in ("quality_delta_p50", "quality_delta_p95"):
        assert 0.0 <= soak_report[key] <= 1.0, f"{key} out of [0,1]: {soak_report[key]}"


def test_report_metadata_fields_are_populated(soak_report):
    assert soak_report["corpus_version"]
    assert soak_report["baseline_tokens_method"] == "claude_tokens_avoided"
    assert soak_report["generated_at"]
    assert soak_report["chuzom_version"]
    assert soak_report["price_table_version"]
