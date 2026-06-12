"""TUI Panels — Specialized widgets for dashboard display.

Defines reusable panel components:
  - TimelinePanel: Route progress with stage indicators
  - OutputPanel: Live streaming output with formatting
  - MetricsPanel: Real-time KPI metrics
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static, RichLog
from rich.console import RenderableType
from rich.panel import Panel
from rich.text import Text
from rich.table import Table


class TimelinePanel(Static):
    """Display route progress timeline with stage indicators.

    Shows ordered sequence of routing stages:
      ✓ Completed (success)
      ✗ Failed (with reason)
      ⏳ Pending (in progress)
      ✨ Committed (output started - commit barrier)
    """

    stages: reactive[list[dict[str, Any]]] = reactive(
        [], recompose=True
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize timeline panel."""
        super().__init__(*args, **kwargs)
        self.stages = []

    def add_stage(
        self,
        name: str,
        status: str = "pending",
        details: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        """Add a new stage to the timeline.

        Args:
            name: Stage name (e.g., "Classification", "Attempt 1")
            status: Stage status - "pending", "success", or "failed"
            details: Additional details (e.g., model name, error reason)
            duration_ms: How long the stage took
        """
        icon = self._status_to_icon(status)
        stage = {
            "name": name,
            "status": status,
            "details": details,
            "duration_ms": duration_ms,
            "icon": icon,
        }
        self.stages = [*self.stages, stage]
        self.render()

    def _status_to_icon(self, status: str) -> str:
        """Convert status to display icon."""
        icons = {
            "success": "✓",
            "failed": "✗",
            "pending": "⏳",
        }
        return icons.get(status, "•")

    def render(self) -> Panel:
        """Render the timeline panel."""
        lines = []
        for stage in self.stages:
            icon = stage["icon"]
            name = stage["name"]
            status = stage["status"]
            details = stage["details"]

            # Color code by status
            if status == "success":
                color = "green"
            elif status == "failed":
                color = "red"
            else:
                color = "yellow"

            detail_text = f" — {details}" if details else ""
            line = f"  {icon} {name}{detail_text}"
            lines.append(Text(line, style=color))

        content = "\n".join(str(line) for line in lines) if lines else "Waiting..."
        return Panel(content, title="📋 Route Timeline", border_style="blue")


class OutputPanel(Static):
    """Display live streaming output with syntax highlighting.

    Features:
      - Real-time text streaming
      - Syntax highlighting for code blocks
      - Thinking block extraction and collapsible display
      - Scrollable with line wrapping
    """

    accumulated_text: str = ""
    in_code_block: bool = False
    code_language: str = ""
    code_buffer: str = ""
    thinking_blocks: list[str] = []

    def compose(self) -> ComposeResult:
        """Compose the output panel with a RichLog."""
        yield RichLog(wrap=True, markup=True, highlight=True, id="output-log")

    def append_text(self, text: str) -> None:
        """Append text to the output stream."""
        self.accumulated_text += text

        # Check for thinking blocks (Claude)
        if "<thinking>" in text:
            self.thinking_blocks.append("🧠 Thinking...")

        # Check for code blocks
        if "```" in text:
            self._handle_code_block()
        else:
            # Regular text output
            log: RichLog = self.query_one("#output-log", RichLog)
            log.write(Text(text, style="default"))

    def _handle_code_block(self) -> None:
        """Handle code block formatting."""
        log: RichLog = self.query_one("#output-log", RichLog)
        lines = self.accumulated_text.split("\n")
        for line in lines:
            if line.startswith("```"):
                self.in_code_block = not self.in_code_block
                if self.in_code_block:
                    parts = line.split("```")
                    self.code_language = parts[1].strip() if len(parts) > 1 else ""
            elif self.in_code_block:
                self.code_buffer += line + "\n"
            else:
                log.write(Text(line + "\n", style="default"))

    def render(self) -> RenderableType:
        """Render the panel content."""
        return Text(self.accumulated_text or "(Waiting for output...)", style="default")


class MetricsPanel(Static):
    """Display real-time routing metrics.

    Shows:
      - Current model
      - Token counts (input + output)
      - Cost accumulation
      - Throughput (tokens/sec)
      - Latency
      - Confidence (if classification available)
    """

    model: reactive[str] = reactive("N/A")
    input_tokens: reactive[int] = reactive(0)
    output_tokens: reactive[int] = reactive(0)
    cost_usd: reactive[float] = reactive(0.0)
    latency_ms: reactive[float] = reactive(0.0)
    throughput: reactive[float] = reactive(0.0)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize metrics panel."""
        super().__init__(*args, **kwargs)

    def update_metrics(
        self,
        model: str = "N/A",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        throughput: float = 0.0,
    ) -> None:
        """Update metric values."""
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = cost_usd
        self.latency_ms = latency_ms
        self.throughput = throughput
        self.render()

    def render(self) -> Panel:
        """Render metrics panel."""
        total_tokens = self.input_tokens + self.output_tokens

        # Build metrics table
        table = Table(show_header=False, show_footer=False, padding=(0, 1))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("🤖 Model", self.model)
        table.add_row("📊 Tokens", f"{total_tokens:,}")
        table.add_row("📥 Input", f"{self.input_tokens:,}")
        table.add_row("📤 Output", f"{self.output_tokens:,}")
        table.add_row("💰 Cost", f"${self.cost_usd:.4f}")
        table.add_row("⏱️  Latency", f"{self.latency_ms:.0f}ms")
        table.add_row("🚀 Throughput", f"{self.throughput:.1f} tok/s")

        return Panel(table, title="📈 Metrics", border_style="green", expand=True)
