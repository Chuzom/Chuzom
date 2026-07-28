"""Gate 13 (#23) — mutation-coverage tests for gates.py.

These pin behaviours that a mutmut run showed were NOT exercised by the existing
gate tests (survivors in `_check_length`, `run_gates`, `_check_syntax`). Each test
targets a specific surviving mutant so the mutation score on gates.py rises toward
"all non-equivalent mutants killed".

Gates auto-skip under pytest unless CHUZOM_GATES=on (see run_gates), so where a
test needs the *real* env-branching behaviour it manipulates CHUZOM_GATES and
PYTEST_CURRENT_TEST explicitly.
"""
from __future__ import annotations

import pytest

from chuzom.contract import GateType, build_contract
from chuzom.gates import _check_length, _check_syntax, run_gates
from chuzom.types import Complexity, TaskType


def _contract(task_type=TaskType.ANALYZE, complexity=Complexity.COMPLEX):
    return build_contract("m", task_type, complexity, "test/model")


# ── _check_length boundary: kills `actual < min_len` → `actual <= min_len` ────

def test_length_gate_exact_boundary_passes():
    """A response EXACTLY at min_output_length must PASS. `<` vs `<=` differ only
    at the boundary, so this is the one input that kills the mutant."""
    c = _contract(complexity=Complexity.COMPLEX)  # min_output_length == 50
    min_len = c.constraints.min_output_length
    assert _check_length(c, "x" * min_len).passed, "exactly min chars must pass"
    r = _check_length(c, "x" * (min_len - 1))
    assert not r.passed, "one char under min must fail"
    assert "too short" in r.reason


# ── run_gates env handling ────────────────────────────────────────────────────

def test_gates_off_disables_even_without_pytest_marker(monkeypatch):
    """CHUZOM_GATES=off must disable gates via the 'off' branch specifically —
    not incidentally via the pytest-skip path. Removing PYTEST_CURRENT_TEST
    isolates the 'off' branch (kills the "off"→"XXoffXX" mutant)."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("CHUZOM_GATES", "off")
    c = build_contract("g", TaskType.CODE, Complexity.MODERATE, "test/m")
    passed, results = run_gates(c, "x")  # would fail LENGTH if gates ran
    assert passed and results == []


def test_gates_run_when_env_unset_and_not_pytest(monkeypatch):
    """With CHUZOM_GATES unset AND no pytest marker, gates RUN (not skipped, not
    crashed). Kills the `os.environ.get("CHUZOM_GATES", "")` → `, None` mutant,
    which would raise AttributeError on None.lower() when the var is unset."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("CHUZOM_GATES", raising=False)
    c = build_contract("g", TaskType.CODE, Complexity.MODERATE, "test/m")
    passed, results = run_gates(c, "x")  # too short → LENGTH fails
    assert not passed, "gates must actually run (and fail) when env is unset"
    assert results, "gate results must be produced, not skipped/crashed"


def test_gates_on_forces_run_under_pytest(monkeypatch):
    """CHUZOM_GATES=on overrides the pytest auto-skip. Pins the 'on' comparison."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")
    monkeypatch.setenv("CHUZOM_GATES", "on")
    c = build_contract("g", TaskType.CODE, Complexity.MODERATE, "test/m")
    passed, _ = run_gates(c, "x")
    assert not passed, "CHUZOM_GATES=on must force gates to run under pytest"


# ── _check_syntax code detection: case + structure ───────────────────────────

@pytest.fixture(autouse=True)
def _force_gates(monkeypatch):
    monkeypatch.setenv("CHUZOM_GATES", "on")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)


def test_syntax_gate_detects_unfenced_lowercase_code_with_error():
    """A non-fenced response whose first lines start with lowercase `def `/`return`
    is treated as code; a syntax error in it must FAIL. Kills the case-folding
    mutants (`"def "`→`"DEF "`, etc.) — with them the lowercase keywords aren't
    detected, the block is treated as prose, and the broken code slips through."""
    c = _contract(task_type=TaskType.CODE)
    broken = "def f(:\n    return 1\nfrom x import y\n"  # 3 code-indicator lines, invalid syntax
    r = _check_syntax(c, broken)
    assert not r.passed, "unfenced lowercase code with a syntax error must fail"
    assert "SyntaxError" in r.reason


def test_syntax_gate_prose_is_not_code():
    """Plain prose (no code-indicator lines) passes the syntax gate — pins the
    'non-code response' branch so a mutant flipping the indicator threshold is
    caught alongside the detection tests."""
    c = _contract(task_type=TaskType.CODE)
    r = _check_syntax(c, "This is a normal sentence. And another one here.")
    assert r.passed


# ── _check_structure (lever-① new code): kill the marker/boundary/field mutants ─

from chuzom.gates import _check_structure  # noqa: E402


def _structure_contract():
    return build_contract("s", TaskType.ANALYZE, Complexity.MODERATE, "test/m")


@pytest.mark.parametrize("marker", ["## ", "### ", "- ", "* ", "1. "])
def test_structure_each_marker_type_counts(marker):
    """A >200-char, single-paragraph, <3-sentence body structured ONLY by exactly
    two of ONE marker type must PASS. Removing that marker must FAIL. This kills
    the per-marker string mutants (`"\\n## "`→`"XX\\n## XX"`), the `+`→`-`
    marker-sum mutants, and the `markers >= 2` boundary mutants — for every
    marker kind — because the marker count is the sole reason the body is legible."""
    c = _structure_contract()
    filler = "x" * 110  # no sentence punctuation, no blank lines
    body = f"lead\n{marker}{filler}\n{marker}{filler}"
    assert len(body) > 200
    assert _check_structure(c, body).passed, f"two '{marker}' markers must structure it"
    # Strip the markers → same length-class body, now genuinely unstructured.
    unstructured = body.replace(f"\n{marker}", "\n")
    assert not _check_structure(c, unstructured).passed, \
        f"without the '{marker}' markers the wall must fail"


def test_structure_exactly_three_sentences_passes():
    """Structured ONLY by exactly 3 sentences (0 markers, 1 paragraph) must PASS —
    kills the `sentences >= 3` → `> 3` / `>= 4` mutants."""
    c = _structure_contract()
    body = (
        "This first sentence is padded with enough words to push the whole body "
        "comfortably past two hundred characters in total length here. This is the "
        "second sentence adding still more filler words for length. And a third."
    )
    assert body.count(".") == 3 and "\n" not in body and len(body) > 200
    assert _check_structure(c, body).passed


def test_structure_length_gate_boundary_exact():
    """The >200 length guard: a 200-char unstructured body PASSES (not gated), a
    201-char one FAILS. Kills `> 200` → `>= 200` and `> 200` → `> 201`."""
    c = _structure_contract()
    assert _check_structure(c, "a" * 200).passed, "exactly 200 chars must not be gated"
    assert not _check_structure(c, "a" * 201).passed, "201 unstructured chars must fail"


def test_structure_result_fields_are_populated():
    """Kill the GateResult field mutants (gate=None/passed=None/reason=None): a
    failing structure check reports gate=STRUCTURE, passed=False, non-empty reason;
    a passing one reports gate=STRUCTURE, passed=True."""
    c = _structure_contract()
    fail = _check_structure(c, "a" * 300)
    assert fail.gate == GateType.STRUCTURE
    assert fail.passed is False
    assert fail.reason and "unstructured wall" in fail.reason
    ok = _check_structure(c, "short prose. two sentences. three sentences here.")
    assert ok.gate == GateType.STRUCTURE
    assert ok.passed is True
