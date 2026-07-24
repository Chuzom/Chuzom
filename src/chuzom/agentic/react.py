"""Local ReAct harness — a tier-0 Agent that runs a bounded tool-loop over a
local model (Ollama's native tool-calling API) with a sandboxed tool executor.

This is what turns a bare local text model into an *agent* for milestone
delegation. Both the model client and the tool executor are injected, so unit
tests drive the whole loop with fakes — no live model, no real shell — while the
default wiring talks to a real Ollama server + a bounded shell/file/gh executor.

Anti-stuck: the loop is hard-bounded by ``max_steps``; if the model never emits a
final answer it stops and returns what it has (the milestone's objective
acceptance check then decides pass/fail — the model's own claim is never trusted).
Local-model reliability is best-effort by nature; confidence is reported low.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chuzom.agentic.adapters import pack_prompt
from chuzom.agentic.engine import AgentRunResult
from chuzom.agentic.ledger import Milestone


@dataclass
class ToolCall:
    # NOT frozen: ``args`` is a dict, so a frozen dataclass would generate an
    # unhashable __hash__ that raises only when hashed — a latent footgun.
    name: str
    args: dict[str, Any]


@dataclass
class ChatTurn:
    """One model turn: a final ``content`` answer, ``tool_calls``, or an
    ``error`` (client-level failure — kept DISTINCT from a legitimate empty
    answer so the engine can surface an honest reason instead of a blank)."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: str = ""


# client(messages, tools) -> ChatTurn ; executor(name, args) -> result string.
OllamaClient = Callable[[list[dict[str, Any]], list[dict[str, Any]]], ChatTurn]
ToolExecutor = Callable[[str, dict[str, Any]], str]

_SYSTEM = (
    "You are a local coding agent. Use the provided tools to accomplish the task. "
    "When done, reply with a short final message (no tool call). Be concrete — an "
    "objective check verifies your work, so make real changes."
)

# Ollama tool schemas advertised to the model.
DEFAULT_TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "bash", "description": "Run a shell command and return its output.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                       "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file's contents.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Write content to a file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"},
                       "content": {"type": "string"}}, "required": ["path", "content"]}}},
]


def default_tool_executor(cwd: str | None = None, timeout: float = 30.0) -> ToolExecutor:
    """A bounded shell/file executor. Not a security sandbox — it caps time and
    output; run delegated irreversible work behind the MGEE worktree gate."""
    base = Path(cwd).resolve() if cwd else Path.cwd()

    def _resolve(path_arg: str) -> Path:
        # 🥷 Backslash-Security: using vibe-coding rules for Path Traversal & Directory Access
        # Relative paths resolve UNDER the working dir (a relative "marker.txt"
        # must land in cwd, not the process dir), and the result must stay within
        # base — a model-supplied "../../etc/passwd" is rejected, not followed.
        p = Path(path_arg)
        resolved = (p if p.is_absolute() else base / p).resolve()
        if base not in resolved.parents and resolved != base:
            raise ValueError(f"path escapes working directory: {path_arg}")
        return resolved

    def execute(name: str, args: dict[str, Any]) -> str:
        try:
            if name == "bash":
                proc = subprocess.run(
                    ["/bin/sh", "-c", str(args.get("command", ""))], cwd=str(base),
                    capture_output=True, text=True, timeout=timeout, check=False,
                )
                out = (proc.stdout or "") + (proc.stderr or "")
                return f"[exit {proc.returncode}]\n{out[:4000]}"
            if name == "read_file":
                return _resolve(args["path"]).read_text(encoding="utf-8", errors="ignore")[:4000]
            if name == "write_file":
                p = _resolve(args["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(str(args.get("content", "")), encoding="utf-8")
                return f"wrote {p}"
            return f"unknown tool: {name}"
        except Exception as exc:  # noqa: BLE001 — a tool error is returned to the model, never fatal
            return f"tool error: {exc}"
    return execute


@dataclass
class ReActAgent:
    """A local ReAct agent (tier 0). ``client`` + ``executor`` are injected."""

    tier: int = 0
    client: OllamaClient | None = None
    executor: ToolExecutor | None = None
    # Default to a model that is actually installed AND supports Ollama native
    # tool-calling. qwen2.5-coder:7b is frequently absent -> 404 -> silent empty
    # runs; qwen2.5:7b is the warm local default.
    model: str = "qwen2.5:7b"
    max_steps: int = 8
    cwd: str | None = None
    cost_per_call_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        if self.executor is None:
            self.executor = default_tool_executor(cwd=self.cwd)
        if self.client is None:
            self.client = _default_ollama_client(self.model)

    def run(
        self, milestone: Milestone, frozen_context: list[dict[str, Any]], budget_left: float
    ) -> AgentRunResult:
        assert self.client is not None and self.executor is not None
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": pack_prompt(milestone, frozen_context)},
        ]
        actions: list[dict[str, Any]] = []
        final = ""
        error = ""
        steps = 0
        for steps in range(1, self.max_steps + 1):
            turn = self.client(messages, DEFAULT_TOOLS)
            if turn.error:
                # Client-level failure (model missing, unreachable, bad JSON) —
                # record it and stop; do NOT treat it as an empty final answer.
                error = turn.error
                break
            if not turn.tool_calls:
                final = turn.content
                break
            messages.append({"role": "assistant", "content": turn.content})
            for tc in turn.tool_calls:
                result = self.executor(tc.name, tc.args)
                actions.append({"tool": tc.name, "args": tc.args, "result": result[:500]})
                messages.append({"role": "tool", "name": tc.name, "content": result})

        artifacts: dict[str, Any] = {
            "provider": "ollama-react",
            "tier": self.tier,
            "mid": milestone.id,
            "output": final,
            "actions": actions,
            "steps": steps,
            "hit_step_cap": (steps >= self.max_steps and not final),
            "error": error,
        }
        # local models are best-effort; confidence stays low even on a clean
        # finish, and lowest when the run errored out with nothing.
        confidence = 0.6 if final else 0.2
        return AgentRunResult(artifacts, cost_usd=self.cost_per_call_usd, confidence=confidence)


def _default_ollama_client(model: str, base_url: str | None = None) -> OllamaClient:
    """Real client hitting Ollama's /api/chat with tools. Lazy/deferred; unit
    tests inject a fake and never reach this."""
    import os
    import urllib.request

    url = (base_url or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")

    def client(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatTurn:
        body = json.dumps({"model": model, "messages": messages, "tools": tools,
                           "stream": False}).encode()
        req = urllib.request.Request(  # noqa: S310 — fixed localhost Ollama URL from config
            f"{url}/api/chat", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
                data = json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001 — surface the failure, don't fake an empty answer
            return ChatTurn(error=f"ollama call failed ({model}): {exc}")
        msg = data.get("message", {}) or {}
        calls = [
            ToolCall(tc["function"]["name"], tc["function"].get("arguments", {}) or {})
            for tc in (msg.get("tool_calls") or [])
        ]
        return ChatTurn(content=msg.get("content", "") or "", tool_calls=calls)

    return client
