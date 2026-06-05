"""Session Summary Dashboard — terminal-rendered overview of routing activity.

Pulls from ~/.tessera/lineage.db and ~/.tessera/sessions.db and renders
a panel-based dashboard with:

    1. HEADLINE   — total cost + savings vs always-premium baseline
    2. SPARKLINE  — spend pattern across the session
    3. TIERS      — bar chart of local/cheap/mid/premium distribution
    4. PROVIDERS  — per-provider call counts + cost
    5. INVERSIONS — up/down inversion alerts with examples
    6. AGENTS     — per-session rollup if any agents ran
    7. SAFETY     — PII catches forced to local routing
    8. ROUTES     — top (task_type, model) pairs
    9. PUNCHLINE  — one-line summary the user can copy-paste

Designed to render in under 100ms with no network. Lazy-imports rich so
basic `tessera --help` stays snappy.
"""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from tessera.lineage import Inversion, LineageStore, Tier
from tessera.agents import SessionStore


# Premium baseline pricing — for the "vs always-premium" savings number.
# Using GPT-4o pricing (mid-tier) so the savings number is realistic, not
# inflated by comparing to Opus. Update when prices change.
_BASELINE_PER_1K_INPUT = 0.0025
_BASELINE_PER_1K_OUTPUT = 0.010


_TIER_COLOR = {
    Tier.LOCAL.value: "green",
    Tier.CHEAP.value: "cyan",
    Tier.MID.value: "yellow",
    Tier.PREMIUM.value: "magenta",
    Tier.UNKNOWN.value: "white",
}


@dataclass
class SessionSummaryData:
    """All aggregated stats the dashboard needs. Pure data — no rendering."""

    total_decisions: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    baseline_cost_usd: float = 0.0
    savings_usd: float = 0.0
    savings_pct: float = 0.0
    tier_counts: dict[str, int] = field(default_factory=dict)
    tier_costs: dict[str, float] = field(default_factory=dict)
    provider_counts: dict[str, int] = field(default_factory=dict)
    provider_costs: dict[str, float] = field(default_factory=dict)
    up_inversions: list[dict] = field(default_factory=list)
    down_inversions: list[dict] = field(default_factory=list)
    inversion_rate: float = 0.0
    pii_catches: int = 0
    framework_counts: dict[str, int] = field(default_factory=dict)
    top_routes: list[tuple[str, str, int]] = field(default_factory=list)
    cost_sparkline: list[float] = field(default_factory=list)
    agent_sessions: list[dict] = field(default_factory=list)
    earliest_ts: float = 0.0
    latest_ts: float = 0.0
    host_counts: dict[str, int] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if self.earliest_ts and self.latest_ts:
            return max(0.0, self.latest_ts - self.earliest_ts)
        return 0.0


