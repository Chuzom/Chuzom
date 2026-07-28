"""#24 — release-scale corpus extension (moderate2 / hard2).

Validates the new corpora load, are well-formed, and that every OBJECTIVE entry's
own reference answer grades 5 under grade_objective — i.e. the expected_contains /
expected_max_words are self-consistent (a right answer isn't accidentally failed by
too tight a word cap). Deterministic; no LLM, no metered calls. The audited baseline
(moderate/hard) is untouched, so the release benchmark stays reproducible.
"""
from __future__ import annotations

import pytest

from bench.judge import grade_objective
from bench.runner import load_corpus

EXT = ["moderate2", "hard2"]


@pytest.mark.parametrize("diff", EXT)
def test_corpus_loads_and_is_wellformed(diff):
    rows = load_corpus(diff)
    assert len(rows) >= 10, f"{diff} should have a meaningful number of prompts"
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), f"{diff} has duplicate ids"
    for r in rows:
        assert r.get("prompt", "").strip(), f"{r.get('id')} has empty prompt"
        assert r.get("kind") in ("objective", "subjective"), r.get("id")
        if r["kind"] == "objective":
            assert r.get("expected_contains"), f"{r['id']} objective needs expected_contains"
        else:
            assert r.get("judge_criteria"), f"{r['id']} subjective needs judge_criteria"


@pytest.mark.parametrize("diff", EXT)
def test_objective_reference_answers_self_grade_five(diff):
    """Every objective entry's own expected answer must grade 5 — catches a word cap
    set tighter than the reference answer it's meant to accept."""
    for r in load_corpus(diff):
        if r["kind"] != "objective":
            continue
        reference = str(r["expected_contains"][0])
        res = grade_objective(reference, r)
        assert res.score == 5, (
            f"{r['id']}: reference {reference!r} graded {res.score} "
            f"(max_words={r.get('expected_max_words')}) — {res.rationale}"
        )


def test_extension_does_not_shadow_audited_baseline():
    """The audited moderate/hard corpora are unchanged in size (reproducibility)."""
    assert len(load_corpus("moderate")) == 17
    assert len(load_corpus("hard")) == 16
