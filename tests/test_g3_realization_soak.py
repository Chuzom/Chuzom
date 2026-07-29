"""G3 gate — realization telemetry is complete end-to-end (CHZ-EXT-204).

Drives the REAL hooks (not just the helper): enforce-route.py on a routed
tool-call (honor → verified_used) and stop-enforce.py on a plain-text turn
(override → verified_overridden), then asserts the execution_events ledger has
ZERO NULL realization rows and a computable bypass rate. Before the fix the
ledger was 100% NULL, so a bypass run was indistinguishable from a perfect one.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENFORCE_HOOK = ROOT / "src" / "chuzom" / "hooks" / "enforce-route.py"
STOP_HOOK = ROOT / "src" / "chuzom" / "hooks" / "stop-enforce.py"

HONORS = 5
OVERRIDES = 4


def _seed_pending(home: Path, sid: str) -> None:
    now = time.time()
    pending = {
        "task_type": "query",
        "complexity": "simple",
        "method": "heuristic",
        "expected_tool": "llm_query",
        "original_prompt": "what is a monad",
        "issued_at": now,
        "expires_at": now + 3600,
        "turn_id": int(now),
        "session_id": sid,
    }
    (home / ".chuzom" / f"pending_route_{sid}.json").write_text(json.dumps(pending))


def _env(home: Path, ledger_db: Path) -> dict:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["CHUZOM_ENFORCE"] = "hard"
    env["CHUZOM_EXECUTION_LEDGER_DB"] = str(ledger_db)
    env["OPENAI_API_KEY"] = ""
    env["GEMINI_API_KEY"] = ""
    return env


def _run(hook: Path, payload: dict, env: dict) -> None:
    subprocess.run(
        [sys.executable, str(hook)], input=json.dumps(payload),
        capture_output=True, text=True, env=env, timeout=30,
    )


def _realization_rows(db: Path) -> list[sqlite3.Row]:
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute(
            "SELECT session_id, event_type, realization_status, used_by_host, accepted "
            "FROM execution_events"
        ))
    finally:
        conn.close()


def test_realization_telemetry_complete(tmp_path):
    home = tmp_path
    (home / ".chuzom").mkdir(parents=True, exist_ok=True)
    ledger = home / "ledger.db"
    env = _env(home, ledger)

    # Honor: routed tool call → enforce-route writes verified_used.
    for i in range(HONORS):
        sid = f"honor-{i}"
        _seed_pending(home, sid)
        _run(ENFORCE_HOOK, {"session_id": sid, "tool_name": "mcp__chuzom__llm_query",
                             "tool_input": {}}, env)

    # Override: plain-text turn (pending survives to Stop) → verified_overridden.
    for i in range(OVERRIDES):
        sid = f"override-{i}"
        _seed_pending(home, sid)
        _run(STOP_HOOK, {"session_id": sid}, env)

    rows = _realization_rows(ledger)
    realization_rows = [r for r in rows if r["event_type"] in
                        ("route_realized", "plain_text_override")]
    assert realization_rows, "no realization events were written by the real hooks"

    null_realization = [r for r in realization_rows if r["realization_status"] is None]
    assert not null_realization, (
        f"CHZ-EXT-204: {len(null_realization)} realization rows have NULL status"
    )

    used = sum(1 for r in realization_rows if r["realization_status"] == "verified_used")
    overridden = sum(1 for r in realization_rows if r["realization_status"] == "verified_overridden")
    assert used >= 1, "honor path wrote no verified_used"
    assert overridden >= 1, "override path wrote no verified_overridden"

    # Bypass rate is computable (the whole point of populating the ledger).
    bypass_rate = overridden / (used + overridden)
    assert 0.0 <= bypass_rate <= 1.0
    # Every realization row must carry a session_id (CHZ-PRV-06).
    assert all(r["session_id"] for r in realization_rows), "realization row missing session_id"
