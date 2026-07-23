"""P6 — the canonical context-dependent signal shared by advisory + enforcement.

A context-dependent prompt is exempted from hard-blocking (enforce-route.py) and
gets the advisory note (auto-route.py) — both now read this one function, so a
prompt flagged by one is guaranteed handled by the other.
"""
from __future__ import annotations

import pytest

from chuzom.context_signal import is_context_dependent

CONTEXT_DEPENDENT = [
    "run the tests",
    "fix the bug in the parser",
    "why does the dashboard not update",
    "restart the server",
    "stop the rest",
    "run it",
    "what does this do",
    "as we discussed earlier",
    "in the previous session",
    "check /Users/me/proj/app.py",
    "look at src/chuzom/server.py",
    "delete the merged branch",
]

ROUTABLE = [
    "what is the capital of France",
    "explain how SQLite WAL mode works",
    "write a regex for email addresses",
    "translate 'good morning' into Spanish",
    "summarize the theory of relativity in two sentences",
    "what are the five love languages",
]


@pytest.mark.parametrize("prompt", CONTEXT_DEPENDENT)
def test_context_dependent_prompts_detected(prompt):
    assert is_context_dependent(prompt) is True


@pytest.mark.parametrize("prompt", ROUTABLE)
def test_routable_prompts_not_flagged(prompt):
    # these are self-contained knowledge/generation tasks a stateless model CAN do
    assert is_context_dependent(prompt) is False


def test_empty_and_whitespace_safe():
    assert is_context_dependent("") is False
    assert is_context_dependent("   ") is False


def test_enforcement_hook_imports_the_shared_signal():
    """The enforce-route hook references chuzom.context_signal (parity guarantee)."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "src" / "chuzom" / "hooks" / "enforce-route.py").read_text()
    assert "from chuzom.context_signal import is_context_dependent" in src
    assert "CTX_DEP_EXEMPT" in src
