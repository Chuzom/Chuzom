"""Session Summary Dashboard — modern two-panel overview at session end.

Layout: main panel (routing + savings + quota) + 14-day activity bar chart.
Style: concise, information-dense, Tokyo Night palette.
"""

from __future__ import annotations

import datetime
from typing import Optional

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from chuzom.ui.theme import PALETTE


_METHOD_SHORT: dict[str, str] = {
    "heuristic": "heuristic",
    "heuristic-weak": "heuristic",
    "build-fast-path": "build-fast",
    "content-generation-fast-path": "content-gen",
    "ollama": "ollama",
    "llm": "llm-class",
    "context-inherit": "ctx-inherit",
    "code-context-inherit": "ctx-inherit",
    "override": "override",
    "fallback": "fallback",
    "unknown": "unknown",
    "introspection": "introspect",
    "introspect": "introspect",
    "introspection-fast-path": "introspect",
}

_METHOD_SYMBOLS: dict[str, str] = {
    "heuristic": "⚡",
    "heuristic-weak": "⚡",
    "build-fast-path": "🔨",
    "content-generation-fast-path": "📝",
    "ollama": "🧠",
    "llm": "🧠",
    "context-inherit": "🔗",
    "code-context-inherit": "🔗",
    "override": "📌",
    "fallback": "🔄",
    "unknown": "❓",
    "introspection": "🔍",
    "introspect": "🔍",
    "introspection-fast-path": "🔍",
}

_FREE_METHODS = frozenset({
    "heuristic", "heuristic-weak", "build-fast-path",
    "content-generation-fast-path", "context-inherit",
    "code-context-inherit", "introspection", "introspect",
    "introspection-fast-path",
})


def _fmt_tok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _fmt_usd(amount: float) -> str:
    return f"${amount:.2f}" if amount >= 0.01 else f"${amount:.4f}"


