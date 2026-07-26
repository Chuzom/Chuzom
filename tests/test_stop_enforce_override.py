"""B7 / INV-ENF-002/003: a plain-text override updates realization accounting.

Before the fix, stop-enforce.py detected a plain-text bypass (Claude answered a
routed Q&A prompt directly, no tool call) but only wrote a strike/log line — it never
touched session_spend or any savings accounting, so realized_savings_usd overcounted.
This proves _record_override now (a) increments session_spend.overridden_turns and
(b) emits a canonical plain_text_override ledger event with verified_overridden.

Hermetic: ledger points at a tmp DB; session_spend is a controlled in-memory instance.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HOOK =Path(__file__).resolve().parent.parent / "src" / "chuzom" / "hooks" / "stop-enforce.py"


def _load_stop_enforce():
    spec = importlib.util.spec_from_file_location("stop_enforce_mod", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plain_text_override_updates_session_spend_and_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUZOM_EXECUTION_LEDGER_DB", str(tmp_path / "usage.db"))
    from chuzom import execution_ledger
    from chuzom.session_spend import SessionSpend

    spend = SessionSpend()
    spend.prompt_sequence = 7
    assert spend.overridden_turns == 0

    # Route _record_override's lazy get_session_spend() to our controlled instance.
    import chuzom.session_spend as ss
    monkeypatch.setattr(ss, "get_session_spend", lambda: spend)

    mod = _load_stop_enforce()
    mod._record_override("sess-b7", "query")

    # (a) realization accounting updated — parity with the tool-call override path.
    assert spend.overridden_turns == 1
    assert spend.last_overridden_seq == 7

    # (b) canonical ledger carries the override event.
    rows = execution_ledger._load_rows("session_id = ?", ("sess-b7",))
    ev = [r for r in rows if r["event_type"] == "plain_text_override"]
    assert len(ev) == 1
    assert ev[0]["override_type"] == "plain_text"
    assert ev[0]["realization_status"] == "verified_overridden"
    assert ev[0]["used_by_host"] == 0  # False


def test_record_override_is_fail_open(tmp_path, monkeypatch):
    """A hook must never raise: if session_spend blows up, override still no-ops cleanly."""
    monkeypatch.setenv("CHUZOM_EXECUTION_LEDGER_DB", str(tmp_path / "usage.db"))
    import chuzom.session_spend as ss

    def _boom():
        raise RuntimeError("spend backend down")

    monkeypatch.setattr(ss, "get_session_spend", _boom)
    mod = _load_stop_enforce()
    # Must not raise despite the session_spend failure.
    mod._record_override("sess-fail", "analyze")
    # Ledger event still recorded (independent try/except).
    from chuzom import execution_ledger
    rows = execution_ledger._load_rows("session_id = ?", ("sess-fail",))
    assert any(r["event_type"] == "plain_text_override" for r in rows)


def test_dedup_same_prompt_sequence_counts_once(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUZOM_EXECUTION_LEDGER_DB", str(tmp_path / "usage.db"))
    from chuzom.session_spend import SessionSpend

    spend = SessionSpend()
    spend.prompt_sequence = 3
    import chuzom.session_spend as ss
    monkeypatch.setattr(ss, "get_session_spend", lambda: spend)

    mod = _load_stop_enforce()
    mod._record_override("s", "query")
    mod._record_override("s", "query")  # same prompt_sequence → deduped
    assert spend.overridden_turns == 1
