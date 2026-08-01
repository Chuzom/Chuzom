"""AUDIT-B Phase 7c — does route_and_stream() actually crash at the
build_context_messages(prompt, system_prompt, caller_context) call site
(router.py ~line 4486), which looks like a positional call against a
keyword-only async function (missing `await`, wrong call convention)?

Executes route_and_stream() for real against a monkeypatched
providers.call_llm_stream_events, in a hermetic HOME, and reports the
actual exception (if any) instead of inferring from source alone.
"""
import asyncio
import json
import os
import sys
import tempfile

TMP_HOME = tempfile.mkdtemp(prefix="chuzom-audit-b-phase7c-")
os.environ["HOME"] = TMP_HOME
os.environ["CLAUDE_SESSION_ID"] = "audit-b-p7c-session"
os.environ["CHUZOM_SESSION_CONTEXT"] = "all"
os.environ["CHUZOM_DISABLE_LLM_CLASSIFIERS"] = "1"
os.environ["CHUZOM_DIRECT_EXECUTION"] = "1"
os.environ["CHUZOM_ENFORCE"] = "suggest"
os.environ["CHUZOM_ZERO_CLAUDE"] = "off"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["CHUZOM_PROJECT_ID"] = "audit-b-phase7c-project"

sys.path.insert(0, "/Users/yaliandrona/Projects/Chuzom/src")

from chuzom import providers  # noqa: E402
from chuzom import router  # noqa: E402
from chuzom.types import TaskType  # noqa: E402


async def _fake_stream_events(model, messages, *, temperature=None, max_tokens=None, **kw):
    yield {"type": "delta", "text": "hello"}
    yield {"type": "done", "content": "hello", "cost_usd": 0.0, "input_tokens": 1, "output_tokens": 1}


async def main():
    providers.call_llm_stream_events = _fake_stream_events
    router.providers.call_llm_stream_events = _fake_stream_events

    events = []
    error = None
    error_type = None
    import traceback
    tb_text = None
    try:
        async for ev in router.route_and_stream(
            TaskType.QUERY,
            "does streaming crash on context injection?",
            model_override="openai/canary-stream",
        ):
            events.append(ev.get("type"))
    except Exception as e:  # noqa: BLE001
        error = str(e)
        error_type = type(e).__name__
        tb_text = traceback.format_exc()

    print(json.dumps({
        "events_seen_before_error": events,
        "error_type": error_type,
        "error": error,
        "traceback": tb_text,
    }, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
