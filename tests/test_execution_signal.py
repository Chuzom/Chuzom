"""ENF-FIX-1 — the execution-need signal is high-precision and bidirectional.

It must FIRE on prompts whose completion needs local command execution / repo
operations (so enforcement can name the tool-capable door), and stay SILENT on
explanation, prose deliverables, and pure code-authoring (which a completion door
handles). A false positive hijacks an ordinary prompt into a heavy tool loop, so
the silent direction is tested as hard as the firing one.
"""
from __future__ import annotations

import pytest

from chuzom.execution_signal import detect_execution, needs_execution


# ── FIRES: genuine local-execution / repo-ops requests ────────────────────────

@pytest.mark.parametrize("prompt", [
    "Run the test suite and commit the passing changes.",
    "Run the database migration and apply the schema changes.",
    "git rebase onto main and push the branch.",
    "Deploy the service to the staging cluster.",
    "Bisect the commits to find the regression.",
    "Regenerate the lockfile and reinstall dependencies.",
    "Apply the migration then restart the server.",
    "Rebuild the docker image and redeploy it.",
    "Run pytest and fix whatever the suite reports.",
    "Revert the last commit on the branch.",
])
def test_fires_on_execution_requests(prompt):
    sig = detect_execution(prompt)
    assert sig.fires, f"should fire (needs local execution): {prompt!r} — {sig.reason}"
    assert sig.verb and sig.obj


# ── SILENT: explanation, prose, and pure authoring must NOT fire ──────────────

@pytest.mark.parametrize("prompt", [
    # Explanatory / interrogative lead — wants understanding, not execution.
    "Explain how to run the test suite and commit changes in git.",
    "How do I rebase onto main and push the branch?",
    "What does deploying to a Kubernetes cluster involve?",
    "Why does the migration fail when I apply it?",
    "Describe how the CI pipeline runs the tests.",
    # Prose / content deliverables that merely mention execution words.
    "Write a blog post about running tests and deploying to production.",
    "Draft a tutorial on how to rebase and merge branches in git.",
    "Write documentation for the deploy script.",
    # Pure authoring — a completion door (llm_code) handles these; no local run.
    "Write a function that sorts a list of integers.",
    "Implement a binary search and explain the complexity.",
    # Everyday false-positive bait for the generic verbs.
    "Run a marathon training plan for a beginner.",
    "Apply for a software engineering job at a startup.",
])
def test_silent_on_non_execution(prompt):
    sig = detect_execution(prompt)
    assert not sig.fires, f"should stay silent: {prompt!r} — matched {sig.verb!r}/{sig.obj!r}"


def test_needs_execution_helper_agrees():
    assert needs_execution("Run the test suite and commit the passing changes.")
    assert not needs_execution("Explain how continuous deployment works.")


def test_reason_records_matched_axes():
    """An enforced route must be able to log WHY it fired."""
    sig = detect_execution("git rebase onto main and push the branch.")
    assert sig.verb in {"rebase", "push"}
    assert sig.obj in {"git", "branch", "main"}  # first concrete anchor matched
    assert "execution verb" in sig.reason
