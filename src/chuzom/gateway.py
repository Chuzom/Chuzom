"""OpenAI-compatible HTTP gateway — route ANY LLM client through Chuzom.

Exposes ``POST /v1/chat/completions`` (+ ``/v1/models``, ``/healthz``) and wraps
Chuzom's routing chain (``build_chain`` + ``execute_chain``). Any litellm /
openai-sdk / LangChain client routes through Chuzom by pointing at it:

    export OPENAI_BASE_URL=http://127.0.0.1:17900/v1
    export OPENAI_API_KEY=chuzom            # ignored, but clients require one

Every call is metered into ``~/.chuzom/usage.db`` + ``savings_log.jsonl`` exactly
like the in-editor hook path, so external agents (Stockagent, cron jobs, Agno
agents) finally show up in the Chuzom ledger. This is the Surface-C fix.

Run:  python -m chuzom.gateway   (or: uvicorn chuzom.gateway:app --port 17900)
"""
from __future__ import annotations

import re
import time
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from chuzom.hooks.chain_builder import build_chain, get_current_pressure
from chuzom.hooks.direct_executor import execute_chain

app = FastAPI(title="Chuzom Gateway", version="1")

_CODE = re.compile(
    r"\b(code|function|class|def |bug|refactor|implement|compile|stack ?trace|"
    r"api|sql|regex|unit test|typescript|python|rust|golang)\b",
    re.IGNORECASE,
)


class _Msg(BaseModel):
    role: str
    content: object | None = None  # str or OpenAI content-parts list


class _ChatRequest(BaseModel):
    model: str | None = None
    messages: list[_Msg]
    temperature: float | None = None
    max_tokens: int | None = None
    # task_type / complexity may be passed as hints; otherwise inferred.
    task_type: str | None = None
    complexity: str | None = None


def _flatten(messages: list[_Msg]) -> str:
    parts = []
    for m in messages:
        c = m.content
        if isinstance(c, list):  # OpenAI vision/content-parts format
            c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
        if c:
            parts.append(f"{m.role}: {c}")
    return "\n".join(parts)


def _classify(prompt: str) -> tuple[str, str]:
    """Lightweight task/complexity inference (matches the hook's tiers)."""
    task = "code" if _CODE.search(prompt) else "analyze"
    n = len(prompt)
    complexity = "complex" if n > 2000 else "moderate" if n > 400 else "simple"
    return task, complexity


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "chuzom-gateway"}


@app.get("/v1/models")
def models() -> dict:
    return {"object": "list",
            "data": [{"id": "chuzom-auto", "object": "model", "owned_by": "chuzom"}]}


@app.post("/v1/chat/completions")
def chat_completions(req: _ChatRequest) -> dict:
    prompt = _flatten(req.messages)
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="no message content")

    task = req.task_type or None
    complexity = req.complexity or None
    if not task or not complexity:
        _t, _c = _classify(prompt)
        task, complexity = task or _t, complexity or _c

    zone, _pct = get_current_pressure()
    chain = build_chain(complexity, zone, task)
    result = execute_chain(prompt, chain, task, timeout=120)
    if result is None:
        raise HTTPException(status_code=502,
                            detail="Chuzom routing failed — all models in the chain were exhausted")

    # Meter into usage.db + savings_log.jsonl (same path as the hook).
    try:
        from chuzom.hooks.savings_logger import log_direct_savings, log_direct_to_db
        log_direct_to_db(result=result, prompt=prompt, task_type=task,
                         complexity=complexity, classifier_type="gateway", session_id="gateway")
        log_direct_savings(result=result, task_type=task, complexity=complexity,
                           session_id="gateway", host="gateway")
    except Exception:
        pass  # metering is best-effort; never fail the response

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": f"{result.model.provider}/{result.model.model}",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result.text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": result.input_tokens,
            "completion_tokens": result.output_tokens,
            "total_tokens": result.input_tokens + result.output_tokens,
        },
    }


def main() -> None:
    import os

    import uvicorn
    host = os.environ.get("CHUZOM_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("CHUZOM_GATEWAY_PORT", "17900"))
    print(f"Chuzom Gateway → http://{host}:{port}/v1  (set OPENAI_BASE_URL to this)")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
