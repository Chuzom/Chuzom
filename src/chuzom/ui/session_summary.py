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
        """Render 14-day activity sparklines with day labels.

        Args:
            daily_calls: Calls per day for last 14 days (oldest first)
            daily_tokens: Tokens per day for last 14 days (oldest first)
            avg_calls: Average calls per day
            avg_tokens: Average tokens per day
        """
        import datetime

        lines: list[Text] = []
        lines.append(Text("📈 14-Day Activity", style=f"bold {PALETTE.accent}"))
        lines.append(Text(""))

        BAR_CHARS = "▁▂▃▄▅▆▇█"

        def spark(values: list[int | float]) -> str:
            if not values:
                return ""
            mx = max(values) or 1
            return "".join(BAR_CHARS[min(7, int(v / mx * 8))] for v in values[-14:])

        def _day_labels(n: int) -> str:
            today = datetime.date.today()
            labels = []
            for i in range(n - 1, -1, -1):
                d = today - datetime.timedelta(days=i)
                labels.append(d.strftime("%d"))
            return " ".join(labels)

        n = min(14, len(daily_calls) if daily_calls else len(daily_tokens) if daily_tokens else 0)

        if n > 0:
            # Date header row
            day_labels = _day_labels(n)
            lines.append(Text(f"  {day_labels}", style=PALETTE.text_dim))

        if daily_calls and n > 0:
            sp = spark(daily_calls[-n:])
            # Space out sparkline chars to align with date labels (2 chars each)
            sp_wide = " ".join(sp)
            lines.append(Text(f"  {sp_wide}", style=PALETTE.accent))
            lines.append(
                Text(
                    f"  Calls  ·  avg {avg_calls}/day  ·  total {sum(daily_calls[-n:])}",
                    style=PALETTE.text_primary,
                )
            )
            lines.append(Text(""))

        if daily_tokens and n > 0:
            sp = spark(daily_tokens[-n:])
            sp_wide = " ".join(sp)
            lines.append(Text(f"  {sp_wide}", style=PALETTE.accent))
            lines.append(
                Text(
                    f"  Tokens ·  avg {avg_tokens:,}/day  ·  total {sum(daily_tokens[-n:]):,}",
                    style=PALETTE.text_primary,
                )
            )

        if not daily_calls and not daily_tokens:
            lines.append(Text("  No activity data for this period", style=PALETTE.text_dim))

        content = Group(*lines)
        return Panel(content, border_style=PALETTE.muted_border, expand=True, title="14-Day Activity", title_align="left")

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
        """Render 14-day cost trend sparkline with date labels.

        Args:
            daily_costs: Daily costs for last 14 days (oldest first)
            total_saved: Total savings amount
        """
        import datetime

        lines: list[Text] = []
        lines.append(Text("📊 14-Day Cost Trend", style=f"bold {PALETTE.accent}"))
        lines.append(Text(""))

        BAR_CHARS = "▁▂▃▄▅▆▇█"

        n = min(14, len(daily_costs)) if daily_costs else 0

        if n > 0:
            today = datetime.date.today()
            day_labels = " ".join(
                (today - datetime.timedelta(days=n - 1 - i)).strftime("%d")
                for i in range(n)
            )
            lines.append(Text(f"  {day_labels}", style=PALETTE.text_dim))

            window = daily_costs[-n:]
            mx = max(window) or 1
            sp_wide = " ".join(BAR_CHARS[min(7, int(c / mx * 8))] for c in window)
            lines.append(Text(f"  {sp_wide}", style=PALETTE.accent))

            total = sum(window)
            avg = total / n
            lines.append(Text(""))
            lines.append(Text(f"  Total: ${total:.2f}  ·  Avg: ${avg:.4f}/day", style=PALETTE.text_primary))

            if total_saved > 0:
                pct_saved = (total_saved / (total + total_saved) * 100) if (total + total_saved) > 0 else 0
                lines.append(Text(f"  Saved: ${total_saved:.2f} via routing  ({pct_saved:.0f}% of gross)", style=PALETTE.success))
        else:
            lines.append(Text("  No cost data for this period", style=PALETTE.text_dim))

        content = Group(*lines)
        return Panel(content, border_style=PALETTE.muted_border, expand=True, title="14-Day Cost Trend", title_align="left")

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
        claude_session_pct: float = 0.0,
        claude_session_resets_at: str = "",
        claude_weekly_resets_at: str = "",
        gemini_quota_pct: float = 0.0,
        codex_quota_pct: float = 0.0,
        codex_remaining: str = "",
        claude_remaining: str = "Unknown",
        gemini_remaining: str = "Unknown",
        subscriptions: list[dict] | None = None,
    ) -> RenderableType:
        """Render subscription quota status — flexible, shows active subscriptions only.

        Args:
            claude_quota_pct: Claude weekly quota used (0-100)
            claude_session_pct: Claude 5h session quota used (0-100)
            claude_session_resets_at: ISO timestamp when 5h window resets
            claude_weekly_resets_at: ISO timestamp when weekly window resets
            gemini_quota_pct: Gemini API quota used (0-100)
            codex_quota_pct: Codex quota used (0-100)
            codex_remaining: Codex remaining calls/quota string
            claude_remaining: Claude remaining text (legacy)
            gemini_remaining: Gemini remaining time text
            subscriptions: Optional list of {name, pct, resets_at, window} dicts
                           for fully flexible rendering
        """
        import datetime

        BAR_LEN = 20

        def _status_icon(pct: float) -> str:
            if pct < 50:
                return "🟢"
            if pct < 80:
                return "🟡"
            return "🔴"

        def _bar(pct: float) -> str:
            filled = min(BAR_LEN, int(pct / 100 * BAR_LEN))
            return "█" * filled + "░" * (BAR_LEN - filled)

        def _format_resets_at(iso_ts: str) -> str:
            if not iso_ts:
                return ""
            try:
                dt = datetime.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
                now = datetime.datetime.now(datetime.timezone.utc)
                delta = dt - now
                if delta.total_seconds() <= 0:
                    return "resets soon"
                total_sec = int(delta.total_seconds())
                hours, rem = divmod(total_sec, 3600)
                minutes = rem // 60
                if hours >= 24:
                    days = hours // 24
                    return f"resets in {days}d {hours % 24}h"
                if hours > 0:
                    return f"resets in {hours}h {minutes}m"
                return f"resets in {minutes}m"
            except Exception:
                return iso_ts

        lines: list[Text] = []
        lines.append(Text("📦 Subscription Quotas", style=f"bold {PALETTE.accent}"))
        lines.append(Text(""))

        any_shown = False

        # ── Claude Pro (structured: 5h session + weekly windows) ──────────────
        if claude_quota_pct > 0 or claude_session_pct > 0:
            any_shown = True
            lines.append(Text("  Claude Pro", style=f"bold {PALETTE.text_primary}"))

            # 5-hour session window
            if claude_session_pct >= 0:
                reset_str = _format_resets_at(claude_session_resets_at)
                icon = _status_icon(claude_session_pct)
                b = _bar(claude_session_pct)
                lines.append(
                    Text(
                        f"    5h session  [{b}] {claude_session_pct:5.1f}%  {icon}",
                        style=PALETTE.text_primary,
                    )
                )
                if reset_str:
                    lines.append(Text(f"                  {reset_str}", style=PALETTE.text_dim))

            # Weekly window
            icon = _status_icon(claude_quota_pct)
            b = _bar(claude_quota_pct)
            reset_str = _format_resets_at(claude_weekly_resets_at)
            lines.append(
                Text(
                    f"    Weekly      [{b}] {claude_quota_pct:5.1f}%  {icon}",
                    style=PALETTE.text_primary,
                )
            )
            if reset_str:
                lines.append(Text(f"                  {reset_str}", style=PALETTE.text_dim))
            elif claude_remaining and claude_remaining != "Unknown":
                lines.append(Text(f"                  {claude_remaining}", style=PALETTE.text_dim))

            lines.append(Text(""))

        # ── Gemini API ────────────────────────────────────────────────────────
        if gemini_quota_pct > 0:
            any_shown = True
            icon = _status_icon(gemini_quota_pct)
            b = _bar(gemini_quota_pct)
            lines.append(Text("  Gemini API", style=f"bold {PALETTE.text_primary}"))
            lines.append(
                Text(
                    f"    Daily rate   [{b}] {gemini_quota_pct:5.1f}%  {icon}",
                    style=PALETTE.text_primary,
                )
            )
            if gemini_remaining and gemini_remaining != "Unknown":
                lines.append(Text(f"                  {gemini_remaining}", style=PALETTE.text_dim))
            lines.append(Text(""))

        # ── Codex / OpenAI ────────────────────────────────────────────────────
        if codex_quota_pct > 0 or codex_remaining:
            any_shown = True
            icon = _status_icon(codex_quota_pct) if codex_quota_pct > 0 else "🟢"
            b = _bar(codex_quota_pct)
            lines.append(Text("  Codex (OpenAI)", style=f"bold {PALETTE.text_primary}"))
            if codex_quota_pct > 0:
                lines.append(
                    Text(
                        f"    Quota        [{b}] {codex_quota_pct:5.1f}%  {icon}",
                        style=PALETTE.text_primary,
                    )
                )
            if codex_remaining:
                lines.append(Text(f"    {codex_remaining}", style=PALETTE.text_dim))
            lines.append(Text(""))

        # ── Flexible extra subscriptions ──────────────────────────────────────
        for sub in (subscriptions or []):
            name = sub.get("name", "Unknown")
            pct = float(sub.get("pct", 0))
            resets_at = sub.get("resets_at", "")
            window = sub.get("window", "")
            any_shown = True
            icon = _status_icon(pct)
            b = _bar(pct)
            label = f"{window:12}" if window else f"{'Quota':12}"
            lines.append(Text(f"  {name}", style=f"bold {PALETTE.text_primary}"))
            lines.append(
                Text(f"    {label} [{b}] {pct:5.1f}%  {icon}", style=PALETTE.text_primary)
            )
            reset_str = _format_resets_at(resets_at)
            if reset_str:
                lines.append(Text(f"                  {reset_str}", style=PALETTE.text_dim))
            lines.append(Text(""))

        if not any_shown:
            lines.append(Text("  No active subscription quotas", style=PALETTE.text_dim))

        content = Group(*lines)
        return Panel(content, border_style=PALETTE.muted_border, expand=True, title="Subscription Quotas", title_align="left")

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
        claude_session_pct: float = 0.0,
        claude_session_resets_at: str = "",
        claude_weekly_resets_at: str = "",
        gemini_quota_pct: float = 0.0,
        codex_quota_pct: float = 0.0,
        codex_remaining: str = "",
        claude_remaining: str = "Unknown",
        gemini_remaining: str = "Unknown",
        subscriptions: list[dict] | None = None,
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

        # Always show cost sparkline (even if empty, shows "No historical data yet")
        panels.append(self.render_cost_sparkline(daily_costs or [], total_saved))
        panels.append(Text(""))

        # Always show model breakdown (even if empty, shows "No model data yet")
        panels.append(self.render_model_breakdown(model_breakdown or {}))
        panels.append(Text(""))

        # Always show quota status (even if unused)
        panels.append(
            self.render_quota_status(
                claude_quota_pct=claude_quota_pct,
                claude_session_pct=claude_session_pct,
                claude_session_resets_at=claude_session_resets_at,
                claude_weekly_resets_at=claude_weekly_resets_at,
                gemini_quota_pct=gemini_quota_pct,
                codex_quota_pct=codex_quota_pct,
                codex_remaining=codex_remaining,
                claude_remaining=claude_remaining,
                gemini_remaining=gemini_remaining,
                subscriptions=subscriptions,
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
