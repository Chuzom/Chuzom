"""AUDIT-B Phase 7b — does the secret survive buffer eviction + a process
restart, once it's no longer among the 3 newest durable records and no
longer shares a keyword with the final query?

Takes TMP_HOME as argv[1] so it can be pointed at the SAME hermetic HOME
used by phase7_cross_provider.py (same session_id, same project) to prove
whether the durable JSONL (not the in-process buffer, which resets here
because this is a fresh process = fresh SessionBuffer singleton) still
carries the secret forward.

Usage: python phase7b_buffer_eviction_and_restart.py <tmp_home_dir>
"""
import asyncio
import json
import os
import sys

TMP_HOME = sys.argv[1]
os.environ["HOME"] = TMP_HOME
os.environ["CLAUDE_SESSION_ID"] = "audit-b-p7-session-1"  # SAME session as phase7
os.environ["CHUZOM_SESSION_CONTEXT"] = "all"
os.environ["CHUZOM_DISABLE_LLM_CLASSIFIERS"] = "1"
os.environ["CHUZOM_DIRECT_EXECUTION"] = "1"
os.environ["CHUZOM_ENFORCE"] = "suggest"
os.environ["CHUZOM_ZERO_CLAUDE"] = "off"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["CHUZOM_PROJECT_ID"] = "audit-b-phase7-project"  # SAME project

sys.path.insert(0, "/Users/yaliandrona/Projects/Chuzom/src")

from chuzom import providers  # noqa: E402
from chuzom import router  # noqa: E402
from chuzom.types import TaskType  # noqa: E402

CAPTURED = []


async def _fake_call_llm(model, messages, *, temperature=None, max_tokens=None, extra_params=None):
    CAPTURED.append({"model": model, "messages": messages})
    from chuzom.types import LLMResponse
    return LLMResponse(
        content=f"[canned reply from {model}]",
        model=model, input_tokens=10, output_tokens=10,
        cost_usd=0.0001, latency_ms=1.0, provider=model.split("/", 1)[0],
    )


async def main():
    providers.call_llm = _fake_call_llm
    router.providers.call_llm = _fake_call_llm

    # This is a FRESH process: prove the in-process buffer is empty here
    # (new SessionBuffer singleton) before doing anything.
    from chuzom.context import get_session_buffer
    fresh_buffer_count_before = get_session_buffer().message_count

    # 4 filler exchanges (unrelated topic, no shared keywords with "code")
    # to push the ORANGE-742 record out of both:
    #   (a) the in-process buffer's last-5-messages window (irrelevant here
    #       since this is a fresh process anyway), and
    #   (b) the durable JSONL's "3 newest unconditionally" window.
    filler_prompts = [
        "What's a good pasta recipe for four people?",
        "Explain how TCP handshakes work in three sentences.",
        "List three benefits of unit testing.",
        "Summarize the plot of Romeo and Juliet in one sentence.",
    ]
    for i, p in enumerate(filler_prompts):
        await router.route_and_call(
            TaskType.QUERY, p,
            model_override="openai/canary-filler",
            suppress_ledger=True,
        )

    # Final question: deliberately uses the word "code" so it WOULD match
    # the original "The secret code is ORANGE-742..." record via the
    # durable layer's keyword-overlap fallback, if that record is still
    # anywhere in the (capped at 200, most-recent-first-loaded) event log.
    final_resp = await router.route_and_call(
        TaskType.QUERY,
        "Going back to the very start of our conversation — what was that secret code again?",
        model_override="anthropic/canary-final",
        suppress_ledger=True,
    )

    out = {
        "fresh_buffer_count_before_any_call_this_process": fresh_buffer_count_before,
        "final_response": final_resp.content,
        "final_payload_messages": CAPTURED[-1]["messages"],
        "orange_742_present_in_final_payload": any(
            "ORANGE-742" in m.get("content", "") for m in CAPTURED[-1]["messages"]
        ),
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