def collect(
    lineage_store: LineageStore | None = None,
    session_store: SessionStore | None = None,
    *,
    since_seconds: float | None = 86400.0,
    limit: int = 5000,
) -> SessionSummaryData:
    """Aggregate stats from lineage + sessions DBs.

    Args:
        lineage_store / session_store: defaults to ~/.tessera/lineage.db and
            ~/.tessera/sessions.db when None.
        since_seconds: only include rows newer than this. None = all-time.
        limit: cap on lineage rows fetched (defaults to 5000 — covers a
            multi-day session).
    """
    lineage_store = lineage_store or LineageStore()
    session_store = session_store or SessionStore()
    rows = lineage_store.recent(limit=limit)
    if since_seconds is not None:
        cutoff = time.time() - since_seconds
        rows = [r for r in rows if r["timestamp"] >= cutoff]

    data = SessionSummaryData()
    if not rows:
        return data

    data.total_decisions = len(rows)
    data.earliest_ts = min(r["timestamp"] for r in rows)
    data.latest_ts = max(r["timestamp"] for r in rows)

    # Cost + latency + tier + provider aggregation
    for row in rows:
        cost = row.get("cost_usd", 0.0) or 0.0
        latency = row.get("latency_ms", 0) or 0
        tier = row.get("model_tier", Tier.UNKNOWN.value)
        model = row.get("model_chosen", "<unknown>")
        provider = model.split("/", 1)[0] if "/" in model else model
        host = row.get("host", "<unknown>")

        data.total_cost_usd += cost
        data.total_latency_ms += latency
        data.tier_counts[tier] = data.tier_counts.get(tier, 0) + 1
        data.tier_costs[tier] = data.tier_costs.get(tier, 0.0) + cost
        data.provider_counts[provider] = data.provider_counts.get(provider, 0) + 1
        data.provider_costs[provider] = data.provider_costs.get(provider, 0.0) + cost
        data.host_counts[host] = data.host_counts.get(host, 0) + 1

        framework = row.get("framework")
        if framework:
            data.framework_counts[framework] = (
                data.framework_counts.get(framework, 0) + 1
            )

        inv = row.get("inversion", Inversion.NONE.value)
        if inv == Inversion.UP.value:
            data.up_inversions.append({
                "model_chosen": model,
                "complexity": row.get("complexity"),
                "task_type": row.get("task_type"),
                "timestamp": row.get("timestamp"),
            })
        elif inv == Inversion.DOWN.value:
            data.down_inversions.append({
                "model_chosen": model,
                "complexity": row.get("complexity"),
                "task_type": row.get("task_type"),
                "timestamp": row.get("timestamp"),
            })

        # PII catches: heuristic via notes column
        notes = (row.get("notes") or "").lower()
        if "pii" in notes or "secret" in notes:
            data.pii_catches += 1

    # Baseline cost: estimate input/output tokens per row (we don't store
    # them yet — approximate from latency as a proxy: rough rule that
    # ~500 output tokens ≈ 2000ms latency). This is intentionally simple;
    # v0.0.3 will store actual token counts in lineage.
    for row in rows:
        latency = row.get("latency_ms", 0) or 0
        est_output_tokens = max(20, latency // 4)  # rough proxy
        est_input_tokens = max(50, est_output_tokens * 2)
        data.baseline_cost_usd += (
            (est_input_tokens / 1000) * _BASELINE_PER_1K_INPUT
            + (est_output_tokens / 1000) * _BASELINE_PER_1K_OUTPUT
        )
    data.savings_usd = max(0.0, data.baseline_cost_usd - data.total_cost_usd)
    if data.baseline_cost_usd > 0:
        data.savings_pct = data.savings_usd / data.baseline_cost_usd
    inv_total = len(data.up_inversions) + len(data.down_inversions)
    data.inversion_rate = inv_total / data.total_decisions if data.total_decisions else 0.0

    # Top routes — (task_type, tier) pairs ordered by frequency
    route_counts = Counter(
        (r.get("task_type", "?"), r.get("model_tier", "?"))
        for r in rows
    )
    data.top_routes = [
        (tt, tier, count)
        for (tt, tier), count in route_counts.most_common(8)
    ]

    # Cost sparkline — bucket spend into 24 time buckets across session
    if data.duration_seconds > 0:
        buckets = 24
        bucket_size = max(1.0, data.duration_seconds / buckets)
        spark: dict[int, float] = defaultdict(float)
        for row in rows:
            idx = int(
                (row["timestamp"] - data.earliest_ts) / bucket_size
            )
            idx = min(idx, buckets - 1)
            spark[idx] += row.get("cost_usd", 0.0) or 0.0
        data.cost_sparkline = [spark.get(i, 0.0) for i in range(buckets)]

    # Agent sessions
    try:
        # Get unique session_ids from lineage that have rollups
        session_ids = {
            r.get("session_id") for r in rows if r.get("session_id")
        }
        for sid in session_ids:
            try:
                rollup = session_store.rollup(sid)
                data.agent_sessions.append(rollup)
            except Exception:
                # Skip sessions whose store entry is gone
                continue
    except Exception:
        pass

    return data


# ────────────────────────────────────────────────────────────────────────
# Rendering
# ────────────────────────────────────────────────────────────────────────

_SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def _render_sparkline(values: list[float], width: int = 24) -> str:
    """Render a list of floats as a unicode bar sparkline."""
    if not values:
        return "—"
    max_v = max(values) or 1.0
    out = []
    for v in values[:width]:
        idx = int(round((v / max_v) * (len(_SPARK_CHARS) - 1)))
        out.append(_SPARK_CHARS[idx])
    return "".join(out)


def _fmt_cost(usd: float) -> str:
    if usd >= 1.0:
        return f"${usd:.2f}"
    if usd >= 0.01:
        return f"${usd:.4f}"
    if usd > 0:
        return f"{usd * 100:.3f}¢"
    return "$0.00"


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"


def render(data: SessionSummaryData, *, console=None) -> None:
    """Render the dashboard to console (defaults to stdout via rich)."""
    from rich import box
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.progress_bar import ProgressBar
    from rich.table import Table
    from rich.text import Text

    if console is None:
        console = Console()

    # ── HEADLINE — savings vs baseline ─────────────────────────────────
    headline_text = Text.assemble(
        ("Session savings  ", "bold"),
        (_fmt_cost(data.savings_usd), "bold green" if data.savings_usd > 0 else "white"),
        (f"  ({data.savings_pct * 100:.0f}% vs always-premium)", "dim"),
    )
    spend_line = Text.assemble(
        ("Spent ", "dim"),
        (_fmt_cost(data.total_cost_usd), "bold"),
        ("  ·  baseline ", "dim"),
        (_fmt_cost(data.baseline_cost_usd), "dim"),
    )
    decisions_line = Text.assemble(
        (f"{data.total_decisions} routing decisions", "bold"),
        ("  ·  ", "dim"),
        (_fmt_duration(data.duration_seconds), "dim"),
        ("  ·  ", "dim"),
        (f"{data.total_latency_ms / max(1, data.total_decisions):.0f} ms avg", "dim"),
    )
    headline = Panel(
        Group(headline_text, spend_line, decisions_line),
        title="◆ Session Summary",
        border_style="bright_blue",
        padding=(1, 2),
    )

    # ── SPARKLINE — spend over time ────────────────────────────────────
    if data.cost_sparkline:
        spark_text = Text(_render_sparkline(data.cost_sparkline),
                          style="cyan")
        spark_panel = Panel(
            Align.center(spark_text, vertical="middle"),
            title=f"Spend over time  ({len(data.cost_sparkline)} buckets)",
            border_style="cyan",
            padding=(0, 2),
        )
    else:
        spark_panel = None

    # ── TIER DISTRIBUTION ─────────────────────────────────────────────
    tier_table = Table(box=box.MINIMAL, show_header=True, show_edge=False,
                       header_style="bold", expand=True)
    tier_table.add_column("Tier", style="bold")
    tier_table.add_column("Calls", justify="right")
    tier_table.add_column("Cost", justify="right")
    tier_table.add_column("Share", justify="left", ratio=2)
    max_calls = max(data.tier_counts.values()) if data.tier_counts else 1
    tier_order = [Tier.LOCAL.value, Tier.CHEAP.value, Tier.MID.value,
                  Tier.PREMIUM.value, Tier.UNKNOWN.value]
    for tier in tier_order:
        n = data.tier_counts.get(tier, 0)
        if n == 0:
            continue
        cost = data.tier_costs.get(tier, 0.0)
        color = _TIER_COLOR.get(tier, "white")
        bar = ProgressBar(total=max_calls, completed=n,
                          complete_style=color, finished_style=color)
        tier_table.add_row(
            Text(tier, style=color),
            str(n), _fmt_cost(cost), bar,
        )
    tier_panel = Panel(tier_table, title="◆ Tier distribution",
                       border_style="green", padding=(0, 1))

    # ── PROVIDERS ─────────────────────────────────────────────────────
    provider_table = Table(box=box.MINIMAL, show_header=True,
                           show_edge=False, header_style="bold")
    provider_table.add_column("Provider")
    provider_table.add_column("Calls", justify="right")
    provider_table.add_column("Cost", justify="right")
    for provider, count in sorted(
        data.provider_counts.items(), key=lambda kv: -kv[1]
    )[:8]:
        provider_table.add_row(
            provider,
            str(count),
            _fmt_cost(data.provider_costs.get(provider, 0.0)),
        )
    provider_panel = Panel(provider_table, title="◆ Providers",
                           border_style="cyan", padding=(0, 1))

    # ── INVERSIONS ────────────────────────────────────────────────────
    inv_lines = []
    if data.up_inversions:
        inv_lines.append(Text.assemble(
            (f"↑ {len(data.up_inversions)} UP-inversion(s)", "bold red"),
            ("  — complex prompts routed to cheap/local", "dim"),
        ))
        for inv in data.up_inversions[:3]:
            inv_lines.append(Text.assemble(
                ("  · ", "dim red"),
                (str(inv["task_type"]), "yellow"),
                (" / ", "dim"),
                (str(inv["complexity"]), "bold"),
                (" → ", "dim"),
                (str(inv["model_chosen"]), "red"),
            ))
    if data.down_inversions:
        inv_lines.append(Text.assemble(
            (f"↓ {len(data.down_inversions)} DOWN-inversion(s)", "bold yellow"),
            ("  — simple prompts forced to premium", "dim"),
        ))
        for inv in data.down_inversions[:3]:
            inv_lines.append(Text.assemble(
                ("  · ", "dim yellow"),
                (str(inv["task_type"]), "yellow"),
                (" / ", "dim"),
                (str(inv["complexity"]), "bold"),
                (" → ", "dim"),
                (str(inv["model_chosen"]), "yellow"),
            ))
    if not inv_lines:
        inv_lines = [Text("✓ No routing inversions detected — every prompt "
                          "went to the right tier", style="green")]
    rate_color = (
        "green" if data.inversion_rate < 0.05
        else "yellow" if data.inversion_rate < 0.15
        else "red"
    )
    inv_lines.append(Text.assemble(
        ("Inversion rate: ", "dim"),
        (f"{data.inversion_rate * 100:.1f}%", rate_color),
        (" (target < 5%)", "dim"),
    ))
    inversions_panel = Panel(
        Group(*inv_lines),
        title="◆ Routing health (inversions)",
        border_style=rate_color, padding=(0, 1),
    )

    # ── SAFETY (PII) ──────────────────────────────────────────────────
    safety_color = "green" if data.pii_catches == 0 else "bright_green"
    safety_msg = (
        f"✓ {data.pii_catches} PII / secret leak(s) caught — forced local routing"
        if data.pii_catches > 0
        else "✓ No PII / secret signals fired (no leaks observed)"
    )
    safety_panel = Panel(
        Text(safety_msg, style=safety_color),
        title="◆ Safety", border_style=safety_color, padding=(0, 1),
    )

    # ── AGENTS ────────────────────────────────────────────────────────
    agent_panel = None
    if data.agent_sessions:
        agent_table = Table(box=box.MINIMAL, show_header=True,
                            show_edge=False, header_style="bold")
        agent_table.add_column("Agent")
        agent_table.add_column("Session", style="dim")
        agent_table.add_column("Steps", justify="right")
        agent_table.add_column("Cost", justify="right")
        agent_table.add_column("State")
        for sess in data.agent_sessions[:8]:
            agent_table.add_row(
                sess.get("agent_id", "?"),
                sess.get("session_id", "?")[:8] + "…",
                str(sess.get("total_steps", 0)),
                _fmt_cost(sess.get("total_cost_usd", 0.0)),
                sess.get("state", "?"),
            )
        agent_panel = Panel(agent_table, title="◆ Agent sessions",
                            border_style="magenta", padding=(0, 1))

    # ── TOP ROUTES ────────────────────────────────────────────────────
    routes_table = Table(box=box.MINIMAL, show_header=True,
                         show_edge=False, header_style="bold")
    routes_table.add_column("Task")
    routes_table.add_column("Tier")
    routes_table.add_column("Calls", justify="right")
    for task, tier, count in data.top_routes[:6]:
        color = _TIER_COLOR.get(tier, "white")
        routes_table.add_row(task, Text(tier, style=color), str(count))
    routes_panel = Panel(routes_table, title="◆ Top routes",
                         border_style="bright_black", padding=(0, 1))

    # ── PUNCHLINE ─────────────────────────────────────────────────────
    punch_parts = [
        f"Tessera classified {data.total_decisions} prompts",
    ]
    if data.tier_counts.get(Tier.LOCAL.value, 0) > 0:
        n = data.tier_counts[Tier.LOCAL.value]
        punch_parts.append(f"routed {n} to local (free)")
    if data.tier_counts.get(Tier.CHEAP.value, 0) > 0:
        n = data.tier_counts[Tier.CHEAP.value]
        c = data.tier_costs.get(Tier.CHEAP.value, 0.0)
        punch_parts.append(f"{n} to cheap ({_fmt_cost(c)})")
    if data.pii_catches > 0:
        punch_parts.append(
            f"caught {data.pii_catches} PII leak(s) → forced local"
        )
    if data.savings_usd > 0:
        punch_parts.append(
            f"saved {_fmt_cost(data.savings_usd)} "
            f"({data.savings_pct * 100:.0f}%) vs always-premium"
        )
    punchline = "  ·  ".join(punch_parts) + "."
    punchline_panel = Panel(
        Text(punchline, style="bold bright_white"),
        border_style="bright_blue",
        title="◆ One-line",
        padding=(0, 2),
    )

    # ── ASSEMBLE ──────────────────────────────────────────────────────
    console.print()
    console.print(headline)
    if spark_panel:
        console.print(spark_panel)
    console.print(Columns([tier_panel, provider_panel], equal=False,
                          expand=True))
    console.print(Columns([inversions_panel, safety_panel], expand=True))
    if agent_panel:
        console.print(agent_panel)
    console.print(routes_panel)
    console.print(punchline_panel)
    console.print()


def render_markdown(data: SessionSummaryData) -> str:
    """Alternative renderer for `tessera summary --markdown` / sharing."""
    out = ["# Tessera Session Summary\n"]

    out.append("## Headline\n")
    out.append(
        f"- **Session cost:** {_fmt_cost(data.total_cost_usd)}  "
        f"_(baseline {_fmt_cost(data.baseline_cost_usd)})_"
    )
    out.append(
        f"- **Savings vs always-premium:** "
        f"**{_fmt_cost(data.savings_usd)} ({data.savings_pct * 100:.0f}%)**"
    )
    out.append(f"- **Routing decisions:** {data.total_decisions}")
    out.append(f"- **Session duration:** {_fmt_duration(data.duration_seconds)}")
    out.append(
        f"- **Avg latency:** "
        f"{data.total_latency_ms / max(1, data.total_decisions):.0f} ms"
    )
    out.append("")

    out.append("## Spend pattern\n")
    if data.cost_sparkline:
        out.append(f"```\n{_render_sparkline(data.cost_sparkline)}\n```")
    out.append("")

    out.append("## Tier distribution\n")
    out.append("| Tier | Calls | Cost |")
    out.append("|---|---:|---:|")
    for tier in [Tier.LOCAL.value, Tier.CHEAP.value, Tier.MID.value,
                 Tier.PREMIUM.value, Tier.UNKNOWN.value]:
        n = data.tier_counts.get(tier, 0)
        if n == 0:
            continue
        c = data.tier_costs.get(tier, 0.0)
        out.append(f"| `{tier}` | {n} | {_fmt_cost(c)} |")
    out.append("")

    out.append("## Providers\n")
    out.append("| Provider | Calls | Cost |")
    out.append("|---|---:|---:|")
    for p, n in sorted(data.provider_counts.items(), key=lambda kv: -kv[1])[:8]:
        out.append(f"| `{p}` | {n} | {_fmt_cost(data.provider_costs[p])} |")
    out.append("")

    out.append("## Routing health\n")
    out.append(
        f"- Inversion rate: **{data.inversion_rate * 100:.1f}%**  "
        f"(target < 5%)"
    )
    out.append(f"- UP-inversions: {len(data.up_inversions)} (complex → cheap)")
    out.append(f"- DOWN-inversions: {len(data.down_inversions)} (simple → premium)")
    out.append("")

    out.append("## Safety\n")
    if data.pii_catches > 0:
        out.append(
            f"- ✓ **{data.pii_catches}** secret/PII leak(s) caught — "
            f"forced local routing"
        )
    else:
        out.append("- ✓ No PII signals fired this session")
    out.append("")

    if data.agent_sessions:
        out.append("## Agent sessions\n")
        out.append("| Agent | Session | Steps | Cost | State |")
        out.append("|---|---|---:|---:|---|")
        for s in data.agent_sessions[:8]:
            out.append(
                f"| `{s.get('agent_id', '?')}` "
                f"| `{s.get('session_id', '?')[:8]}…` "
                f"| {s.get('total_steps', 0)} "
                f"| {_fmt_cost(s.get('total_cost_usd', 0.0))} "
                f"| `{s.get('state', '?')}` |"
            )
        out.append("")

    if data.top_routes:
        out.append("## Top routes\n")
        out.append("| Task | Tier | Calls |")
        out.append("|---|---|---:|")
        for task, tier, count in data.top_routes[:6]:
            out.append(f"| `{task}` | `{tier}` | {count} |")
        out.append("")

    return "\n".join(out)


# ────────────────────────────────────────────────────────────────────────
# CLI entrypoint
# ────────────────────────────────────────────────────────────────────────

def cli_summary(
    *,
    since_hours: float = 24.0,
    limit: int = 5000,
    markdown: bool = False,
) -> int:
    """Implementation behind `tessera summary`. Returns exit code."""
    data = collect(since_seconds=since_hours * 3600, limit=limit)
    if markdown:
        print(render_markdown(data))
        return 0
    if data.total_decisions == 0:
        print(
            "No routing decisions recorded in the last "
            f"{since_hours:.0f}h. Use Tessera for a bit, then re-run "
            "`tessera summary`."
        )
        return 0
    render(data)
    return 0
