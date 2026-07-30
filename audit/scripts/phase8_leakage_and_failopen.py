"""AUDIT-B Phase 8-9 — cross-project isolation, session-id collision, and
fail-open behavior when the session_context store is corrupted/unwritable.

All in one hermetic HOME so results are directly comparable.
"""
import asyncio
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

TMP_HOME = tempfile.mkdtemp(prefix="chuzom-audit-b-phase8-")
os.environ["HOME"] = TMP_HOME
os.environ["CHUZOM_SESSION_CONTEXT"] = "all"
os.environ["CHUZOM_DISABLE_LLM_CLASSIFIERS"] = "1"
os.environ["CHUZOM_DIRECT_EXECUTION"] = "1"
os.environ["CHUZOM_ENFORCE"] = "suggest"
os.environ["CHUZOM_ZERO_CLAUDE"] = "off"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

sys.path.insert(0, "/Users/yaliandrona/Projects/Chuzom/src")

from chuzom import providers  # noqa: E402
from chuzom import router  # noqa: E402
from chuzom import session_store  # noqa: E402
from chuzom.types import TaskType  # noqa: E402

CAPTURED = []


async def _fake_call_llm(model, messages, *, temperature=None, max_tokens=None, extra_params=None):
    CAPTURED.append({"model": model, "messages": messages})
    from chuzom.types import LLMResponse
    # Must be >=20 chars or the dispatch length gate rejects it and silently
    # diverts the call through the emergency-BUDGET-fallback path instead —
    # which (per CHZ-AUD-B finding) skips session_store.record_event()
    # entirely. Use a long canned reply so we exercise the PRIMARY/normal
    # success path and get a clean read on the durable recording behavior.
    return LLMResponse(
        content=f"acknowledged and recorded for model {model} in this turn",
        model=model, input_tokens=10, output_tokens=10,
        cost_usd=0.0001, latency_ms=1.0, provider=model.split("/", 1)[0],
    )


async def main():
    providers.call_llm = _fake_call_llm
    router.providers.call_llm = _fake_call_llm

    out = {}

    # ---- Test A: cross-project isolation, SAME session_id, DIFFERENT
    # CHUZOM_PROJECT_ID. Project 1 gets a secret; Project 2 (same session_id)
    # must NOT see it if isolation holds.
    os.environ["CLAUDE_SESSION_ID"] = "shared-session-id-collision-test"
    os.environ["CHUZOM_PROJECT_ID"] = "project-alpha"
    CAPTURED.clear()
    await router.route_and_call(
        TaskType.QUERY, "Project ALPHA secret is PURPLE-999. Remember it.",
        model_override="ollama/canary-alpha", suppress_ledger=True,
    )

    os.environ["CHUZOM_PROJECT_ID"] = "project-beta"
    CAPTURED.clear()
    resp_beta = await router.route_and_call(
        TaskType.QUERY, "What secret did we just discuss?",
        model_override="ollama/canary-beta", suppress_ledger=True,
    )
    beta_payload = CAPTURED[-1]["messages"]
    out["cross_project_same_session_id"] = {
        "project_alpha_secret_leaked_into_project_beta_payload": any(
            "PURPLE-999" in m.get("content", "") for m in beta_payload
        ),
        "project_beta_payload": beta_payload,
        "project_alpha_dir_exists": (Path(TMP_HOME) / ".chuzom/projects/project-alpha").exists(),
        "project_beta_dir_exists": (Path(TMP_HOME) / ".chuzom/projects/project-beta").exists(),
        "on_disk_files_project_alpha": sorted(
            p.name for p in (Path(TMP_HOME) / ".chuzom/projects/project-alpha").glob("*")
        ) if (Path(TMP_HOME) / ".chuzom/projects/project-alpha").exists() else [],
        "on_disk_files_project_beta": sorted(
            p.name for p in (Path(TMP_HOME) / ".chuzom/projects/project-beta").glob("*")
        ) if (Path(TMP_HOME) / ".chuzom/projects/project-beta").exists() else [],
    }

    # ---- Test B: session-id collision WITHIN the same project (by-design
    # sharing expected: two different logical conversations that happen to
    # reuse the same session_id string should mix, since the store keys
    # purely on (project_id, session_id)).
    os.environ["CHUZOM_PROJECT_ID"] = "project-gamma"
    os.environ["CLAUDE_SESSION_ID"] = "reused-session-id"
    CAPTURED.clear()
    await router.route_and_call(
        TaskType.QUERY, "Conversation ONE secret is TEAL-111.",
        model_override="ollama/canary-g1", suppress_ledger=True,
    )
    # Simulate a totally different logical conversation reusing the same id.
    CAPTURED.clear()
    resp2 = await router.route_and_call(
        TaskType.QUERY, "Unrelated new conversation — what secret was mentioned?",
        model_override="ollama/canary-g2", suppress_ledger=True,
    )
    out["same_project_session_id_reuse_mixes_content"] = {
        "teal_111_present_in_second_conversation_payload": any(
            "TEAL-111" in m.get("content", "") for m in CAPTURED[-1]["messages"]
        ),
    }

    # ---- Test C: fail-open when the session_context JSONL is corrupted
    # (torn/garbage line) — does build_session_context still return cleanly
    # without raising, and does routing still succeed?
    os.environ["CHUZOM_PROJECT_ID"] = "project-corrupt"
    os.environ["CLAUDE_SESSION_ID"] = "corrupt-session"
    sid = session_store.resolve_session_id()
    path = session_store._session_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json at all\n{\"kind\": \"user_prompt\"\n", encoding="utf-8")
    corrupt_error = None
    try:
        ctx_text = session_store.build_session_context(sid, query=None)
        resp_after_corrupt = await router.route_and_call(
            TaskType.QUERY, "does routing survive a corrupt session file?",
            model_override="ollama/canary-corrupt", suppress_ledger=True,
        )
        out["fail_open_on_corrupt_jsonl"] = {
            "build_session_context_returned": repr(ctx_text),
            "routing_succeeded": True,
            "response": resp_after_corrupt.content,
        }
    except Exception as e:
        out["fail_open_on_corrupt_jsonl"] = {
            "exception_raised": f"{type(e).__name__}: {e}",
            "routing_succeeded": False,
        }

    # ---- Test D: fail-open when the session_context file/dir is read-only
    # (permission denied on write).
    os.environ["CHUZOM_PROJECT_ID"] = "project-readonly"
    os.environ["CLAUDE_SESSION_ID"] = "readonly-session"
    ro_sid = session_store.resolve_session_id()
    ro_path = session_store._session_path(ro_sid)
    ro_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(ro_path.parent, stat.S_IRUSR | stat.S_IXUSR)  # r-x, no write
    try:
        resp_ro = await router.route_and_call(
            TaskType.QUERY, "does routing survive a read-only session dir?",
            model_override="ollama/canary-readonly", suppress_ledger=True,
        )
        out["fail_open_on_readonly_dir"] = {
            "routing_succeeded": True,
            "response": resp_ro.content,
        }
    except Exception as e:
        out["fail_open_on_readonly_dir"] = {
            "exception_raised": f"{type(e).__name__}: {e}",
            "routing_succeeded": False,
        }
    finally:
        os.chmod(ro_path.parent, stat.S_IRWXU)  # restore so tmp cleanup works

    out["tmp_home"] = TMP_HOME
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
