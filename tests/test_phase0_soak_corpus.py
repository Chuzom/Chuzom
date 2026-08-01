"""Phase 0 Step 6 — soak corpus + schema + privacy validator.

Proves the committed `soak/corpus/v1.jsonl` (a small, SYNTHETIC-but-realistic,
pre-redacted corpus of routing-representative prompts) loads cleanly and
passes full schema + uniqueness + secret-scrubber privacy validation. This is
the CI-facing guarantee that the corpus never regresses into an invalid or
secret-leaking state (CHZ-PRV-06) — the builder that would derive rows from
real `session_store` history must never run in CI; this test only ever reads
the already-committed, already-redacted file.
"""
from __future__ import annotations

from soak.corpus_schema import (
    CORPUS_VERSION,
    DEFAULT_CORPUS_PATH,
    VALID_COMPLEXITIES,
    VALID_TASK_TYPES,
    load_corpus,
    validate_corpus,
)


def test_corpus_file_exists():
    assert DEFAULT_CORPUS_PATH.exists(), f"missing corpus file: {DEFAULT_CORPUS_PATH}"


def test_corpus_loads_without_error():
    rows = load_corpus()
    assert isinstance(rows, list)
    assert rows, "corpus must not be empty"


def test_corpus_row_count_within_brief_bounds():
    # Brief: "a small (~30-50 row)" corpus.
    rows = load_corpus()
    assert 30 <= len(rows) <= 50, f"expected 30-50 rows, got {len(rows)}"


def test_corpus_fully_valid_and_secret_free():
    rows = load_corpus()
    errors = validate_corpus(rows)
    assert errors == [], f"corpus validation errors: {errors}"


def test_corpus_ids_are_unique():
    rows = load_corpus()
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate ids found in corpus"


def test_corpus_all_rows_are_current_version():
    rows = load_corpus()
    assert all(r["corpus_version"] == CORPUS_VERSION for r in rows)


def test_corpus_covers_multiple_task_types():
    rows = load_corpus()
    seen_task_types = {r["gold_task_type"] for r in rows}
    # Sanity: the corpus should exercise more than a single task type, and
    # every value used must be a real TaskType.
    assert len(seen_task_types) >= 3
    assert seen_task_types <= VALID_TASK_TYPES


def test_corpus_covers_multiple_complexities():
    rows = load_corpus()
    seen = {r["gold_complexity"] for r in rows}
    assert len(seen) >= 2
    assert seen <= VALID_COMPLEXITIES


def test_corpus_covers_both_host_modes():
    rows = load_corpus()
    seen = {r["host_mode"] for r in rows}
    assert seen == {"subscription", "metered"}
