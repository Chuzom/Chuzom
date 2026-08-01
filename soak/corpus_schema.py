"""Schema + validation for the Phase 0 realized-savings soak corpus.

The corpus (``soak/corpus/v1.jsonl``) is a small, SYNTHETIC-but-realistic,
pre-redacted set of routing-representative prompts. It is committed to the
repo and read directly in CI -- the builder that would derive a corpus from
real ``session_store`` history must NEVER run in CI (privacy: CHZ-PRV-06).

Every row is validated against this schema (required fields + enum
membership) and against ``chuzom.secret_scrubber`` (no credential-shaped
substring survives untouched) before it is trusted by ``replay.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chuzom.secret_scrubber import scrub_text
from chuzom.types import Complexity, TaskType

CORPUS_VERSION = "v1"

REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "prompt",
    "gold_task_type",
    "gold_answer",
    "host_mode",
    "gold_complexity",
    "source",
    "corpus_version",
)

VALID_TASK_TYPES = frozenset(t.value for t in TaskType)
VALID_COMPLEXITIES = frozenset(c.value for c in Complexity)
VALID_HOST_MODES = frozenset({"subscription", "metered"})

# Fields whose string content is checked for secret-shaped substrings. Every
# free-text field a human (or a scraped session) could have populated with a
# credential -- "source" is a fixed enum-ish label, not free text, so it's
# excluded to avoid false positives on legitimate short labels.
_PRIVACY_CHECKED_FIELDS: tuple[str, ...] = ("id", "prompt", "gold_answer")

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parent / "corpus" / "v1.jsonl"


@dataclass(frozen=True)
class CorpusRow:
    id: str
    prompt: str
    gold_task_type: str
    gold_answer: str
    host_mode: str
    gold_complexity: str
    source: str
    corpus_version: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CorpusRow":
        return cls(**{k: d[k] for k in REQUIRED_FIELDS})


def validate_row(row: dict[str, Any]) -> list[str]:
    """Return a list of validation error strings; empty list == valid."""
    errors: list[str] = []

    missing = [f for f in REQUIRED_FIELDS if f not in row]
    if missing:
        errors.append(f"row missing required fields: {missing}")
        return errors  # further checks would KeyError

    if not isinstance(row["id"], str) or not row["id"]:
        errors.append("id must be a non-empty string")
    if not isinstance(row["prompt"], str) or not row["prompt"].strip():
        errors.append("prompt must be a non-empty string")
    if not isinstance(row["gold_answer"], str) or not row["gold_answer"].strip():
        errors.append("gold_answer must be a non-empty string")
    if not isinstance(row["source"], str) or not row["source"]:
        errors.append("source must be a non-empty string")

    if row["gold_task_type"] not in VALID_TASK_TYPES:
        errors.append(
            f"gold_task_type {row['gold_task_type']!r} not in {sorted(VALID_TASK_TYPES)}"
        )
    if row["gold_complexity"] not in VALID_COMPLEXITIES:
        errors.append(
            f"gold_complexity {row['gold_complexity']!r} not in {sorted(VALID_COMPLEXITIES)}"
        )
    if row["host_mode"] not in VALID_HOST_MODES:
        errors.append(f"host_mode {row['host_mode']!r} not in {sorted(VALID_HOST_MODES)}")
    if row["corpus_version"] != CORPUS_VERSION:
        errors.append(
            f"corpus_version {row['corpus_version']!r} != expected {CORPUS_VERSION!r}"
        )

    return errors


def privacy_errors(row: dict[str, Any]) -> list[str]:
    """Secret-scrub every free-text field; a field is "clean" iff
    ``scrub_text`` is idempotent on it (no secret-shaped pattern matched)."""
    errors: list[str] = []
    for field in _PRIVACY_CHECKED_FIELDS:
        value = row.get(field)
        if not isinstance(value, str):
            continue
        scrubbed = scrub_text(value)
        if scrubbed != value:
            errors.append(f"field {field!r} on row {row.get('id')!r} contains a secret pattern")
    return errors


def load_corpus(path: Path | None = None) -> list[dict[str, Any]]:
    """Load + parse the jsonl corpus. Does NOT validate -- call
    ``validate_corpus`` separately so callers can choose to fail loudly."""
    p = path or DEFAULT_CORPUS_PATH
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{p}:{line_no}: invalid JSON: {e}") from e
    return rows


def validate_corpus(rows: list[dict[str, Any]]) -> list[str]:
    """Validate schema + uniqueness + privacy across the whole corpus.
    Returns a flat list of error strings; empty == fully valid."""
    errors: list[str] = []
    seen_ids: set[str] = set()

    if not rows:
        return ["corpus is empty"]

    for row in rows:
        row_id = row.get("id", "<missing-id>")
        for err in validate_row(row):
            errors.append(f"{row_id}: {err}")
        for err in privacy_errors(row):
            errors.append(err)
        if row_id in seen_ids:
            errors.append(f"{row_id}: duplicate id")
        seen_ids.add(row_id)

    return errors
