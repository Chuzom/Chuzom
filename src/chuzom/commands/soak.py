"""``chuzom soak`` -- Phase 0 Step 8 CLI: run the realized-savings soak
corpus end-to-end and write ``soak/report.json``.

Thin wrapper around ``soak.report.run_soak`` + ``write_report``. All the
hermetic mocking (no live API keys, no live provider dispatch) lives in
``soak/replay.py``; this module just wires up a scratch ledger, drives the
async pipeline, and prints a short summary.

Flags:
  --use-gold-complexity  Hermetic default. Resolve each corpus row's
                          complexity from its own ``gold_complexity`` label
                          instead of the classifier path -- this is also the
                          CI-safe path (G7 gate), since it guarantees no live
                          classifier call is attempted.
  --full                 Opt-in: resolve complexity via the normal
                          (non-gold) path instead of the corpus's
                          gold_complexity label. Mutually exclusive with
                          --use-gold-complexity (the last one wins if both
                          are passed; --full overrides the default).
  --out PATH              Where to write report.json. Defaults to
                          soak/report.json (soak.report.DEFAULT_REPORT_PATH).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

from soak.report import DEFAULT_REPORT_PATH, run_soak, write_report

__all__ = ["cmd_soak"]


def cmd_soak(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="chuzom soak")
    parser.add_argument(
        "--use-gold-complexity",
        action="store_true",
        default=True,
        help="Use each corpus row's gold_complexity as the complexity_hint "
             "(hermetic default -- no live classifier call).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Resolve complexity via the normal (non-gold) path instead of "
             "gold_complexity. Overrides --use-gold-complexity.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=f"Path to write report.json (default: {DEFAULT_REPORT_PATH}).",
    )
    opts = parser.parse_args(args)

    use_gold_complexity = not opts.full

    with tempfile.TemporaryDirectory(prefix="chuzom-soak-") as tmp:
        tmp_path = Path(tmp)
        ledger_path = tmp_path / "soak_ledger.db"
        routing_ledger_dir = tmp_path / "routing_ledger"
        routing_ledger_dir.mkdir(parents=True, exist_ok=True)

        try:
            report = asyncio.run(
                run_soak(
                    ledger_path=ledger_path,
                    routing_ledger_dir=routing_ledger_dir,
                    use_gold_complexity=use_gold_complexity,
                )
            )
        except ValueError as err:
            print(f"soak failed: {err}", file=sys.stderr)
            return 1

    out_path = Path(opts.out) if opts.out else None
    written = write_report(report, out_path)

    print(f"Wrote {written}")
    print(f"  corpus_version={report['corpus_version']}  n_routes={report['n_routes']}")
    print(f"  host_mode_split={report['host_mode_split']}")
    net_ci = report["net_realized_savings_usd"]["metered"]
    quota_ci = report["realized_quota_tokens_saved"]["subscription"]
    print(
        "  net_realized_savings_usd.metered.point="
        f"{net_ci['point']}  ci95={net_ci['ci95']}"
    )
    print(
        "  realized_quota_tokens_saved.subscription.point="
        f"{quota_ci['point']}  ci95={quota_ci['ci95']}"
    )
    print(f"  overhead_as_pct_of_gross={report['overhead_as_pct_of_gross']}")
    print(f"  mis_route_rate={report['mis_route_rate']}  adoption_unknown_fraction={report['adoption_unknown_fraction']}")
    # Phase 0.1 FIX 3: never surface only the point estimate -- state plainly
    # whether the CI lower bound actually supports a savings claim.
    if report["savings_claim_supported"]:
        print("  savings_claim_supported=True (a headline metric's 95% CI lower bound clears 0)")
    else:
        print(
            "  savings_claim_supported=False -- this run is an infrastructure "
            "smoke-test (pipeline ran, report schema complete), NOT proof of a saving."
        )
    return 0
