"""Phase 0 Step 8 -- ``chuzom soak`` CLI.

Verifies the real entry point (``cmd_soak``, dispatched from ``chuzom.cli``)
runs the soak pipeline end-to-end and writes a valid ``report.json`` to disk,
using the same hermetic default (``--use-gold-complexity``) as the G7 CI gate
in ``tests/soak/realized_savings_soak.py``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from chuzom.commands.soak import cmd_soak

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


def test_cmd_soak_use_gold_complexity_writes_valid_report():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "report.json"
        # --runs 2 keeps this a CLI-wiring test (rc, output path, valid report
        # schema incl. the min-across-runs aggregation) without running the full
        # DEFAULT_N_SOAK_RUNS soak inside the 30s pytest-timeout. The statistical
        # N-run behavior is exercised by tests/soak/realized_savings_soak.py.
        rc = cmd_soak(["--use-gold-complexity", "--runs", "2", "--out", str(out_path)])

        assert rc == 0
        assert out_path.exists()

        report = json.loads(out_path.read_text())
        missing = REQUIRED_REPORT_KEYS - report.keys()
        assert not missing, f"report.json missing required keys: {missing}"
        assert report["n_routes"] > 0
        # Phase 0.1 FIX 4d: hook overhead is null ("not measured") in this
        # hermetic harness -- the external PreToolUse hook script that
        # populates hook_input_tokens/hook_output_tokens is never invoked by
        # route_and_call, so a real percentage here would be structurally
        # impossible, not a genuine zero-overhead measurement.
        overhead = report["overhead_as_pct_of_gross"]
        assert overhead is None or 0.0 <= overhead <= 1.0

        # Phase 0.1 FIX 3, extended by Phase 0.2 FIX A/C: gate on
        # conservative_ci_lower -- the MINIMUM 95% CI lower bound observed
        # across all N soak runs (a single run's point estimate is not
        # run-to-run reproducible, see soak.report.NONDETERMINISM_NOTE) --
        # never a single run's point estimate or single-run CI. Require the
        # report's own label to agree with the math.
        quota_floor = report["realized_quota_tokens_saved"]["subscription"]["conservative_ci_lower"]
        net_floor = report["net_realized_savings_usd"]["metered"]["conservative_ci_lower"]
        defensible = quota_floor > 0 or net_floor > 0
        assert report["savings_claim_supported"] == defensible, (
            f"savings_claim_supported={report['savings_claim_supported']} does not "
            f"match the CI math (quota conservative_ci_lower={quota_floor}, "
            f"net conservative_ci_lower={net_floor})"
        )
        assert report["n_soak_runs"] >= 1


def test_cmd_soak_default_output_path_when_out_omitted(monkeypatch, tmp_path):
    """No --out given -> writes to soak.report.DEFAULT_REPORT_PATH.

    Redirects that module-level default into tmp_path rather than the real
    repo location, so running this test never leaves a generated
    soak/report.json dirtying the working tree.
    """
    import soak.report as report_mod

    default_path = tmp_path / "report.json"
    monkeypatch.setattr(report_mod, "DEFAULT_REPORT_PATH", default_path)

    # --runs 2: this test only verifies the default-output-path behavior, so it
    # need not run the full DEFAULT_N_SOAK_RUNS soak (which on a contended CI
    # runner exceeded the 30s pytest-timeout — same class as the G7 fix).
    rc = cmd_soak(["--use-gold-complexity", "--runs", "2"])

    assert rc == 0
    assert default_path.exists()
    report = json.loads(default_path.read_text())
    assert REQUIRED_REPORT_KEYS <= report.keys()
