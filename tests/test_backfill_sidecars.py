"""Tests for scripts/backfill_sidecars.py — replay JSON sidecars into routing_decisions."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Make ``scripts/`` importable for tests.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from backfill_sidecars import SidecarRecord, backfill  # noqa: E402


def _write_sidecar(
    directory: Path,
    *,
    session_id: str,
    task_type: str,
    complexity: str,
    tool: str,
    saved_at: float,
) -> Path:
    path = directory / f"last_route_{session_id}.json"
    path.write_text(json.dumps({
        "task_type": task_type,
        "complexity": complexity,
        "tool": tool,
        "saved_at": saved_at,
    }))
    return path


def _count_backfilled_rows(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM routing_decisions "
            "WHERE reason_code = 'sidecar_backfill'"
        ).fetchone()
        return int(row[0])
    finally:
        conn.close()


def test_sidecar_record_parses_well_formed_file(tmp_path):
    path = _write_sidecar(
        tmp_path,
        session_id="abcd1234",
        task_type="code",
        complexity="moderate",
        tool="llm_code",
        saved_at=1_780_000_000.5,
    )
    record = SidecarRecord.from_path(path)
    assert record is not None
    assert record.session_id == "abcd1234"
    assert record.task_type == "code"
    assert record.complexity == "moderate"
    assert record.tool == "llm_code"
    assert record.saved_at == pytest.approx(1_780_000_000.5)
    assert record.correlation_id == "sidecar:abcd1234:1780000000.5"
    # ISO timestamp parses back to the same epoch
    assert "2026" in record.iso_timestamp


def test_sidecar_record_returns_none_for_malformed(tmp_path):
    path = tmp_path / "last_route_bad.json"
    path.write_text("{not json")
    assert SidecarRecord.from_path(path) is None


def test_sidecar_record_returns_none_for_missing_fields(tmp_path):
    path = tmp_path / "last_route_partial.json"
    path.write_text(json.dumps({"task_type": "code"}))
    assert SidecarRecord.from_path(path) is None


@pytest.mark.asyncio
async def test_backfill_inserts_rows(tmp_path, temp_db):
    _write_sidecar(
        tmp_path, session_id="sess1", task_type="code",
        complexity="moderate", tool="llm_code",
        saved_at=1_780_000_000.0,
    )
    _write_sidecar(
        tmp_path, session_id="sess2", task_type="research",
        complexity="complex", tool="llm_research",
        saved_at=1_780_000_100.0,
    )

    report = await backfill(tmp_path)

    assert report.scanned == 2
    assert report.inserted == 2
    assert report.skipped_duplicate == 0
    assert report.skipped_malformed == 0

    from chuzom.config import get_config
    db_path = get_config().chuzom_db_path
    assert _count_backfilled_rows(db_path) == 2


@pytest.mark.asyncio
async def test_backfill_is_idempotent(tmp_path, temp_db):
    """Re-running the backfill must not double-insert."""
    _write_sidecar(
        tmp_path, session_id="sess1", task_type="code",
        complexity="moderate", tool="llm_code",
        saved_at=1_780_000_000.0,
    )

    first = await backfill(tmp_path)
    second = await backfill(tmp_path)

    assert first.inserted == 1
    assert second.inserted == 0
    assert second.skipped_duplicate == 1

    from chuzom.config import get_config
    db_path = get_config().chuzom_db_path
    assert _count_backfilled_rows(db_path) == 1, (
        "Second backfill must not produce duplicate rows"
    )


@pytest.mark.asyncio
async def test_backfill_dry_run_writes_nothing(tmp_path, temp_db):
    _write_sidecar(
        tmp_path, session_id="sess1", task_type="code",
        complexity="moderate", tool="llm_code",
        saved_at=1_780_000_000.0,
    )

    report = await backfill(tmp_path, dry_run=True)
    assert report.inserted == 1  # counted, not persisted

    from chuzom.config import get_config
    db_path = get_config().chuzom_db_path
    assert _count_backfilled_rows(db_path) == 0


@pytest.mark.asyncio
async def test_backfill_skips_malformed_sidecars(tmp_path, temp_db):
    (tmp_path / "last_route_bad.json").write_text("{nope")
    _write_sidecar(
        tmp_path, session_id="good", task_type="code",
        complexity="moderate", tool="llm_code",
        saved_at=1_780_000_000.0,
    )

    report = await backfill(tmp_path)

    assert report.scanned == 2
    assert report.inserted == 1
    assert report.skipped_malformed == 1
