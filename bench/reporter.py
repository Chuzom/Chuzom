"""Markdown report generator — turn RunRow + scorecards into readable output."""
from __future__ import annotations

from pathlib import Path

from bench.runner import RouterScorecard, RunRow, pareto_frontier


def _fmt_cost(usd: float) -> str:
    if usd >= 0.01:
        return f"${usd:.4f}"
    return f"${usd*1000:.3f}m"  # millicents


def _fmt_pct(p: float) -> str:
    return f"{p*100:.0f}%"


def render_report(rows: list[RunRow], cards: list[RouterScorecard]) -> str:
    """Build a full markdown report. Sections:
        1. Scorecard table — head-to-head ranking
        2. Pareto frontier — routers worth picking from
        3. Savings — total + per-difficulty
        4. Per-prompt detail — collapsible
    """
    out: list[str] = ["# Chuzom Benchmark — Head-to-Head Results", ""]

    # Sort by quality desc, then cost asc → ranking shows best quality first,
    # then ties broken by who's cheaper.
    sorted_cards = sorted(cards, key=lambda c: (-c.avg_judge_score, c.avg_cost_usd))

    out.append("## 1 · Scorecard")
    out.append("")
    out.append("| Rank | Router | Avg quality (1–5) | Quality preserved (≥4) | Avg cost / prompt | Avg tokens | Avg latency | Success |")
    out.append("|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(sorted_cards, 1):
        out.append(
            f"| {i} | **{c.router_name}** "
            f"| {c.avg_judge_score:.2f} "
            f"| {_fmt_pct(c.quality_preserved_pct)} "
            f"| {_fmt_cost(c.avg_cost_usd)} "
            f"| {c.avg_total_tokens:.0f} "
            f"| {c.avg_latency_ms:.0f} ms "
            f"| {c.prompts_succeeded}/{c.prompts_attempted} |"
        )
    out.append("")

    # Pareto frontier
    frontier = set(pareto_frontier(cards))
    out.append("## 2 · Pareto Frontier (cost vs quality)")
    out.append("")
    out.append("Routers below are the only ones worth picking from — every other router is strictly dominated (cheaper AND better exists).")
    out.append("")
    for c in sorted_cards:
        marker = "✅" if c.router_name in frontier else "  "
        out.append(
            f"{marker} `{c.router_name}` — quality {c.avg_judge_score:.2f}, cost {_fmt_cost(c.avg_cost_usd)}"
        )
    out.append("")

    # Savings: pick the cheapest-on-frontier (call it "champion") and
    # compare it to the most-expensive router as the "baseline savings".
    if sorted_cards:
        most_expensive = max(cards, key=lambda c: c.avg_cost_usd)
        # Champion: best quality on frontier; if frontier exists, cheapest-with-good-quality.
        champion_candidates = [c for c in cards if c.router_name in frontier]
        if champion_candidates:
            champion = max(champion_candidates, key=lambda c: c.avg_judge_score)
            if most_expensive.avg_cost_usd > 0:
                savings_pct = (most_expensive.avg_cost_usd - champion.avg_cost_usd) / most_expensive.avg_cost_usd
            else:
                savings_pct = 0.0
            quality_delta = champion.avg_judge_score - most_expensive.avg_judge_score
            out.append("## 3 · Savings")
            out.append("")
            out.append(f"**Champion (Pareto frontier, best quality):** `{champion.router_name}`")
            out.append(f"**Most expensive (baseline):** `{most_expensive.router_name}`")
            out.append("")
            out.append(f"- Cost savings vs baseline: **{_fmt_pct(savings_pct)}** ({_fmt_cost(most_expensive.avg_cost_usd)} → {_fmt_cost(champion.avg_cost_usd)} per prompt)")
            out.append(f"- Quality delta: **{quality_delta:+.2f}** points (1–5 scale)")
            out.append(f"- Token reduction: **{(most_expensive.avg_total_tokens - champion.avg_total_tokens) / max(1, most_expensive.avg_total_tokens) * 100:+.0f}%** ({most_expensive.avg_total_tokens:.0f} → {champion.avg_total_tokens:.0f} avg)")
            out.append("")

    # Per-difficulty savings breakdown
    out.append("## 4 · Per-difficulty breakdown")
    out.append("")
    for difficulty in ("easy", "moderate"):
        diff_rows = [r for r in rows if r.difficulty == difficulty]
        if not diff_rows:
            continue
        by_router: dict[str, list[RunRow]] = {}
        for r in diff_rows:
            by_router.setdefault(r.router_name, []).append(r)
        out.append(f"### {difficulty.title()} prompts ({len(diff_rows)//len(by_router)} prompts)")
        out.append("")
        out.append("| Router | Avg quality | Avg cost | Models used |")
        out.append("|---|---|---|---|")
        for name, rr in sorted(by_router.items(), key=lambda kv: -sum(r.judge_score for r in kv[1]) / len(kv[1])):
            avg_q = sum(r.judge_score for r in rr) / len(rr)
            avg_c = sum(r.cost_usd for r in rr) / len(rr)
            models = {}
            for r in rr:
                models[r.model_chosen] = models.get(r.model_chosen, 0) + 1
            models_str = ", ".join(f"{m} ({n}×)" for m, n in models.items())
            out.append(f"| `{name}` | {avg_q:.2f} | {_fmt_cost(avg_c)} | {models_str} |")
        out.append("")

    # Per-prompt detail
    out.append("## 5 · Per-prompt detail")
    out.append("")
    by_prompt: dict[str, list[RunRow]] = {}
    for r in rows:
        by_prompt.setdefault(r.corpus_id, []).append(r)
    for pid, prompt_rows in by_prompt.items():
        out.append(f"### {pid} ({prompt_rows[0].difficulty} · {prompt_rows[0].category})")
        out.append("")
        out.append("| Router | Model | Score | Tokens | Cost | Latency | Rationale |")
        out.append("|---|---|---|---|---|---|---|")
        for r in sorted(prompt_rows, key=lambda r: -r.judge_score):
            rationale = r.judge_rationale.replace("\n", " ")[:80]
            out.append(
                f"| `{r.router_name}` | `{r.model_chosen}` | {r.judge_score} "
                f"| {r.input_tokens}+{r.output_tokens} | {_fmt_cost(r.cost_usd)} "
                f"| {r.latency_ms} ms | {rationale} |"
            )
        out.append("")

    return "\n".join(out)


def save_report(rows: list[RunRow], cards: list[RouterScorecard], out_path: Path) -> Path:
    report = render_report(rows, cards)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    return out_path
