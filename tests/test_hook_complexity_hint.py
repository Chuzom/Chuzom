"""Tests for the hook → MCP complexity hint bridge.

The auto-route hook writes ``~/.chuzom/last_classification.json`` on
every UserPromptSubmit. MCP llm_* tools read that file to discover the
hook's classification verdict so a short user prompt doesn't get re-
classified as moderate by the router's length heuristic after wrapping.

Tests below pin three contracts:

1. Caller-supplied complexity always wins over the hook hint.
2. Stale hint files (> 120s old) are ignored — fresh classification
   from the current turn must beat anything that lingered.
3. Malformed / partially-written hint files don't crash callers —
   the file is updated atomically, but a half-written read is still
   possible during the rename window.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from chuzom.tools.text import (
    _effective_complexity,
    _read_hook_complexity_hint,
)


@pytest.fixture
def hint_file(monkeypatch, tmp_path):
    """Redirect Path.home() so the hint reader picks up our temp file."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    chuzom_dir = tmp_path / ".chuzom"
    chuzom_dir.mkdir(parents=True, exist_ok=True)
    return chuzom_dir / "last_classification.json"


def _write_hint(path: Path, complexity: str, *, age_sec: float = 0.0) -> None:
    path.write_text(json.dumps({
        "task_type": "query",
        "complexity": complexity,
        "method": "heuristic",
        "issued_at": time.time() - age_sec,
        "session_id": "test",
    }))


# ── Reader contract ─────────────────────────────────────────────────────


def test_reader_returns_recent_hint(hint_file):
    _write_hint(hint_file, "simple")
    assert _read_hook_complexity_hint() == "simple"


def test_reader_ignores_stale_hint(hint_file):
    """A hint older than 120s must NOT be used — a previous turn's
    classification shouldn't leak into the current one."""
    _write_hint(hint_file, "simple", age_sec=200.0)
    assert _read_hook_complexity_hint() is None


def test_reader_returns_none_when_file_missing(hint_file):
    # File was never written
    assert _read_hook_complexity_hint() is None


def test_reader_swallows_malformed_json(hint_file):
    """Atomic-rename writes can race with reads; a half-written file is
    rare but possible. Reader must not propagate the exception."""
    hint_file.write_text("{not actually json")
    assert _read_hook_complexity_hint() is None


def test_reader_rejects_unknown_complexity_values(hint_file):
    """Defence against future schema drift — a hint file written by a
    newer client must not coerce the router into accepting an unknown
    bucket."""
    hint_file.write_text(json.dumps({
        "complexity": "ultra_complex",
        "issued_at": time.time(),
    }))
    assert _read_hook_complexity_hint() is None


def test_reader_handles_non_numeric_issued_at(hint_file):
    """Defence against a partial / corrupt write: issued_at must be
    numeric or the hint is ignored."""
    hint_file.write_text(json.dumps({
        "complexity": "simple",
        "issued_at": "not a number",
    }))
    assert _read_hook_complexity_hint() is None


# ── _effective_complexity priority order ───────────────────────────────


def test_caller_hint_wins(hint_file):
    """When the MCP tool was called with an explicit complexity, that
    must win — the caller knows their intent better than the hook."""
    _write_hint(hint_file, "complex")
    assert _effective_complexity("simple") == "simple"


def test_hook_hint_used_when_caller_omits(hint_file):
    _write_hint(hint_file, "simple")
    assert _effective_complexity(None) == "simple"


def test_floor_used_when_no_hint_anywhere(hint_file):
    """For ``llm_analyze`` (floor=moderate) — pure-simple is never a
    real analysis task, so falling through to None should hit the floor."""
    # No hint file written
    assert _effective_complexity(None, floor="moderate") == "moderate"


def test_caller_none_and_hook_none_returns_none(hint_file):
    """Without an analyze-style floor, missing everything returns None
    so the router's length heuristic can take over."""
    assert _effective_complexity(None) is None
