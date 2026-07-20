"""Run the savings-integrity experiments offline and write a scorecard.

    python -m bench.experiments            # run all shapes, write report.md
    python -m bench.experiments --quiet    # only the PASS/FAIL summary

Exit code is non-zero if any invariant fails — usable as a CI gate.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import analysis, replay

REPORT = Path(__file__).resolve().parent / "report.md"

# Counterfactual quota scenarios (host-equivalent headroom, in dollars).
_SCENARIOS = {
    "unpressured (ample headroom)": 1e9,
    "over cap (no headroom)": 0.0,
}


async def _run() -> tuple[list[dict], list[tuple[str, bool, str]]]:
    rows: list[dict] = []
    checks: list[tuple[str, bool, str]] = []
    for shape in replay.SHAPES:
        trace = replay.load_trace(shape)
        sub = await replay.replay(shape, subscription=True)
        met = await replay.replay(shape, subscription=False)

        for label, ok, detail in analysis.check_reconciliation(sub, trace):
            checks.append((f"[{shape}] {label}", ok, detail))
        checks.append(tuple(f"[{shape}] {x}" if i == 0 else x
                            for i, x in enumerate(analysis.check_window_nesting(sub))))
        checks.append(tuple(f"[{shape}] {x}" if i == 0 else x
                            for i, x in enumerate(analysis.check_real_zero_on_subscription(sub))))
        # Determinism: replaying the same trace yields identical totals.
        sub2 = await replay.replay(shape, subscription=True)
        checks.append((f"[{shape}] deterministic replay",
                       sub["baseline_avoided_usd"] == sub2["baseline_avoided_usd"], ""))

        cf = {name: analysis.counterfactual(trace, cap_headroom_usd=h)
              for name, h in _SCENARIOS.items()}
        rows.append({"shape": shape, "sub": sub, "met": met, "cf": cf})
    return rows, checks


def _fmt_report(rows: list[dict], checks: list[tuple[str, bool, str]]) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = [f"# Savings-integrity scorecard  ({ts})", "",
         "Deterministic offline replay of three realistic session shapes through the",
         "real chuzom savings code. Baseline = latest Opus ($5/$25). See RETROSPECTIVE",
         "Deliverable 4.", "",
         "## Per-shape savings (all-time)", "",
         "| Shape | Turns | Routed% | DIRECT-SKIP% | Baseline-avoided | Real $ (sub) | Real $ (metered) |",
         "|---|---|---|---|---|---|---|"]
    for r in rows:
        s = r["sub"]
        met_real = r["met"]["real_dollars_avoided_usd"]
        L.append(f"| {r['shape']} | {s['turns']} | {s['routed_pct']} | {s['direct_skip_pct']} "
                 f"| ${s['baseline_avoided_usd']:.4f} | ${s['real_dollars_avoided_usd']:.4f} "
                 f"| ${met_real:.4f} |")
    L += ["", "## Counterfactual: real dollars by quota state (all-time)", "",
          "| Shape | Baseline-avoided | Real $ unpressured | Real $ over-cap | Real $ metered |",
          "|---|---|---|---|---|"]
    for r in rows:
        un = r["cf"]["unpressured (ample headroom)"]
        oc = r["cf"]["over cap (no headroom)"]
        L.append(f"| {r['shape']} | ${un.baseline_avoided_usd:.4f} "
                 f"| ${un.real_subscription_usd:.4f} | ${oc.real_subscription_usd:.4f} "
                 f"| ${un.real_metered_usd:.4f} |")
    L += ["", "**Reading:** on a flat-rate subscription with headroom, real dollars avoided is",
          "~$0 (M-3: chuzom is a quota-smoother, not a dollar-saver); the baseline-avoided",
          "figure is a token/quota story, not cash. Real dollars appear only over the cap",
          "or in metered API mode.", "",
          "## Invariants", ""]
    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        L.append(f"- [{mark}] {name}" + (f" — {detail}" if detail else ""))
    L += ["", f"**{passed}/{len(checks)} invariants passed.**", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="chuzom savings-integrity experiments")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    rows, checks = asyncio.run(_run())
    report = _fmt_report(rows, checks)
    REPORT.write_text(report)
    failed = [c for c in checks if not c[1]]
    if args.quiet:
        print(f"{len(checks) - len(failed)}/{len(checks)} invariants passed; report -> {REPORT}")
    else:
        print(report)
    for name, _, detail in failed:
        print(f"FAILED: {name} {detail}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
