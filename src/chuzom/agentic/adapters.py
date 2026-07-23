"""Real-backend adapters implementing the MGEE ``Agent`` protocol.

Adapters shell out to agent CLIs (Codex now; Gemini/Antigravity later) but take
an injected ``runner`` so unit tests drive them with a fake subprocess — the
deterministic engine guarantees never depend on a live model. The adapter only
*runs* the agent and captures what it produced; whether the milestone is DONE is
decided by the milestone's own objective acceptance check, never the CLI's
self-report.
"""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chuzom.agentic.engine import AgentRunResult
from chuzom.agentic.ledger import Milestone


@dataclass(frozen=True)
class ProcResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


# runner(argv, input_text) -> ProcResult. Injected so tests never spawn a model.
Runner = Callable[[list[str], str], ProcResult]


def subprocess_runner(
    argv: list[str], input_text: str, *, cwd: str | None = None, timeout: float = 300.0
) -> ProcResult:
    """Real subprocess runner. A missing binary / timeout is a captured result,
    not an exception — the flow must never hang on a backend."""
    try:
        proc = subprocess.run(
            argv, input=input_text, capture_output=True, text=True,
            cwd=cwd, timeout=timeout, check=False,
        )
    except FileNotFoundError:
        return ProcResult(127, "", f"binary not found: {argv[0]}")
    except subprocess.TimeoutExpired:
        return ProcResult(124, "", f"timed out after {timeout}s")
    return ProcResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def pack_prompt(milestone: Milestone, frozen_context: list[dict[str, Any]]) -> str:
    """Build the delegated prompt: the current milestone + the frozen done-work
    so the agent resumes at the frontier instead of redoing completed milestones."""
    lines = [f"TASK: {milestone.description or milestone.id}"]
    if frozen_context:
        lines += ["", "ALREADY COMPLETED — build on these, do NOT redo:"]
        for c in frozen_context:
            lines.append(f"  - [{c.get('id')}] {c.get('description') or c.get('id')}")
    lines += ["", "An objective check will verify your work — make real, correct changes."]
    return "\n".join(lines)


@dataclass
class CodexAdapter:
    """Delegate a milestone to the Codex CLI. Fake-testable via ``runner``.

    ChatGPT-subscription Codex is metered at $0, so ``cost_per_call_usd``
    defaults to 0.0; savings are computed against a premium baseline separately.
    """

    tier: int
    runner: Runner | None = None
    binary: str = "codex"
    argv_extra: tuple[str, ...] = ("exec",)
    cost_per_call_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.runner is None:
            self.runner = subprocess_runner

    def run(
        self, milestone: Milestone, frozen_context: list[dict[str, Any]], budget_left: float
    ) -> AgentRunResult:
        prompt = pack_prompt(milestone, frozen_context)
        assert self.runner is not None  # set in __post_init__
        proc = self.runner([self.binary, *self.argv_extra], prompt)
        artifacts: dict[str, Any] = {
            "provider": "codex",
            "tier": self.tier,
            "mid": milestone.id,
            "returncode": proc.returncode,
            "output": proc.stdout,
            "stderr": proc.stderr,
            "prompt_sent": prompt,
        }
        confidence = 1.0 if proc.returncode == 0 else 0.3
        return AgentRunResult(artifacts, cost_usd=self.cost_per_call_usd, confidence=confidence)
