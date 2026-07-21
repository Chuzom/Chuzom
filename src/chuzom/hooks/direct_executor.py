"""Direct model execution — call LLMs via HTTP without Claude orchestration.

This module is used by auto-route.py to call models directly from the
UserPromptSubmit hook, returning responses via {"decision": "block"} so
Claude never sees the prompt (0 subscription tokens consumed).

Supports: Ollama (local), Gemini (API), OpenAI (API), Codex (local).
Each call function uses urllib.request (stdlib only — no dependencies).
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass

# Sentinel distinguishing "tag list not yet fetched" from None ("fetch failed").
_UNSET: set = object()  # type: ignore[assignment]


@dataclass(frozen=True)
class ModelSpec:
    """A model in the routing chain."""
    provider: str      # ollama, gemini, openai, codex
    model: str         # e.g. "qwen3.5:latest", "gemini-2.5-flash"
    quota_cost: float = 0.0  # 0 for free/paid-API, >0 for subscription models


@dataclass(frozen=True)
class DirectResult:
    """Result of a direct model call."""
    text: str
    model: ModelSpec
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0


# ── System Prompts ────────────────────────────────────────────────────────────

DIRECT_SYSTEM_PROMPT = """\
You are an AI assistant operating within the chuzom system, providing a direct response to a user of Claude Code.
Your primary goal is to provide a helpful, accurate, and concise response to the user's request.

Guidelines:
1. Be concise and get straight to the point.
2. Use standard Markdown for formatting (code blocks, bold, lists).
3. Do not include unnecessary conversational filler or meta-commentary about being an AI.
4. Your response will be displayed directly in the user's terminal.
"""


# ── Provider HTTP calls ──────────────────────────────────────────────────────

def _get_ollama_url() -> str:
    """Get Ollama base URL, reading env at call time (after dotenv is loaded)."""
    url = os.environ.get("CHUZOM_OLLAMA_URL") or \
          os.environ.get("OLLAMA_BASE_URL") or \
          "http://localhost:11434"
    return url


def ollama_is_alive(timeout: float = 0.5) -> bool:
    """0.5s pre-flight: HEAD /api/tags to confirm Ollama is reachable.

    Avoids spending the full model-call timeout (4s) waiting on a TCP connection
    that will time out anyway when Ollama is not running. Returns False on any
    network error, including connection-refused and timeout.
    """
    try:
        ollama_url = _get_ollama_url()
        req = urllib.request.Request(f"{ollama_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout):  # nosec B310 — localhost only
            return True
    except Exception:
        return False


def available_ollama_models(timeout: float = 0.5) -> set[str] | None:
    """Return the set of model names Ollama serves, via ``GET /api/tags``.

    Returns ``None`` when the tag list cannot be enumerated (Ollama unreachable
    or a malformed response) — distinct from an empty set (Ollama up, nothing
    pulled). Callers use this to avoid selecting a model that would 404 and
    silently fall the turn through to Claude (audit §2.4).
    """
    try:
        ollama_url = _get_ollama_url()
        req = urllib.request.Request(f"{ollama_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — localhost only
            data = json.loads(resp.read())
        return {m.get("name", "") for m in data.get("models", []) if m.get("name")}
    except Exception:
        return None


def _ollama_model_available(model: str, installed: set[str]) -> bool:
    """True if Ollama can serve ``model`` given the installed tag set.

    Mirrors Ollama's own default-tag resolution: a bare name (no ``:tag``)
    resolves to ``<name>:latest``. An explicit tag must match exactly — e.g.
    requesting ``qwen2.5:latest`` when only ``qwen2.5:7b`` is pulled still 404s,
    so we must not treat that as available (audit §2.4).
    """
    if model in installed:
        return True
    if ":" not in model:
        return f"{model}:latest" in installed
    return False


def _chat_messages(prompt: str, history: list[dict] | None) -> list[dict]:
    """Assemble [system, *history, user] for chat-style providers (§2.5).

    ``history`` is prior turns as ``{"role": "user"|"assistant", "content": str}``
    already trimmed/token-capped by the caller. None → the stateless 2-message
    shape (backward compatible).
    """
    messages = [{"role": "system", "content": DIRECT_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    return messages


def call_ollama(prompt: str, model: str, timeout: int = 4,
                history: list[dict] | None = None) -> str | None:
    """Call Ollama's /api/chat endpoint. Returns response text or None."""
    body = json.dumps({
        "model": model,
        "messages": _chat_messages(prompt, history),
        "stream": False,
        "think": False,
        "options": {"temperature": 0.3, "num_predict": 2048},
    }).encode()
    ollama_url = _get_ollama_url()
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — localhost only
            result = json.loads(resp.read())
            msg = result.get("message", {})
            content = msg.get("content", "")
            # Some models (qwen3.5) put response in thinking field when content is empty
            if not content.strip() and msg.get("thinking"):
                content = msg["thinking"]
            
            # Capture usage metrics if available
            usage = {
                "input_tokens": result.get("prompt_eval_count", 0),
                "output_tokens": result.get("eval_count", 0),
            }
            return content, usage
    except Exception:
        return None, {}


