"""Benchmark guard — CI gate that keeps the quality×cost frontier honest and fresh.

Closes G-BENCH-1's root cause: the benchmark results had gone 6 weeks stale, so
routing *quality* was effectively unmeasured while *savings* were tracked live.
This guard fails CI when either:

  1. **Regression** — the primary router's quality drops below a floor
     (share of prompts scoring >= 4, i.e. "quality preserved"). A router that
     saves money by returning worse answers should not pass silently.
  2. **Staleness** — the newest results file is older than a max age. A green
     benchmark that hasn't run in a month is not evidence of anything.

Run in CI weekly (and on changes to bench/ or the router):

    python -m bench            # produce a fresh results file
    python -m bench.guard      # gate on it — exits non-zero on failure

The check functions are pure (inputs in, verdict out) so they unit-test without
running any model. Only ``main()`` touches the filesystem/clock.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from bench.runner import RESULTS_DIR, RunRow, scorecards

# Defaults — override via env or CLI.
DEFAULT_QUALITY_FLOOR = 0.80   # >= 80% of prompts must score >= 4
DEFAULT_MAX_AGE_DAYS = 14      # results older than a fortnight are stale
PRIMARY_ROUTER = "chuzom"


# ── pure checks ──────────────────────────────────────────────────────────────

def check_regression(
    cards,
    quality_floor: float = DEFAULT_QUALITY_FLOOR,
    router: str = PRIMARY_ROUTER,
) -> tuple[bool, str]:
    """Fail if the primary router's quality_preserved_pct is below the floor."""
    card = next((c for c in cards if c.router_name == router), None)
    if card is None:
        return False, f"regression: no scorecard for router {router!r} in results"
    q = card.quality_preserved_pct
    if q < quality_floor:
        return False, (
            f"regression: {router} quality_preserved={q:.0%} "
            f"< floor {quality_floor:.0%} — routing is trading quality for cost"
        )
    return True, f"regression OK: {router} quality_preserved={q:.0%} >= {quality_floor:.0%}"


def results_age_days(results_dir: Path, now: float | None = None) -> float | None:
    """Age (in days) of the newest results JSON, or None if there are none."""
    files = sorted(results_dir.glob("*.json"))
    if not files:
        return None
    newest = max(files, key=lambda p: p.stat().st_mtime)
    now = time.time() if now is None else now
    return (now - newest.stat().st_mtime) / 86400.0


def check_freshness(
    results_dir: Path,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    now: float | None = None,
) -> tuple[bool, str]:
    """Fail if there are no results, or the newest is older than max_age_days."""
    age = results_age_days(results_dir, now=now)
    if age is None:
        return False, "staleness: no benchmark results found — run `python -m bench`"
    if age > max_age_days:
        return False, (
            f"staleness: newest results are {age:.1f} days old "
            f"> max {max_age_days:.0f} days — re-run `python -m bench`"
        )
    return True, f"freshness OK: newest results {age:.1f} days old (<= {max_age_days:.0f})"


# ── filesystem glue ──────────────────────────────────────────────────────────

def load_latest_rows(results_dir: Path) -> list[RunRow]:
    """Load the newest results JSON back into RunRow objects."""
    files = sorted(results_dir.glob("*.json"))
    if not files:
        return []
    newest = max(files, key=lambda p: p.stat().st_mtime)
    raw = json.loads(newest.read_text())
    return [RunRow(**row) for row in raw]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark freshness + regression guard")
    parser.add_argument(
        "--quality-floor", type=float,
        default=float(os.environ.get("CHUZOM_BENCH_QUALITY_FLOOR", DEFAULT_QUALITY_FLOOR)),
    )
    parser.add_argument(
        "--max-age-days", type=float,
        default=float(os.environ.get("CHUZOM_BENCH_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS)),
    )
    parser.add_argument("--router", default=PRIMARY_ROUTER)
    args = parser.parse_args()

    ok_fresh, msg_fresh = check_freshness(RESULTS_DIR, args.max_age_days)
    print(("✅ " if ok_fresh else "❌ ") + msg_fresh)
    if not ok_fresh:
        return 1  # can't judge regression without fresh results

    rows = load_latest_rows(RESULTS_DIR)
    cards = scorecards(rows)
    ok_reg, msg_reg = check_regression(cards, args.quality_floor, args.router)
    print(("✅ " if ok_reg else "❌ ") + msg_reg)
    return 0 if ok_reg else 1


if __name__ == "__main__":
    sys.exit(main())
