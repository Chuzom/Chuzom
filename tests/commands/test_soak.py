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


def test_cmd_soak_use_gold_complexity_writes_valid_report():
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "report.json"
        rc = cmd_soak(["--use-gold-complexity", "--out", str(out_path)])

        assert rc == 0
        assert out_path.exists()

        report = json.loads(out_path.read_text())
        missing = REQUIRED_REPORT_KEYS - report.keys()
        assert not missing, f"report.json missing required keys: {missing}"
        assert report["n_routes"] > 0
        assert 0.0 <= report["overhead_as_pct_of_gross"] <= 1.0

        quota = report["realized_quota_tokens_saved"]["subscription"]["point"]
        net_metered = report["net_realized_savings_usd"]["metered"]["point"]
        assert quota > 0 or net_metered > 0, (
            f"degenerate soak result: quota={quota}, net_metered={net_metered}"
        )


def test_cmd_soak_default_output_path_when_out_omitted(monkeypatch, tmp_path):
    """No --out given -> writes to soak.report.DEFAULT_REPORT_PATH.

    Redirects that module-level default into tmp_path rather than the real
    repo location, so running this test never leaves a generated
    soak/report.json dirtying the working tree.
    """
    import soak.report as report_mod

    default_path = tmp_path / "report.json"
    monkeypatch.setattr(report_mod, "DEFAULT_REPORT_PATH", default_path)

    rc = cmd_soak(["--use-gold-complexity"])

    assert rc == 0
    assert default_path.exists()
    report = json.loads(default_path.read_text())
    assert REQUIRED_REPORT_KEYS <= report.keys()
