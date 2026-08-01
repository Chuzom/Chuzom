"""AUDIT-B Phase 7 — cross-provider within-session context capture.

Hermetic: HOME is redirected to a tmp dir BEFORE any chuzom import, so every
module-level path constant (session_spend.py, discover.py, etc.) resolves
under the tmp dir, never touching the real ~/.chuzom.

Scenario: 3 turns, each forced to a DIFFERENT provider via model_override,
all within the same resolved session_id (via $CLAUDE_SESSION_ID) and same
process (so the in-process SessionBuffer singleton is also live). We
monkeypatch providers.call_llm to capture the EXACT messages list handed to
each "provider" and print it as JSON so the parent process can inspect it.

Turn 1 -> ollama/canary-local      (local/free provider)
Turn 2 -> openai/canary-openai     (external provider)
Turn 3 -> perplexity/canary-ppx    (external provider)
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# 1. Hermetic HOME — must happen before any chuzom import.
TMP_HOME = tempfile.mkdtemp(prefix="chuzom-audit-b-phase7-")
os.environ["HOME"] = TMP_HOME
os.environ["CLAUDE_SESSION_ID"] = "audit-b-p7-session-1"
os.environ["CHUZOM_SESSION_CONTEXT"] = "all"
os.environ["CHUZOM_DISABLE_LLM_CLASSIFIERS"] = "1"
os.environ["CHUZOM_DIRECT_EXECUTION"] = "1"
os.environ["CHUZOM_ENFORCE"] = "suggest"
os.environ["CHUZOM_ZERO_CLAUDE"] = "off"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
# Force a stable cwd-independent project scope for this run.
os.environ["CHUZOM_PROJECT_ID"] = "audit-b-phase7-project"

sys.path.insert(0, "/Users/yaliandrona/Projects/Chuzom/src")

from chuzom import providers  # noqa: E402
from chuzom import router  # noqa: E402
from chuzom.types import TaskType  # noqa: E402

CAPTURED = []  # list of {"model":..., "messages":[...]}


async def _fake_call_llm(model, messages, *, temperature=None, max_tokens=None, extra_params=None):
    CAPTURED.append({"model": model, "messages": messages})
    # Return a deterministic canned response so downstream code (buffer
    # recording, session_store.record_event, cost calc) proceeds normally.
    from chuzom.types import LLMResponse
    canned = {
        "ollama/canary-local": "Noted. I will not repeat the code.",
        "openai/canary-openai": "x = <the code from before>  # variable created",
        "perplexity/canary-ppx": "We are using that value in the variable.",
    }.get(model, "ok")
    return LLMResponse(
        content=canned,
        model=model,
        input_tokens=10,
        output_tokens=10,
        cost_usd=0.0001,
        latency_ms=1.0,
        provider=model.split("/", 1)[0],
    )


async def main():
    providers.call_llm = _fake_call_llm
    router.providers.call_llm = _fake_call_llm  # router imported `providers` module directly

    turns = [
        ("ollama/canary-local", "The secret code is ORANGE-742. Don't repeat it back to me."),
        ("openai/canary-openai", "Make a python variable that holds the code from before."),
        ("perplexity/canary-ppx", "What value are we using for that variable? Just state it plainly."),
    ]

    results = []
    for model, prompt in turns:
        resp = await router.route_and_call(
            TaskType.QUERY,
            prompt,
            model_override=model,
            suppress_ledger=True,
        )
        results.append({"model": model, "prompt": prompt, "response": resp.content})

    out = {
        "tmp_home": TMP_HOME,
        "turns": results,
        "captured_payloads": CAPTURED,
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
