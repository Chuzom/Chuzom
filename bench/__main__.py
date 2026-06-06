"""CLI entrypoint — `python -m bench` runs the full benchmark.

Usage:
    python -m bench                              # full corpus, default routers
    python -m bench --easy-only                  # smoke easy only
    python -m bench --routers chuzom,always-cheap
    python -m bench --judge-model openai/gpt-4o-mini
    python -m bench --no-cache                   # force re-runs
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from bench.reporter import save_report
from bench.routers import default_routers
from bench.runner import (
    RESULTS_DIR,
    load_corpus,
    load_full_corpus,
    run_benchmark,
    save_results,
    scorecards,
)


def _select_routers(spec: str | None):
    all_routers = default_routers()
    if not spec:
        return all_routers
    wanted = {name.strip() for name in spec.split(",")}
    chosen = [r for r in all_routers if r.name in wanted]
    missing = wanted - {r.name for r in chosen}
    if missing:
        print(f"unknown routers: {sorted(missing)}", file=sys.stderr)
        sys.exit(2)
    return chosen


async def amain(args: argparse.Namespace) -> int:
    if args.easy_only:
        corpus = load_corpus("easy")
    elif args.moderate_only:
        corpus = load_corpus("moderate")
    else:
        corpus = load_full_corpus()

    routers = _select_routers(args.routers)
    print(
        f"Running {len(corpus)} prompts × {len(routers)} routers = "
        f"{len(corpus) * len(routers)} routing calls + {sum(1 for e in corpus if e.get('kind') == 'subjective')} judge calls",
        file=sys.stderr,
    )

    if args.no_cache:
        from bench.runner import CACHE_DIR
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
        print("(cleared response cache)", file=sys.stderr)

    rows = await run_benchmark(routers, corpus=corpus, judge_model=args.judge_model)
    cards = scorecards(rows)

    run_id = time.strftime("%Y%m%d-%H%M%S")
    json_path = save_results(rows, run_id=run_id)
    md_path = save_report(rows, cards, out_path=RESULTS_DIR / f"{run_id}.md")
    print(f"\nResults written:\n  {json_path}\n  {md_path}", file=sys.stderr)

    # Print scorecard to stdout for quick inspection
    print("\nScorecard:")
    for c in sorted(cards, key=lambda c: (-c.avg_judge_score, c.avg_cost_usd)):
        print(
            f"  {c.router_name:20s}  q={c.avg_judge_score:.2f}  "
            f"cost=${c.avg_cost_usd:.5f}  tokens={c.avg_total_tokens:.0f}  "
            f"latency={c.avg_latency_ms:.0f}ms"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Chuzom router benchmark")
    parser.add_argument("--easy-only", action="store_true")
    parser.add_argument("--moderate-only", action="store_true")
    parser.add_argument("--routers", help="comma-separated router names (default: all)")
    parser.add_argument(
        "--judge-model", default="anthropic/claude-3.5-sonnet",
        help="LLM judge model (subjective prompts only). Default: claude-3.5-sonnet via subscription.",
    )
    parser.add_argument("--no-cache", action="store_true", help="force re-runs (clear cache)")
    args = parser.parse_args()
    return asyncio.run(amain(args))


if __name__ == "__main__":
    sys.exit(main())