def call_gemini(prompt: str, model: str = "gemini-2.5-flash", timeout: int = 10,
                history: list[dict] | None = None) -> tuple[str | None, dict]:
    """Call Gemini API. Returns (response text, usage dict) or (None, {})."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None, {}
    # Gemini uses role "model" for assistant turns and nests text under parts.
    contents = []
    for turn in history or []:
        role = "model" if turn.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    # Gemini 1.5+ supports system_instruction
    body = json.dumps({
        "system_instruction": {"parts": [{"text": DIRECT_SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — HTTPS only
            result = json.loads(resp.read())
            content = result["candidates"][0]["content"]["parts"][0]["text"]
            usage = result.get("usageMetadata", {})
            return content, {
                "input_tokens": usage.get("promptTokenCount", 0),
                "output_tokens": usage.get("candidatesTokenCount", 0),
            }
    except Exception:
        return None, {}


def call_openai(prompt: str, model: str = "gpt-4o-mini", timeout: int = 10,
                history: list[dict] | None = None) -> tuple[str | None, dict]:
    """Call OpenAI chat completions API. Returns (response text, usage dict) or (None, {})."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None, {}
    body = json.dumps({
        "model": model,
        "messages": _chat_messages(prompt, history),
        "temperature": 0.3,
        "max_tokens": 2048,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — HTTPS only
            result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            return content, {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            }
    except Exception:
        return None, {}


# ── Quality Gate ─────────────────────────────────────────────────────────────

def quality_ok(response: str, task_type: str) -> bool:
    """Basic quality gate — reject garbage responses before returning to user."""
    if not response or len(response.strip()) < 10:
        return False
    # Model refused or is confused
    refusal_phrases = ("i cannot", "i can't", "as an ai", "i don't have")
    lower = response.lower()
    if sum(1 for p in refusal_phrases if p in lower) >= 2:
        return False
    return True


# ── Chain Executor ───────────────────────────────────────────────────────────

_PROVIDER_CALLS = {
    "ollama": lambda prompt, model, timeout, history: call_ollama(prompt, model, timeout, history),
    "gemini": lambda prompt, model, timeout, history: call_gemini(prompt, model, timeout, history),
    "openai": lambda prompt, model, timeout, history: call_openai(prompt, model, timeout, history),
}


def execute_chain(
    prompt: str,
    chain: list[ModelSpec],
    task_type: str,
    timeout: int = 4,
    history: list[dict] | None = None,
) -> DirectResult | None:
    """Try each model in the chain until one returns a quality response.

    Skips models whose provider is 'claude' - those cannot be called directly
    from the hook. The caller decides whether failure falls through or blocks.

    For Ollama models, runs a 0.5s pre-flight health check first so we spend
    4s max per Ollama call rather than 15s waiting on a dead connection.

    Returns DirectResult on success, None if all models failed or only Claude remains.
    """
    _ollama_alive: bool | None = None  # lazily evaluated once per chain execution
    _ollama_installed: set[str] | None = _UNSET  # tag set, fetched once per chain

    for model in chain:
        if model.provider == "claude":
            continue  # Can't call Claude from the hook — skip

        # Pre-flight for Ollama models (evaluated once, cached for the chain):
        #   1. Enumerate installed models via /api/tags.
        #   2. If enumerable, skip any model that is NOT pulled — calling it would
        #      404 and silently fall the turn through to Claude (audit §2.4).
        #   3. If /api/tags can't be enumerated, fall back to a plain reachability
        #      probe so a transient tag-list hiccup doesn't disable routing.
        if model.provider == "ollama":
            if _ollama_installed is _UNSET:
                _ollama_installed = available_ollama_models(timeout=0.5)
            if _ollama_installed is None:
                if _ollama_alive is None:
                    _ollama_alive = ollama_is_alive(timeout=0.5)
                if not _ollama_alive:
                    continue
            elif not _ollama_model_available(model.model, _ollama_installed):
                continue  # model not pulled — do not call (§2.4)

        call_fn = _PROVIDER_CALLS.get(model.provider)
        if not call_fn:
            continue

        t0 = time.monotonic()
        try:
            response, usage = call_fn(prompt, model.model, timeout, history)
        except Exception:
            continue

        if response and quality_ok(response, task_type):
            latency_ms = int((time.monotonic() - t0) * 1000)
            return DirectResult(
                text=response,
                model=model,
                latency_ms=latency_ms,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )

    return None  # All non-Claude models failed; the caller selects failover policy.


# ── Agent Loop Execution (for file-op tasks) ─────────────────────────────────

def execute_agent(
    prompt: str,
    chain: list[ModelSpec],
    project_root: str | None = None,
    timeout: int = 60,
) -> DirectResult | None:
    """Run a tool-calling agent loop for tasks that need file operations.

    Unlike execute_chain (text-in/text-out), this gives the model access to
    read_file, edit_file, write_file, search_files, list_files, and run_command.

    Only Ollama models support tool calling from the hook. Other providers
    are skipped (they'd need their own tool-calling protocol).

    Returns DirectResult on success, None if all models failed.
    """
    from pathlib import Path as _Path

    try:
        from chuzom.hooks.agent_loop import run_agent_loop
    except ImportError:
        return None

    if project_root:
        root = _Path(project_root)
    else:
        root = _Path.cwd()

    # Fix #4 + #3: try empirically-reliable Ollama tool-callers FIRST. Some
    # models advertise the `tools` capability but can't actually use the
    # structured protocol (observed: qwen2.5-coder:7b), so we order by PROVEN
    # reliability, not the capability flag.
    #
    # Primary signal is the self-calibrating registry (Fix #3): models that
    # passed a live ground-truth probe rank first, unknown next, known-failers
    # last. This auto-adapts to any future model without a code change. The
    # static substring priority below is the tiebreaker AND the fallback when
    # the registry is empty (never probed / Ollama down). Stable sort preserves
    # chain order among equally-ranked models; non-Ollama entries are skipped.
    _AGENT_PRIORITY = ("hermes", "qwen3-coder", "devstral", "qwen3")

    try:
        from chuzom.agentic_registry import get_registry, rank as _registry_rank
        _verdicts = get_registry()  # cached; only probes when model set changes
    except Exception:
        _verdicts = {}

    def _static_rank(name: str) -> int:
        for idx, sub in enumerate(_AGENT_PRIORITY):
            if sub in name:
                return idx
        return len(_AGENT_PRIORITY)

    def _agent_rank(m: ModelSpec) -> tuple[int, int]:
        if m.provider != "ollama":
            return (3, len(_AGENT_PRIORITY))  # non-ollama skipped anyway
        name = m.model.lower()
        reg = _registry_rank(m.model, _verdicts) if _verdicts else 1
        return (reg, _static_rank(name))

    chain = sorted(chain, key=_agent_rank)

    ollama_attempted = 0
    for model in chain:
        if model.provider != "ollama":
            continue  # Only Ollama supports tool calling from the hook (for now)

        ollama_attempted += 1
        t0 = time.monotonic()
        # run_agent_loop might need to return usage as well
        # For now, we'll just capture the response
        response = run_agent_loop(
            prompt=prompt,
            model=model.model,
            project_root=root,
            timeout_per_call=timeout,
        )

        if response and quality_ok(response, "code"):
            latency_ms = int((time.monotonic() - t0) * 1000)
            return DirectResult(
                text=response,
                model=model,
                latency_ms=latency_ms,
            )

    # Loud failure (Fix #4): the whole chain drifted/failed. Surface it on
    # stderr (which Claude Code shows) instead of returning a silent None —
    # callers can then fall back to native tools knowing the local loop gave up.
    if ollama_attempted:
        import sys as _sys
        print(
            f"[chuzom] agent-loop: all {ollama_attempted} ollama model(s) "
            f"failed or drifted — falling back",
            file=_sys.stderr,
        )
    return None
