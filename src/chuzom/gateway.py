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


class _ModelRef:
    """Tiny ``.provider`` / ``.model`` holder so the wire-format endpoints can keep
    formatting ``f"{r.model.provider}/{r.model.model}"`` unchanged."""

    __slots__ = ("provider", "model")

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model


class _RoutedResult:
    """Adapts :func:`route_payload`'s JSON dict to the ``.text`` /
    ``.model.provider`` / ``.model.model`` / ``.input_tokens`` / ``.output_tokens``
    shape the gateway's wire-format endpoints expect."""

    __slots__ = ("text", "input_tokens", "output_tokens", "cost_usd", "model")

    def __init__(self, d: dict) -> None:
        self.text = d.get("text", "")
        self.input_tokens = d.get("input_tokens", 0) or 0
        self.output_tokens = d.get("output_tokens", 0) or 0
        self.cost_usd = d.get("cost_usd", 0.0) or 0.0
        prov = d.get("provider") or ""
        mdl = d.get("model") or ""
        # route_and_call may return model as "provider/model" or bare — normalize
        # to the bare model name so f"{provider}/{model}" doesn't double the prefix.
        bare = mdl.split("/", 1)[1] if "/" in mdl and mdl.split("/", 1)[0] == prov else mdl
        self.model = _ModelRef(prov, bare)


def _route(prompt: str, task_type: str | None, complexity: str | None,
           prefer_model: str | None = None):
    """Shared core for every wire-format endpoint: classify (if needed) → route
    through Chuzom's FULL router and adapt the result.

    Routes via :func:`chuzom.route_server.route_payload` → ``route_and_call``, so
    gateway traffic gets the same budget caps, caching, paid-spend cap, and cost
    logging as the native ``/route`` endpoint (and the standalone route server).
    ``prefer_model`` (the OpenAI ``model`` field) requests a specific tier.
    """
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="no prompt content")
    if not task_type or not complexity:
        _t, _c = _classify(prompt)
        task_type, complexity = task_type or _t, complexity or _c

    from chuzom.route_server import route_payload
    try:
        out = route_payload({
            "prompt": prompt,
            "task_type": task_type,
            "complexity": complexity,
            "model": prefer_model,
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Chuzom routing failed: {e}")
    return _RoutedResult(out)


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
            "formats": ["openai", "anthropic", "ollama", "route"]}


@app.get("/health")  # alias — parity with the standalone route server
def health() -> dict:
    return {"ok": True}


# ── Native: POST /route (parity with the zero-dep route_server) ───────────────
@app.post("/route")
def route(payload: dict) -> dict:
    """Minimal native routing endpoint — same contract as ``chuzom.route_server``.

    Body: ``{"prompt", "complexity"?, "system"?, "task_type"?, "max_tokens"?,
    "temperature"?, "model"?}`` → ``{"text","model","provider","cost_usd",
    "input_tokens","output_tokens","complexity"}``. Goes through the same
    ``route_payload`` core as every other endpoint.
    """
    from chuzom.route_server import route_payload
    try:
        return route_payload(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"route failed: {e}")


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
    r = _route(_flatten(req.messages), req.task_type, req.complexity, prefer_model=req.model)
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
