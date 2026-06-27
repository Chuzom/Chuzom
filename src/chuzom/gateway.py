"""Multi-protocol HTTP gateway — route ANY LLM client through Chuzom.

One server, several wire formats, all backed by the same router
(``build_chain`` + ``execute_chain``). A client enrolls by pointing its base URL
here — no code change, whichever SDK it speaks:

    OpenAI     POST /v1/chat/completions   OPENAI_BASE_URL=http://127.0.0.1:17900/v1
    Anthropic  POST /v1/messages           ANTHROPIC_BASE_URL=http://127.0.0.1:17900
    Ollama     POST /api/chat,/api/generate   point OLLAMA_BASE_URL/host here

Every call is metered into ``~/.chuzom/usage.db`` + ``savings_log.jsonl`` like the
in-editor hook path, so external agents finally show up in the ledger (Surface-C fix).
Bind host/port come from the active preset (see ``chuzom.presets``).

Run:  chuzom gateway   (or: python -m chuzom.gateway)
"""
from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from chuzom.hooks.chain_builder import build_chain, get_current_pressure, needs_claude_tools
from chuzom.hooks.direct_executor import execute_agent, execute_chain


def _load_dotenv() -> None:
    """Load provider API keys from chuzom's .env files into os.environ.

    A launchd/systemd-spawned gateway has a bare environment, so without this it
    has no GEMINI_API_KEY/etc. and every cloud-model route fails. Mirrors the
    hook's loader (no override of existing env)."""
    for env_path in (Path.home() / ".chuzom" / ".env", Path.home() / ".env"):
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            pass


_load_dotenv()  # at import, before any routing

app = FastAPI(title="Chuzom Gateway", version="2")

_CODE = re.compile(
    r"\b(code|function|class|def |bug|refactor|implement|compile|stack ?trace|"
    r"api|sql|regex|unit test|typescript|python|rust|golang)\b",
    re.IGNORECASE,
)


def _classify(prompt: str) -> tuple[str, str]:
    task = "code" if _CODE.search(prompt) else "analyze"
    n = len(prompt)
    complexity = "complex" if n > 2000 else "moderate" if n > 400 else "simple"
    return task, complexity


def _route(prompt: str, task_type: str | None, complexity: str | None):
    """Shared core: classify (if needed) → route → meter. Returns a DirectResult."""
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="no prompt content")
    if not task_type or not complexity:
        _t, _c = _classify(prompt)
        task_type, complexity = task_type or _t, complexity or _c

    zone, _pct = get_current_pressure()
    # File/local tasks → agent-loop (a local tool-calling model that reads files /
    # runs commands); plain Q&A → text-in/text-out. So EVERYTHING routes. The
    # agent loop needs a capable tool-caller, so bias its chain to the coder tier.
    if needs_claude_tools(prompt, task_type):
        result = execute_agent(prompt, build_chain("complex", zone, "code"), timeout=180)
    else:
        result = execute_chain(prompt, build_chain(complexity, zone, task_type),
                               task_type, timeout=150)
    if result is None:
        raise HTTPException(status_code=502,
                            detail="Chuzom routing failed — chain exhausted")
    try:
        from chuzom.hooks.savings_logger import log_direct_savings, log_direct_to_db
        log_direct_to_db(result=result, prompt=prompt, task_type=task_type,
                         complexity=complexity, classifier_type="gateway", session_id="gateway")
        log_direct_savings(result=result, task_type=task_type, complexity=complexity,
                           session_id="gateway", host="gateway")
    except Exception:
        pass
    return result


def _flatten(messages: list) -> str:
    parts = []
    for m in messages or []:
        role = m.get("role", "user") if isinstance(m, dict) else getattr(m, "role", "user")
        c = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        if isinstance(c, list):  # content-parts (OpenAI/Anthropic vision format)
            c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
        if c:
            parts.append(f"{role}: {c}")
    return "\n".join(parts)


# ── health / discovery ───────────────────────────────────────────────────────
@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "chuzom-gateway",
            "formats": ["openai", "anthropic", "ollama"]}


@app.get("/v1/models")
def models() -> dict:
    return {"object": "list",
            "data": [{"id": "chuzom-auto", "object": "model", "owned_by": "chuzom"}]}


@app.get("/api/tags")  # Ollama model-list shape
def ollama_tags() -> dict:
    return {"models": [{"name": "chuzom-auto", "model": "chuzom-auto"}]}


# ── OpenAI: POST /v1/chat/completions ────────────────────────────────────────
class _OAIRequest(BaseModel):
    model: str | None = None
    messages: list
    task_type: str | None = None
    complexity: str | None = None


@app.post("/v1/chat/completions")
def openai_chat(req: _OAIRequest) -> dict:
    r = _route(_flatten(req.messages), req.task_type, req.complexity)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": f"{r.model.provider}/{r.model.model}",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": r.text},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": r.input_tokens, "completion_tokens": r.output_tokens,
                  "total_tokens": r.input_tokens + r.output_tokens},
    }


# ── Anthropic: POST /v1/messages ─────────────────────────────────────────────
class _AnthropicRequest(BaseModel):
    model: str | None = None
    messages: list
    system: str | None = None
    max_tokens: int | None = None


@app.post("/v1/messages")
def anthropic_messages(req: _AnthropicRequest) -> dict:
    prompt = (f"system: {req.system}\n" if req.system else "") + _flatten(req.messages)
    r = _route(prompt, None, None)
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": f"{r.model.provider}/{r.model.model}",
        "content": [{"type": "text", "text": r.text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": r.input_tokens, "output_tokens": r.output_tokens},
    }


# ── Ollama: POST /api/chat  and  POST /api/generate ──────────────────────────
class _OllamaChat(BaseModel):
    model: str | None = None
    messages: list


class _OllamaGenerate(BaseModel):
    model: str | None = None
    prompt: str


@app.post("/api/chat")
def ollama_chat(req: _OllamaChat) -> dict:
    r = _route(_flatten(req.messages), None, None)
    return {
        "model": f"{r.model.provider}/{r.model.model}",
        "message": {"role": "assistant", "content": r.text},
        "done": True,
        "prompt_eval_count": r.input_tokens, "eval_count": r.output_tokens,
    }


@app.post("/api/generate")
def ollama_generate(req: _OllamaGenerate) -> dict:
    r = _route(req.prompt, None, None)
    return {
        "model": f"{r.model.provider}/{r.model.model}",
        "response": r.text,
        "done": True,
        "prompt_eval_count": r.input_tokens, "eval_count": r.output_tokens,
    }


def main() -> None:
    import uvicorn

    from chuzom import presets
    host, port = presets.bind()
    print(f"Chuzom Gateway [{presets.active_name()}] → http://{host}:{port}")
    print("  OpenAI    /v1/chat/completions   |  Anthropic /v1/messages   |  Ollama /api/chat,/api/generate")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