class SessionSummaryDashboard:
    """Modern two-panel session summary dashboard."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def _quota_bar(self, pct: float, width: int = 16) -> str:
        filled = min(width, int(pct / 100 * width))
        return "━" * filled + "─" * (width - filled)

    def _format_resets_at(self, iso_ts: str) -> str:
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

    def _bar_chart_rows(self, values: list[int], n_rows: int = 8) -> list[str]:
        """Build ASCII vertical bar chart rows, top to bottom."""
        if not values or max(values) == 0:
            return [" " * len(values)] * n_rows
        BLOCKS = " ▁▂▃▄▅▆▇█"
        max_val = max(values)
        rows = []
        for r in range(n_rows - 1, -1, -1):
            row_bottom = r * max_val / n_rows
            row_top = (r + 1) * max_val / n_rows
            chars = []
            for v in values:
                if v >= row_top:
                    chars.append("█")
                elif v <= row_bottom:
                    chars.append(" ")
                else:
                    fill = (v - row_bottom) / (row_top - row_bottom)
                    chars.append(BLOCKS[max(1, min(8, int(fill * 8 + 0.5)))])
            rows.append("".join(chars))
        return rows

    def render_main_panel(
        self,
        timestamp: str = "",
        decisions: list[dict] | None = None,
        savings: dict | None = None,
        claude_quota_pct: float = 0.0,
        claude_session_pct: float = 0.0,
        claude_session_resets_at: str = "",
        claude_weekly_resets_at: str = "",
        gemini_quota_pct: float = 0.0,
        gemini_resets_at: str = "",
        codex_quota_pct: float = 0.0,
        codex_resets_at: str = "",
        session_delta_pct: float | None = None,
        weekly_delta_pct: float | None = None,
        model_breakdown: dict[str, float] | None = None,
        session_models: list[dict] | None = None,
        subscriptions: list[dict] | None = None,
    ) -> RenderableType:
        """Single panel: routing decisions (left) + savings (right) + quota + models."""
        decisions = decisions or []
        savings = savings or {}

        total_hits = sum(d.get("count", 0) for d in decisions)
        zero_cost = sum(
            d.get("count", 0) for d in decisions
            if d.get("method", "") in _FREE_METHODS
        )
        zero_pct = (zero_cost / total_hits * 100) if total_hits > 0 else 0.0

        today_saved = savings.get("today", 0.0)
        lifetime_saved = savings.get("lifetime", 0.0)

        # ── Left: routing breakdown ──────────────────────────────────────────
        left_lines: list[RenderableType] = [
            Text(
                f"ROUTING  today  {total_hits} decisions",
                style=f"bold {PALETTE.text_primary}",
            ),
            Text(""),
        ]

        max_name_len = max(
            (len(_METHOD_SHORT.get(d.get("method", ""), d.get("method", "")[:12]))
             for d in decisions),
            default=10,
        )
        for d in decisions:
            method = d.get("method", "unknown")
            count = d.get("count", 0)
            pct = (count / total_hits * 100) if total_hits > 0 else 0
            symbol = d.get("symbol") or _METHOD_SYMBOLS.get(method, "❓")
            short = d.get("short") or _METHOD_SHORT.get(method, method[:12])
            left_lines.append(
                Text(
                    f"  {symbol} {short:<{max_name_len}}  {count:>3}   {pct:>3.0f}%",
                    style=PALETTE.text_primary,
                )
            )

        left_lines.append(Text(""))
        zc_bar = self._quota_bar(zero_pct, width=12)
        left_lines.append(
            Text(
                f"  Zero-cost: {zc_bar} {zero_pct:.0f}%",
                style=PALETTE.success,
            )
        )

        # ── Right: savings summary ───────────────────────────────────────────
        right_lines: list[RenderableType] = [
            Text("SAVINGS  all sessions", style=f"bold {PALETTE.text_primary}"),
            Text(""),
            Text(
                f"  {_fmt_usd(lifetime_saved):<10} lifetime",
                style=PALETTE.success,
            ),
            Text(
                f"  {_fmt_usd(today_saved):<10} today",
                style=PALETTE.text_primary,
            ),
        ]
        for key, label in (("week", "week"), ("month", "month")):
            amount = savings.get(key, 0.0)
            if amount > 0:
                right_lines.append(
                    Text(f"  {_fmt_usd(amount):<10} {label}", style=PALETTE.text_dim)
                )

        # ── Grid: left + right columns ───────────────────────────────────────
        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(ratio=3)
        grid.add_column(ratio=2)
        grid.add_row(Group(*left_lines), Group(*right_lines))

        # ── Quota section (full-width, below grid) ───────────────────────────
        quota_lines: list[RenderableType] = []

        if claude_quota_pct > 0 or claude_session_pct > 0:
            quota_lines.append(Text(""))
            quota_lines.append(
                Text("  Claude Subscription  live", style=f"bold {PALETTE.text_primary}")
            )

            if claude_session_pct >= 0:
                bar = self._quota_bar(claude_session_pct)
                delta_str = ""
                if session_delta_pct is not None:
                    sign = "+" if session_delta_pct >= 0 else ""
                    delta_str = f"  {sign}{session_delta_pct:.1f}pp"
                quota_lines.append(
                    Text(
                        f"   5h {bar}  {claude_session_pct:.0f}%{delta_str}",
                        style=PALETTE.text_primary,
                    )
                )
                reset_str = self._format_resets_at(claude_session_resets_at)
                if reset_str:
                    try:
                        dt = datetime.datetime.fromisoformat(
                            claude_session_resets_at.replace("Z", "+00:00")
                        )
                        local_str = dt.astimezone().strftime("%I:%M%p %Z").lstrip("0").lower()
                        quota_lines.append(
                            Text(f"  {reset_str} ({local_str})", style=PALETTE.text_dim)
                        )
                    except Exception:
                        quota_lines.append(Text(f"  {reset_str}", style=PALETTE.text_dim))

            if claude_quota_pct > 0:
                bar = self._quota_bar(claude_quota_pct)
                delta_str = ""
                if weekly_delta_pct is not None:
                    sign = "+" if weekly_delta_pct >= 0 else ""
                    delta_str = f"  {sign}{weekly_delta_pct:.1f}pp"
                quota_lines.append(
                    Text(
                        f"   weekly {bar}  {claude_quota_pct:.0f}%{delta_str}",
                        style=PALETTE.text_primary,
                    )
                )
                reset_str = self._format_resets_at(claude_weekly_resets_at)
                if reset_str:
                    quota_lines.append(Text(f"  {reset_str}", style=PALETTE.text_dim))

        if gemini_quota_pct > 0:
            quota_lines.append(Text(""))
            quota_lines.append(
                Text("  Gemini API", style=f"bold {PALETTE.text_primary}")
            )
            bar = self._quota_bar(gemini_quota_pct)
            quota_lines.append(
                Text(
                    f"   daily rate {bar}  {gemini_quota_pct:.0f}%",
                    style=PALETTE.text_primary,
                )
            )
            gemini_reset = gemini_resets_at
            if not gemini_reset:
                # Gemini daily quota resets at midnight UTC
                tomorrow = (
                    datetime.datetime.now(datetime.timezone.utc).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    ) + datetime.timedelta(days=1)
                )
                gemini_reset = tomorrow.isoformat()
            reset_str = self._format_resets_at(gemini_reset)
            if reset_str:
                quota_lines.append(Text(f"  {reset_str}", style=PALETTE.text_dim))

        if codex_quota_pct > 0:
            quota_lines.append(Text(""))
            quota_lines.append(
                Text("  Codex (OpenAI)", style=f"bold {PALETTE.text_primary}")
            )
            bar = self._quota_bar(codex_quota_pct)
            quota_lines.append(
                Text(
                    f"   quota {bar}  {codex_quota_pct:.0f}%",
                    style=PALETTE.text_primary,
                )
            )
            if codex_resets_at:
                reset_str = self._format_resets_at(codex_resets_at)
                if reset_str:
                    quota_lines.append(Text(f"  {reset_str}", style=PALETTE.text_dim))

        # ── Flexible extra subscriptions ──────────────────────────────────────
        for sub in (subscriptions or []):
            name = sub.get("name", "Unknown")
            pct = float(sub.get("pct", 0))
            resets_at = sub.get("resets_at", "")
            window = sub.get("window", "quota")
            quota_lines.append(Text(""))
            quota_lines.append(
                Text(f"  {name}", style=f"bold {PALETTE.text_primary}")
            )
            bar = self._quota_bar(pct)
            quota_lines.append(
                Text(f"   {window:<10} {bar}  {pct:.0f}%", style=PALETTE.text_primary)
            )
            reset_str = self._format_resets_at(resets_at)
            if reset_str:
                quota_lines.append(Text(f"  {reset_str}", style=PALETTE.text_dim))

        # ── Models section: per-model calls / tokens / cost / savings ─────────
        model_lines: list[RenderableType] = []
        effective_models = [m for m in (session_models or []) if m.get("calls", 0) > 0]

        if effective_models:
            # Real session data: show calls/tokens/cost per model
            model_lines.append(Text(""))
            model_lines.append(
                Text("  MODELS  this session", style=f"bold {PALETTE.text_primary}")
            )
            total_m_calls = 0
            total_m_tokens = 0
            total_m_cost = 0.0
            total_m_saved = 0.0
            for m in effective_models[:5]:
                model_name = m.get("model", "unknown")
                short = model_name.split("/")[-1][:20]
                calls = m.get("calls", 0)
                tokens = m.get("tokens", 0)
                cost = m.get("cost_usd", m.get("cost", 0.0))
                saved = m.get("saved_usd", m.get("saved", 0.0))
                provider = m.get("provider", "")
                total_m_calls += calls
                total_m_tokens += tokens
                total_m_cost += cost
                total_m_saved += saved
                tok_str = _fmt_tok(tokens) if tokens else "—"
                if provider == "subscription":
                    cost_str = "sub"
                elif cost == 0 and saved > 0:
                    cost_str = "free"
                elif cost > 0:
                    cost_str = _fmt_usd(cost)
                else:
                    cost_str = "—"
                saved_str = f"saved {_fmt_usd(saved)}" if saved > 0.001 else ""
                model_lines.append(
                    Text(
                        f"  {short:<20} {calls:>3}×  {tok_str:>6}  "
                        f"{cost_str:<6}  {saved_str}",
                        style=PALETTE.text_primary,
                    )
                )
            model_lines.append(
                Text(
                    f"  {'total':<20} {total_m_calls:>3}×  "
                    f"{_fmt_tok(total_m_tokens):>6}  "
                    f"{_fmt_usd(total_m_cost):<6}  "
                    f"saved {_fmt_usd(total_m_saved)}",
                    style=PALETTE.success,
                )
            )
        elif model_breakdown:
            # No LLM calls this session — show 14-day mix as context
            model_lines.append(Text(""))
            model_lines.append(
                Text("  MODELS  14-day mix (no LLM calls this session)", style=f"bold {PALETTE.text_dim}")
            )
            for model, pct in sorted(model_breakdown.items(), key=lambda x: -x[1])[:5]:
                short = model.split("/")[-1][:20]
                bar_w = 14
                filled = min(bar_w, round(pct / 100 * bar_w))
                bar = "━" * filled + "─" * (bar_w - filled)
                model_lines.append(
                    Text(
                        f"  {short:<20}  {bar}  {pct:.0f}%",
                        style=PALETTE.text_dim,
                    )
                )

        return Panel(
            Group(grid, *quota_lines, *model_lines),
            border_style=PALETTE.muted_border,
            padding=(1, 2),
            width=70,
        )

    def render_activity_panel(
        self,
        daily_calls: list[int],
        daily_tokens: list[int],
        daily_costs: list[float],
        total_saved: float = 0.0,
        overhead_ms: float = 0.0,
        cache_hit_pct: float = 0.0,
    ) -> RenderableType:
        """14-day activity panel with vertical bar chart and Y-axis labels."""
        n = min(14, len(daily_calls)) if daily_calls else 0
        values = daily_calls[-n:] if n > 0 else []
        N_ROWS = 8
        lines: list[RenderableType] = [
            Text("calls/day", style=PALETTE.text_dim)
        ]

        if values and max(values) > 0:
            max_val = max(values)
            chart_rows = self._bar_chart_rows(values, n_rows=N_ROWS)
            y_labels = [
                int(max_val * (N_ROWS - 1 - i) / max(N_ROWS - 1, 1))
                for i in range(N_ROWS)
            ]
            y_width = max(len(str(max_val)), 3)

            for y_label, row_chars in zip(y_labels, chart_rows):
                lines.append(
                    Text(
                        f"  {y_label:>{y_width}} ┤ {row_chars}",
                        style=PALETTE.accent,
                    )
                )
            lines.append(
                Text(f"  {' ' * y_width}  └{'─' * n}", style=PALETTE.text_dim)
            )

            # X-axis: actual dates, every other day
            today = datetime.date.today()
            x_parts: list[str] = []
            for i in range(n):
                d = today - datetime.timedelta(days=n - 1 - i)
                x_parts.append(d.strftime("%-d") if i % 2 == 0 else " ")
            lines.append(
                Text(
                    f"  {' ' * (y_width + 3)}" + "  ".join(x_parts),
                    style=PALETTE.text_dim,
                )
            )
        else:
            lines.append(Text("  No activity data for this period", style=PALETTE.text_dim))

        lines.append(Text(""))

        total_calls = sum(daily_calls[-n:]) if daily_calls and n > 0 else 0
        total_tokens = sum(daily_tokens[-n:]) if daily_tokens and n > 0 else 0
        avg_calls = total_calls // max(n, 1)

        lines.append(
            Text(
                f"  {total_calls:,} calls · {_fmt_tok(total_tokens)} tok · "
                f"{_fmt_usd(total_saved)} lifetime",
                style=PALETTE.text_primary,
            )
        )

        stats: list[str] = [f"avg {avg_calls}/day"]
        if overhead_ms > 0:
            stats.append(f"{overhead_ms:.0f}ms routing overhead")
        if cache_hit_pct > 0:
            stats.append(f"{cache_hit_pct:.0f}% cache hit")
        lines.append(Text(f"  {' · '.join(stats)}", style=PALETTE.text_dim))

        return Panel(
            Group(*lines),
            border_style=PALETTE.muted_border,
            title="14-DAY ACTIVITY",
            title_align="left",
            width=70,
        )

    def render_quota_graph(
        self,
        quota_samples: list[tuple[str, float]],
        label: str = "Claude weekly",
    ) -> RenderableType:
        """Line graph: subscription quota % over last 10h in 10-min buckets.

        Args:
            quota_samples: list of (iso_timestamp, pct_0_to_100) pairs
            label: quota label shown in footer
        """
        PLOT_LEFT = 5
        PLOT_W = 58
        PLOT_H = 7

        now = datetime.datetime.now(datetime.timezone.utc)
        window_start = now - datetime.timedelta(hours=10)
        N_BUCKETS = 60  # 10h / 10-min

        buckets: list[float | None] = [None] * N_BUCKETS
        for ts_str, raw_pct in quota_samples:
            try:
                ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts < window_start:
                    continue
                elapsed = (ts - window_start).total_seconds()
                idx = min(N_BUCKETS - 1, int(elapsed / 600))
                buckets[idx] = raw_pct
            except Exception:
                continue

        # Forward-fill: carry last known value forward
        last_known: float | None = None
        for i, v in enumerate(buckets):
            if v is not None:
                last_known = v
            elif last_known is not None:
                buckets[i] = last_known

        values = [v if v is not None else 0.0 for v in buckets]
        has_data = any(v > 0 for v in values)

        no_data_text = Text(
            "  No quota timeline data for this session", style=PALETTE.text_dim
        )
        if not has_data:
            return Panel(
                no_data_text,
                border_style=PALETTE.muted_border,
                title="QUOTA TIMELINE  last 10h · 10-min",
                title_align="left",
                width=70,
            )

        # Downsample to PLOT_W columns via linear interpolation
        xs: list[float] = []
        for col in range(PLOT_W):
            src = col * (len(values) - 1) / max(1, PLOT_W - 1)
            i = int(src)
            j = min(i + 1, len(values) - 1)
            t = src - i
            xs.append(values[i] * (1 - t) + values[j] * t)

        def y_of(v: float) -> int:
            return round((100 - max(0, min(100, v))) * (PLOT_H - 1) / 100)

        ys = [y_of(v) for v in xs]
        grid = [[" "] * PLOT_W for _ in range(PLOT_H)]

        # Draw line segments with box-drawing chars
        for x in range(PLOT_W - 1):
            y1, y2 = ys[x], ys[x + 1]
            if y1 == y2:
                grid[y1][x] = "─"
            elif y2 < y1:  # rising (quota increasing)
                grid[y1][x] = "╰"
                for y in range(y2 + 1, y1):
                    grid[y][x] = "│"
                if x + 1 < PLOT_W:
                    grid[y2][x + 1] = "╮"
            else:  # falling
                grid[y1][x] = "╭"
                for y in range(y1 + 1, y2):
                    grid[y][x] = "│"
                if x + 1 < PLOT_W:
                    grid[y2][x + 1] = "╯"

        grid[ys[-1]][-1] = "●"  # current value marker

        y_label_map = {y_of(p): f"{p}%" for p in (100, 75, 50, 25, 0)}
        lines: list[RenderableType] = []

        for row in range(PLOT_H):
            y_lbl = y_label_map.get(row, "   ")
            row_str = "".join(grid[row])
            pct_at_row = 100 - round(row * 100 / (PLOT_H - 1))
            if pct_at_row >= 80:
                style = PALETTE.error if hasattr(PALETTE, "error") else "red"
            elif pct_at_row >= 50:
                style = PALETTE.warning if hasattr(PALETTE, "warning") else "yellow"
            else:
                style = PALETTE.accent
            t = Text()
            t.append(f"{y_lbl:>4} ", style=PALETTE.text_dim)
            t.append(row_str, style=style)
            lines.append(t)

        # X-axis labels
        axis = [" "] * PLOT_W
        for frac, lbl in ((0.0, "10h"), (0.2, "8h"), (0.4, "6h"), (0.6, "4h"), (0.8, "2h"), (1.0, "now")):
            pos = min(PLOT_W - len(lbl), round(frac * (PLOT_W - 1)))
            for i, ch in enumerate(lbl):
                axis[pos + i] = ch
        lines.append(Text("     " + "".join(axis), style=PALETTE.text_dim))

        # Footer: current value + session delta
        current = values[-1]
        start_val = next((v for v in values if v > 0), values[0])
        delta = current - start_val
        sign = "+" if delta >= 0 else ""
        lines.append(
            Text(
                f"  {label}: {current:.1f}%  session +{sign}{delta:.1f}pp",
                style=PALETTE.text_primary,
            )
        )

        return Panel(
            Group(*lines),
            border_style=PALETTE.muted_border,
            title="QUOTA TIMELINE  last 10h · 10-min",
            title_align="left",
            width=70,
        )

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
        session_models: list[dict] | None = None,
        models: list[dict] | None = None,
        claude_quota_pct: float = 0.0,
        claude_session_pct: float = 0.0,
        claude_session_resets_at: str = "",
        claude_weekly_resets_at: str = "",
        gemini_quota_pct: float = 0.0,
        gemini_resets_at: str = "",
        codex_quota_pct: float = 0.0,
        codex_resets_at: str = "",
        codex_remaining: str = "",
        claude_remaining: str = "Unknown",
        gemini_remaining: str = "Unknown",
        subscriptions: list[dict] | None = None,
        session_delta_pct: float | None = None,
        weekly_delta_pct: float | None = None,
        overhead_ms: float = 0.0,
        cache_hit_pct: float = 0.0,
        quota_samples: list[tuple[str, float]] | None = None,
    ) -> RenderableType:
        """Two-panel dashboard: main summary + 14-day activity + quota timeline."""
        main = self.render_main_panel(
            timestamp=timestamp,
            decisions=decisions,
            savings=savings,
            claude_quota_pct=claude_quota_pct,
            claude_session_pct=claude_session_pct,
            claude_session_resets_at=claude_session_resets_at,
            claude_weekly_resets_at=claude_weekly_resets_at,
            gemini_quota_pct=gemini_quota_pct,
            gemini_resets_at=gemini_resets_at,
            codex_quota_pct=codex_quota_pct,
            codex_resets_at=codex_resets_at,
            session_delta_pct=session_delta_pct,
            weekly_delta_pct=weekly_delta_pct,
            model_breakdown=model_breakdown,
            session_models=session_models,
            subscriptions=subscriptions,
        )
        activity = self.render_activity_panel(
            daily_calls=daily_calls or [],
            daily_tokens=daily_tokens or [],
            daily_costs=daily_costs or [],
            total_saved=total_saved,
            overhead_ms=overhead_ms,
            cache_hit_pct=cache_hit_pct,
        )
        panels: list[RenderableType] = [Text(""), main, Text(""), activity]
        if quota_samples:
            quota_graph = self.render_quota_graph(quota_samples)
            panels.extend([Text(""), quota_graph])
        return Group(*panels)

    def print_dashboard(self, **kwargs) -> None:
        """Render and print complete dashboard to console."""
        self.console.print(self.render_full_dashboard(**kwargs))
