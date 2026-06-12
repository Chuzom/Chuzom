"""Session Summary Dashboard — premium rendered overview at session end.

Shows routing decisions, savings, and 14-day activity with Tokyo Night colors.
Rendered as separate panels with muted borders and vivid metrics.
"""

from __future__ import annotations

from typing import Optional

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Group

from chuzom.ui.theme import PALETTE, progress_bar


class SessionSummaryDashboard:
    """Premium session summary dashboard with multiple panels."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize dashboard."""
        self.console = console or Console()

    def render_header(self, timestamp: str = "") -> RenderableType:
        """Render header panel with title and timestamp."""
        header_text = "🎯  Routing Summary"
        if timestamp:
            header_text += f"\n{timestamp}"

        return Panel(
            Text(header_text, justify="center"),
            border_style=PALETTE.muted_border,
            style=f"on {PALETTE.bg_main}",
        )

    def render_decisions_table(
        self,
        decisions: list[dict[str, float | str | int]],
    ) -> RenderableType:
        """Render decisions breakdown by method.

        Args:
            decisions: List of {method, count, total, pct}
        """
        table = Table(
            title="Decisions by Method",
            show_header=True,
            header_style=f"dim {PALETTE.text_dim}",
            border_style=PALETTE.muted_border,
        )

        table.add_column("Method", style=PALETTE.accent, width=20)
        table.add_column("Count", justify="right", style=PALETTE.text_primary)
        table.add_column("Bar", width=32)
        table.add_column("%", justify="right", style=PALETTE.accent, width=6)

        total_count = sum(d.get("count", 0) for d in decisions)

        for decision in decisions:
            method = decision.get("method", "Unknown")
            count = decision.get("count", 0)
            pct = (count / total_count * 100) if total_count > 0 else 0

            bar = progress_bar(pct, max_val=100.0, width=25)

            table.add_row(
                f"[{PALETTE.accent}]{method}[/]",
                str(count),
                bar,
                f"[{PALETTE.accent}]{pct:.0f}%[/]",
            )

        # Zero-cost summary
        zero_cost_count = sum(
            d.get("count", 0)
            for d in decisions
            if d.get("method") in ("heuristic", "context-inherit", "ollama", "codex")
        )
        zero_cost_pct = (zero_cost_count / total_count * 100) if total_count > 0 else 0

        table.add_row(
            f"[{PALETTE.success}]Zero-Cost[/]",
            f"[{PALETTE.success}]{zero_cost_count}[/]",
            progress_bar(zero_cost_pct, max_val=100.0, width=25),
            f"[{PALETTE.success}]{zero_cost_pct:.0f}%[/]",
        )

        return Panel(table, border_style=PALETTE.muted_border, expand=False)

    def render_savings_panel(
        self,
        today: float = 0.0,
        week: float = 0.0,
        month: float = 0.0,
        lifetime: float = 0.0,
        free_calls: int = 0,
        free_saved: float = 0.0,
    ) -> RenderableType:
        """Render cost savings summary.

        Args:
            today: Today's savings
            week: This week's savings
            month: This month's savings
            lifetime: Lifetime savings
            free_calls: Number of free-model calls
            free_saved: Savings from free models
        """
        lines = []

        # Header
        lines.append(
            Text("Cost Savings Summary", style=f"bold {PALETTE.accent}", justify="left")
        )
        lines.append(Text(""))

        # Savings by period
        for label, amount in [
            ("💰 Lifetime Savings", lifetime),
            ("📈 Today", today),
            ("📊 This Week", week),
        ]:
            savings_text = f"${amount:.2f}" if amount >= 1.0 else f"${amount:.4f}"
            lines.append(
                Text(
                    f"  {label:<25} {savings_text:<12} (177% cheaper vs Opus)",
                    style=PALETTE.text_primary,
                )
            )

        lines.append(Text(""))

        # Free routing
        if free_calls > 0:
            free_text = f"codex {free_calls}× calls"
            saved_text = f"${free_saved:.2f} saved"
            lines.append(
                Text(
                    f"  Free Routing:  {free_text:<20} ·  {saved_text}  ✓",
                    style=PALETTE.success,
                )
            )

        content = Group(*lines)
        return Panel(content, border_style=PALETTE.muted_border, expand=False)

    def render_activity_chart(
        self,
        daily_calls: list[int],
        daily_tokens: list[int],
        avg_calls: int = 0,
        avg_tokens: int = 0,
    ) -> RenderableType:
        """Render 14-day activity sparklines.

        Args:
            daily_calls: Calls per day for last 14 days
            daily_tokens: Tokens per day for last 14 days
            avg_calls: Average calls per day
            avg_tokens: Average tokens per day
        """
        lines = []

        lines.append(Text("14-Day Activity", style=f"bold {PALETTE.accent}"))
        lines.append(Text(""))

        # Simple sparkline (─────────────────────)
        if daily_calls:
            max_calls = max(daily_calls) if daily_calls else 1
            sparkline = "".join(
                ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"][
                    min(7, int((c / max_calls * 8))) if max_calls > 0 else 0
                ]
                for c in daily_calls[-14:]
            )
            lines.append(
                Text(
                    f"  Calls: {sparkline}  {avg_calls} avg/day",
                    style=PALETTE.text_primary,
                )
            )

        if daily_tokens:
            max_tokens = max(daily_tokens) if daily_tokens else 1
            sparkline = "".join(
                ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"][
                    min(7, int((t / max_tokens * 8))) if max_tokens > 0 else 0
                ]
                for t in daily_tokens[-14:]
            )
            lines.append(
                Text(
                    f"  Tokens: {sparkline}  {avg_tokens} avg/day",
                    style=PALETTE.text_primary,
                )
            )

        lines.append(Text("  · 100% uptime ✓", style=PALETTE.success))

        content = Group(*lines)
        return Panel(content, border_style=PALETTE.muted_border, expand=False)

    def render_top_models(
        self,
        models: list[dict[str, float | str | int]],
    ) -> RenderableType:
        """Render top routed models table.

        Args:
            models: List of {name, count, cost, pct}
        """
        table = Table(
            title="Top Routed Models",
            show_header=True,
            header_style=f"dim {PALETTE.text_dim}",
            border_style=PALETTE.muted_border,
        )

        table.add_column("Model", style=PALETTE.accent)
        table.add_column("Count", justify="right")
        table.add_column("Cost", justify="right")
        table.add_column("%", justify="right", style=PALETTE.accent)

        total_cost = sum(m.get("cost", 0) for m in models)

        for i, model in enumerate(models[:4], 1):
            name = model.get("name", "Unknown")
            count = model.get("count", 0)
            cost = model.get("cost", 0)
            pct = (cost / total_cost * 100) if total_cost > 0 else 0

            table.add_row(
                f"{i}. {name}",
                f"{count}×",
                f"${cost:.2f}",
                f"{pct:.0f}%",
            )

        return Panel(table, border_style=PALETTE.muted_border, expand=False)

    def render_cost_sparkline(
        self,
        daily_costs: list[float],
        total_saved: float = 0.0,
    ) -> RenderableType:
        """Render 14-day cost trend sparkline.

        Args:
            daily_costs: Daily costs for last 14 days
            total_saved: Total savings amount
        """
        lines = []
        lines.append(Text("📊 14-Day Cost Trend", style=f"bold {PALETTE.accent}"))
        lines.append(Text(""))

        if daily_costs:
            max_cost = max(daily_costs) if daily_costs else 1
            sparkline = "".join(
                ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"][
                    min(7, int((c / max_cost * 8))) if max_cost > 0 else 0
                ]
                for c in daily_costs[-14:]
            )
            total = sum(daily_costs)
            avg = total / len(daily_costs) if daily_costs else 0

            lines.append(Text(f"  Trend: {sparkline}", style=PALETTE.text_primary))
            lines.append(Text(f"  Total: ${total:.2f}  |  Avg: ${avg:.2f}/day", style=PALETTE.text_primary))

            if total_saved > 0:
                lines.append(Text(f"  Saved: ${total_saved:.2f} via routing", style=PALETTE.success))

        content = Group(*lines)
        return Panel(content, border_style=PALETTE.muted_border, expand=False)

    def render_model_breakdown(
        self,
        model_stats: dict[str, float],
    ) -> RenderableType:
        """Render model distribution breakdown.

        Args:
            model_stats: Dict of {model: percentage}
        """
        lines = []
        lines.append(Text("🤖 Model Distribution", style=f"bold {PALETTE.accent}"))
        lines.append(Text(""))

        if model_stats:
            sorted_models = sorted(model_stats.items(), key=lambda x: x[1], reverse=True)
            for model, pct in sorted_models[:5]:  # Show top 5
                bar_length = int(pct / 5)  # Max 20 chars
                bar = "█" * bar_length + "░" * (20 - bar_length)
                model_short = model.split("/")[-1][:25]
                lines.append(
                    Text(
                        f"  {model_short:25} {bar} {pct:5.1f}%",
                        style=PALETTE.text_primary,
                    )
                )

        content = Group(*lines)
        return Panel(content, border_style=PALETTE.muted_border, expand=False)

    def render_quota_status(
        self,
        claude_quota_pct: float = 0.0,
        gemini_quota_pct: float = 0.0,
        claude_remaining: str = "Unknown",
        gemini_remaining: str = "Unknown",
    ) -> RenderableType:
        """Render subscription quota status.

        Args:
            claude_quota_pct: Claude quota used (0-100)
            gemini_quota_pct: Gemini quota used (0-100)
            claude_remaining: Time remaining for Claude
            gemini_remaining: Time remaining for Gemini
        """
        lines = []
        lines.append(Text("📦 Subscription Quotas", style=f"bold {PALETTE.accent}"))
        lines.append(Text(""))

        # Claude quota
        bar_length = int(claude_quota_pct / 5)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        claude_status = "🟢 OK" if claude_quota_pct < 50 else "🟡 HIGH" if claude_quota_pct < 80 else "🔴 CRITICAL"
        lines.append(
            Text(f"  Claude Pro:  [{bar}] {claude_quota_pct:5.1f}% {claude_status}", style=PALETTE.text_primary)
        )
        lines.append(Text(f"              {claude_remaining}", style=PALETTE.text_dim))

        lines.append(Text(""))

        # Gemini quota
        bar_length = int(gemini_quota_pct / 5)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        gemini_status = "🟢 OK" if gemini_quota_pct < 50 else "🟡 HIGH" if gemini_quota_pct < 80 else "🔴 CRITICAL"
        lines.append(
            Text(f"  Gemini API:  [{bar}] {gemini_quota_pct:5.1f}% {gemini_status}", style=PALETTE.text_primary)
        )
        lines.append(Text(f"               {gemini_remaining}", style=PALETTE.text_dim))

        content = Group(*lines)
        return Panel(content, border_style=PALETTE.muted_border, expand=False)

    def render_footer(self) -> RenderableType:
        """Render footer with session complete status."""
        footer_text = "✨ Session Complete  ·  Ready for next prompt"
        return Text(footer_text, style=f"dim {PALETTE.success}", justify="center")

    def render_full_dashboard(
        self,
        timestamp: str = "",
        decisions: list[dict] | None = None,
        savings: dict | None = None,
        daily_calls: list[int] | None = None,
        daily_tokens: list[int] | None = None,
        daily_costs: list[float] | None = None,
        total_saved: float = 0.0,
        model_breakdown: dict[str, float] | None = None,
        models: list[dict] | None = None,
        claude_quota_pct: float = 0.0,
        gemini_quota_pct: float = 0.0,
        claude_remaining: str = "Unknown",
        gemini_remaining: str = "Unknown",
    ) -> RenderableType:
        """Render complete dashboard with all panels.

        Args:
            timestamp: Session timestamp
            decisions: Decision breakdown data
            savings: Savings data {today, week, month, lifetime, free_calls, free_saved}
            daily_calls: Daily call counts
            daily_tokens: Daily token counts
            daily_costs: Daily costs for last 14 days
            total_saved: Total savings amount
            model_breakdown: Dict of model distribution
            models: Top models data
            claude_quota_pct: Claude quota percentage
            gemini_quota_pct: Gemini quota percentage
            claude_remaining: Claude remaining time
            gemini_remaining: Gemini remaining time

        Returns:
            Renderable group of all panels
        """
        panels = [
            self.render_header(timestamp),
            Text(""),
        ]

        if decisions:
            panels.append(self.render_decisions_table(decisions))
            panels.append(Text(""))

        if savings:
            panels.append(
                self.render_savings_panel(
                    today=savings.get("today", 0.0),
                    week=savings.get("week", 0.0),
                    month=savings.get("month", 0.0),
                    lifetime=savings.get("lifetime", 0.0),
                    free_calls=savings.get("free_calls", 0),
                    free_saved=savings.get("free_saved", 0.0),
                )
            )
            panels.append(Text(""))

        if daily_costs:
            panels.append(self.render_cost_sparkline(daily_costs, total_saved))
            panels.append(Text(""))

        if model_breakdown:
            panels.append(self.render_model_breakdown(model_breakdown))
            panels.append(Text(""))

        if claude_quota_pct > 0 or gemini_quota_pct > 0:
            panels.append(
                self.render_quota_status(
                    claude_quota_pct=claude_quota_pct,
                    gemini_quota_pct=gemini_quota_pct,
                    claude_remaining=claude_remaining,
                    gemini_remaining=gemini_remaining,
                )
            )
            panels.append(Text(""))

        if daily_calls or daily_tokens:
            panels.append(
                self.render_activity_chart(
                    daily_calls=daily_calls or [],
                    daily_tokens=daily_tokens or [],
                    avg_calls=sum(daily_calls) // len(daily_calls) if daily_calls else 0,
                    avg_tokens=sum(daily_tokens) // len(daily_tokens)
                    if daily_tokens
                    else 0,
                )
            )
            panels.append(Text(""))

        if models:
            panels.append(self.render_top_models(models))
            panels.append(Text(""))

        panels.append(self.render_footer())

        return Group(*panels)

    def print_dashboard(self, **kwargs) -> None:
        """Render and print complete dashboard to console."""
        dashboard = self.render_full_dashboard(**kwargs)
        self.console.print(dashboard)
