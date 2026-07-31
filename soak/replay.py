"""Phase 0 Step 7 -- replay the soak corpus through the real dispatch path.

Drives ``chuzom.router.route_and_call`` once per corpus row under full
hermetic mocking (no live API keys, no live classifier when
``use_gold_complexity=True``), then closes the loop on realization:

  1. The call itself writes the normal billable ``attempt_completed`` row
     (with ``baseline_equivalent_cost_usd`` / ``classifier_cost_usd`` /
     ``baseline_tokens`` already populated by the Step 3/5 write sites).
  2. Since ``route_and_call`` does not accept a caller-supplied
     ``correlation_id`` (route ids are generated internally), the harness
     reads back the route_id it was assigned via a direct SQL lookback on the
     shared temp ledger DB (mirrors ``tests/test_phase0_quota_tokens.py``).
  3. The response content is scored against ``gold_answer`` (token-overlap
     quality_score in [0, 1]).
  4. A ``route_realized`` event is written for that route_id, using the same
     event shape as ``enforce-route.py::_record_realization_used`` /
     ``_record_agent_marked`` (see that module for the canonical pattern):
       * quality gate passes, not sampled as an override -> verified_used +
         agent_marked (counts toward realized savings, per _COUNTS_AS_REALIZED)
       * quality gate passes, sampled as an override (``override_fraction``)
         -> verified_overridden (does NOT count -- mirrors a host bypass)
       * quality gate fails -> realization_status="unknown" (does NOT count)

# TODO(phase-0.5): this harness manufactures adoption evidence itself (the
# soak *is* both the "host" and the "agent" observing its own routes). The
# production hook<->router route_id reconciliation and a real adoption
# transport are out of scope for Phase 0 -- see phase0_brief.md's approved
# scope decisions #1 and #3.
"""

from __future__ import annotations

import hashlib
import random
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from chuzom.cost import _codex_cost
from chuzom.execution_ledger import LedgerEvent, get_session_accounting, record_event
from chuzom.quality_feedback import reset_quality_store
from chuzom.types import LLMResponse, RoutingProfile, TaskType

# Quality gate: fraction of gold_answer tokens that must appear in the routed
# response for the row to be treated as a quality "pass". Deliberately loose
# (word-overlap, not exact match) -- this is a soak-level adoption proxy, not
# a precision quality benchmark.
GATE_THRESHOLD = 0.4
# Phase 0.1 FIX 4c (bugfix): a LOWER secondary threshold used only to estimate
# gate_false_negative_rate. Semantics: a row that failed the primary
# GATE_THRESHOLD gate but still cleared this looser floor is "probably not
# garbage, just below our official cutoff" -- a candidate false negative. This
# must be strictly BELOW GATE_THRESHOLD: the original value here (0.75, ABOVE
# GATE_THRESHOLD) made `quality_score < GATE_THRESHOLD and quality_score >=
# _floor` mathematically unsatisfiable whenever the floor exceeds the gate --
# gate_false_negative_rate was silently pinned to a fake, structural 0.0 for
# every possible corpus, never a real per-row measurement.
_LENIENT_FLOOR_THRESHOLD = 0.15
# Fraction of gate-passing rows that are (deterministically, seeded) treated
# as if the host/agent overrode the route instead of adopting it -- gives the
# report a non-trivial (not 100%-adopted) adoption_unknown_fraction / mix.
DEFAULT_OVERRIDE_FRACTION = 0.1


class EnvPatcher:
    """Minimal pytest-``monkeypatch``-compatible env patcher (``setenv`` /
    ``delenv``) for non-pytest callers -- specifically the ``chuzom soak`` CLI
    (Step 8), which has no pytest fixture to hand ``replay_corpus``. Restores
    every touched var via ``undo()``."""

    def __init__(self) -> None:
        self._saved: dict[str, str | None] = {}

    def setenv(self, key: str, value: str) -> None:
        import os

        self._saved.setdefault(key, os.environ.get(key))
        os.environ[key] = value

    def delenv(self, key: str, raising: bool = True) -> None:
        import os

        self._saved.setdefault(key, os.environ.get(key))
        os.environ.pop(key, None)

    def undo(self) -> None:
        import os

        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._saved.clear()


class _ReplayCfg:
    """Minimal get_config() stand-in, mirrors tests/test_phase0_quota_tokens.py::_Cfg."""

    chuzom_claude_subscription = False
    chuzom_gemini_subscription = False
    chuzom_claw_code = False
    chuzom_routing_policy = "balanced"
    chuzom_agentic_model = ""
    chuzom_profile = RoutingProfile.BALANCED
    chuzom_monthly_budget = 0.0
    chuzom_daily_spend_limit = 0.0
    chuzom_escalate_above = 0.0
    chuzom_hard_stop_above = 0.0
    codex_daily_limit = 1000
    compaction_mode = "off"
    compaction_threshold = 4000
    prompt_cache_enabled = False
    prompt_cache_min_tokens = 1024
    context_enabled = False
    caveman_mode = "off"
    available_providers = {"openai"}

    def all_ollama_models(self):
        return []

    def all_openai_compat_models(self):
        return []


@dataclass
class RowResult:
    """Everything the report needs about one replayed corpus row."""

    row_id: str
    host_mode: str
    route_id: str | None
    quality_score: float
    quality_delta: float
    gate_pass: bool
    gate_false_negative: bool
    realization_status: str
    adoption_method: str | None
    dispatch_failed: bool
    net_realized_savings_usd: float = 0.0
    realized_quota_tokens_saved: int = 0


@dataclass
class ReplayRun:
    corpus_version: str
    results: list[RowResult] = field(default_factory=list)
    ledger_path: Path | None = None
    period_start_ts: float = 0.0
    period_end_ts: float = 0.0


def _degraded_answer(gold_answer: str, rng: random.Random) -> str:
    """Phase 0.1 FIX 4c: return a stub reply with realistic, seeded variation
    in fidelity to ``gold_answer`` instead of an always-perfect echo.

    Before this fix ``stub_call`` echoed ``gold_answer`` verbatim for every
    row, which forces ``quality_score == 1.0`` (and therefore
    ``quality_delta == 0``, ``gate_false_negative_rate == 0``) for the whole
    corpus -- fake constants dressed up as measurements, not real signal.
    This introduces three deterministic (seeded) fidelity buckets so those
    metrics actually vary with the input, the way a real model's output
    quality would:

      * ~55% faithful replies (full gold content -- the routed model nailed it)
      * ~30% partial replies (50-80% of gold tokens kept, in order -- mostly
        right, some gaps -- exercises quality_delta > 0 while still passing
        the GATE_THRESHOLD gate)
      * ~15% degraded replies (5-20% of gold tokens kept -- exercises the
        gate-fail path; the upper end of that range clears
        _LENIENT_FLOOR_THRESHOLD while still failing GATE_THRESHOLD, giving
        gate_false_negative_rate real per-row signal instead of a fake 0)

    Word-subset, not exact-match corruption, so this is representative noise
    (a model that got "most of it" or "little of it"), not adversarial
    substitution.
    """
    words = gold_answer.split()
    if not words:
        return gold_answer
    roll = rng.random()
    if roll < 0.55:
        return gold_answer
    if roll < 0.85:
        keep_frac = rng.uniform(0.5, 0.8)
    else:
        keep_frac = rng.uniform(0.05, 0.2)
    keep_n = max(1, int(len(words) * keep_frac))
    kept_idx = sorted(rng.sample(range(len(words)), keep_n))
    return " ".join(words[i] for i in kept_idx)


def _quality_score(response_text: str, gold_answer: str) -> float:
    """Word-overlap ratio: fraction of gold_answer's distinct tokens that
    appear (case-insensitively) somewhere in the response. [0, 1]."""
    gold_tokens = {t for t in gold_answer.lower().split() if t}
    if not gold_tokens:
        return 0.0
    resp_tokens = set(response_text.lower().split())
    hit = sum(1 for t in gold_tokens if t in resp_tokens)
    return hit / len(gold_tokens)


def _accepted_route_id(ledger_path: Path, session_id: str) -> str | None:
    """Phase 0.1 FIX 4a: a successful route can end its life two different
    ways in the ledger, and both must count as "accepted" here:

      1. The normal per-attempt path writes ``attempt_completed`` with
         ``accepted = 1``.
      2. The exhaustion-floor success path (router.py's
         ``_emit_ledger_terminal(correlation_id, "accepted",
         route_succeeded=True)`` around the chain-exhaustion fallback) writes
         only a single ``route_completed`` row with
         ``terminal_state = 'accepted'`` -- it does NOT also write an
         ``attempt_completed accepted=1`` row for that same route.

    Before this fix, rows dispatched via the exhaustion-floor path looked
    like a dispatch failure to the soak harness (no matching route_id found),
    even though the route genuinely succeeded -- inflating
    ``soak_dispatch_failure_rate`` with harness artifacts rather than real
    failures.
    """
    conn = sqlite3.connect(str(ledger_path))
    try:
        rows = list(conn.execute(
            "SELECT route_id, turn_id FROM execution_events "
            "WHERE session_id = ? AND ("
            "  (event_type = 'attempt_completed' AND accepted = 1)"
            "  OR (event_type = 'route_completed' AND terminal_state = 'accepted')"
            ") "
            "ORDER BY ts DESC LIMIT 1",
            (session_id,),
        ))
    finally:
        conn.close()
    if not rows:
        return None
    return rows[0][0]


async def _call_row(
    row: dict[str, Any],
    *,
    session_id: str,
    ledger_path: Path,
    routing_ledger_path: Path,
    monkeypatch,
    use_gold_complexity: bool,
    rng: random.Random,
) -> tuple[str | None, str]:
    """Drive one route_and_call() for a corpus row. Returns
    (route_id_or_None, response_content_or_error_marker)."""
    monkeypatch.setenv("CHUZOM_ROUTING_LEDGER", str(routing_ledger_path))
    monkeypatch.setenv("CHUZOM_BANDIT", "off")
    monkeypatch.setenv("CHUZOM_EXECUTION_LEDGER_DB", str(ledger_path))
    monkeypatch.setenv("CHUZOM_SESSION_ID", session_id)
    if row["host_mode"] == "subscription":
        monkeypatch.delenv("CHUZOM_CLAUDE_SUBSCRIPTION", raising=False)
    else:
        monkeypatch.setenv("CHUZOM_CLAUDE_SUBSCRIPTION", "0")

    gold_answer = row["gold_answer"]

    async def stub_call(model, messages, **kwargs):
        # Hermetic stand-in for a real provider call. Phase 0.1 FIX 4c:
        # reply fidelity is seeded-random (see _degraded_answer), not always
        # a perfect echo, so quality_score/quality_delta have real per-row
        # variation instead of being a constant 1.0/0.0 for the whole corpus.
        content = _degraded_answer(gold_answer, rng)
        input_tokens = max(1, len(row["prompt"].split()))
        output_tokens = max(1, len(content.split()))
        # Phase 0.1 FIX 2: derive cost_usd from REAL per-token pricing for the
        # model the router actually selected, times the real token counts --
        # not a flat stub value. `model` arrives as the full chain string
        # (e.g. "openai/gpt-4o-mini"); OPENAI_RATES_PER_M is keyed by the
        # bare model name, so strip the provider prefix before lookup.
        # Unknown models fall back to _codex_cost's own 0.0 (never fabricate
        # a rate we don't have).
        bare_model = model.rsplit("/", 1)[-1]
        cost_usd = _codex_cost(bare_model, input_tokens, output_tokens)
        return LLMResponse(
            content=f"{content} (routed reply)",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=8.0,
            provider="openai",
        )

    tracker = MagicMock()
    tracker.is_healthy.return_value = True
    mock_log = MagicMock()
    mock_log.bind.return_value = MagicMock()

    from chuzom.router import route_and_call

    complexity_hint = row["gold_complexity"] if use_gold_complexity else None

    try:
        with (
            patch("chuzom.router.get_config", return_value=_ReplayCfg()),
            patch("chuzom.router._build_and_filter_chain", new_callable=AsyncMock,
                  return_value=["openai/gpt-4o-mini"]),
            patch("chuzom.router.providers.call_llm", new_callable=AsyncMock,
                  side_effect=stub_call),
            patch("chuzom.router.get_tracker", return_value=tracker),
            patch("chuzom.router.log", mock_log),
            patch("chuzom.router._native_notify", lambda *a, **k: None),
            patch("chuzom.router.cost.get_monthly_spend", new_callable=AsyncMock, return_value=0.0),
            patch("chuzom.router.cost.get_daily_spend", new_callable=AsyncMock, return_value=0.0),
            patch("chuzom.router.cost.get_daily_spend_by_task_type", new_callable=AsyncMock, return_value=0.0),
            patch("chuzom.router.cost.log_usage", new_callable=AsyncMock),
            patch("chuzom.router.reserve_envelope", new_callable=AsyncMock, return_value=(None, True, None)),
            patch("chuzom.router.commit_envelope", new_callable=AsyncMock),
            patch("chuzom.router.release_envelope", new_callable=AsyncMock),
            patch("chuzom.semantic_cache.check", new_callable=AsyncMock, return_value=None),
            patch("chuzom.semantic_cache.store", new_callable=AsyncMock),
        ):
            resp = await route_and_call(
                TaskType(row["gold_task_type"]),
                row["prompt"],
                profile=RoutingProfile.BALANCED,
                complexity_hint=complexity_hint,
                # Honest classifier cost: this harness never invokes a live,
                # billed classifier. With use_gold_complexity=True the
                # corpus's gold_complexity is used directly as complexity_hint
                # (highest-priority branch in _resolve_profile_and_complexity,
                # router.py ~982) -- no classification call happens at all.
                # Even with use_gold_complexity=False (the --full opt-in
                # path), complexity_hint=None falls through to
                # chuzom.classify's "deterministic, 0-cost, 0-latency"
                # heuristic (classify.py), never a real LLM classifier call.
                # A nonzero stub here would fabricate spend for a call that
                # never happened -- mirrors ClassificationResult's own
                # zero-cost fallback convention (classifier.py:320).
                classification_data={"classifier_cost_usd": 0.0},
            )
        route_id = _accepted_route_id(ledger_path, session_id)
        return route_id, resp.content
    except Exception as exc:  # noqa: BLE001 -- dispatch failure is a scored outcome, not a crash
        return None, f"__DISPATCH_FAILED__:{exc}"


def _write_realization(
    *,
    ledger_path: Path,
    session_id: str,
    route_id: str,
    task_type: str,
    realization_status: str,
    adoption_method: str | None,
) -> None:
    """Mirrors enforce-route.py::_record_realization_used / _record_agent_marked:
    content-stable event_id (idempotent under INSERT OR IGNORE), fail-open."""
    try:
        eid_salt = f"{session_id}|{route_id}|route_realized|{adoption_method or 'none'}"
        eid = hashlib.sha256(eid_salt.encode()).hexdigest()[:32]
        record_event(
            LedgerEvent(
                event_id=eid,
                session_id=session_id,
                route_id=route_id,
                event_type="route_realized",
                task_type=task_type,
                realization_status=realization_status,
                adoption_method=adoption_method,
                used_by_host=(realization_status == "verified_used"),
                accepted=True,
            ),
            path=ledger_path,
        )
    except Exception:  # noqa: BLE001 -- realization accounting must never break the soak
        pass


async def replay_corpus(
    rows: list[dict[str, Any]],
    *,
    ledger_path: Path,
    routing_ledger_dir: Path,
    monkeypatch,
    use_gold_complexity: bool = True,
    override_fraction: float = DEFAULT_OVERRIDE_FRACTION,
    seed: int = 0,
) -> ReplayRun:
    """Replay every corpus row once. Returns a ReplayRun with one RowResult
    per row plus the ledger path the caller can pass to
    ``chuzom.execution_ledger.get_period_accounting`` for headline totals."""
    import time

    rng = random.Random(seed)
    run = ReplayRun(corpus_version=rows[0]["corpus_version"] if rows else "v1", ledger_path=ledger_path)
    run.period_start_ts = time.time()

    for row in rows:
        # Phase 0.1 FIX 4b: quality_feedback's _quality_store is a
        # process-global dict keyed on (model, task_type, complexity). Left
        # unreset, 3+ consecutive low-quality rows in the same bucket trip
        # should_skip_model() for every later row in that bucket -- the
        # single stub model gets excluded from its own chain and every
        # subsequent same-bucket row dispatch-fails with "All models failed",
        # a harness artifact, not a real routing failure. Reset before each
        # row so quality learning never leaks across corpus rows.
        reset_quality_store()

        session_id = f"soak-{row['id']}"
        route_id, content = await _call_row(
            row,
            session_id=session_id,
            ledger_path=ledger_path,
            routing_ledger_path=routing_ledger_dir / f"rq-{row['id']}.jsonl",
            monkeypatch=monkeypatch,
            use_gold_complexity=use_gold_complexity,
            rng=rng,
        )

        dispatch_failed = route_id is None
        quality_score = 0.0 if dispatch_failed else _quality_score(content, row["gold_answer"])
        quality_delta = 1.0 - quality_score
        gate_pass = (not dispatch_failed) and quality_score >= GATE_THRESHOLD
        clears_lenient_floor = (
            (not dispatch_failed) and quality_score >= _LENIENT_FLOOR_THRESHOLD
        )
        gate_false_negative = (not gate_pass) and clears_lenient_floor

        realization_status = "unknown"
        adoption_method: str | None = None
        if gate_pass:
            if rng.random() < override_fraction:
                realization_status = "verified_overridden"
                adoption_method = None
            else:
                realization_status = "verified_used"
                adoption_method = "agent_marked"

        if route_id is not None:
            _write_realization(
                ledger_path=ledger_path,
                session_id=session_id,
                route_id=route_id,
                task_type=row["gold_task_type"],
                realization_status=realization_status,
                adoption_method=adoption_method,
            )

        row_net = 0.0
        row_quota = 0
        if route_id is not None:
            acc = get_session_accounting(session_id, path=ledger_path)
            row_net = acc.net_realized_savings_usd
            row_quota = acc.realized_quota_tokens_saved

        run.results.append(RowResult(
            row_id=row["id"],
            host_mode=row["host_mode"],
            route_id=route_id,
            quality_score=quality_score,
            quality_delta=quality_delta,
            gate_pass=gate_pass,
            gate_false_negative=gate_false_negative,
            realization_status=realization_status,
            adoption_method=adoption_method,
            dispatch_failed=dispatch_failed,
            net_realized_savings_usd=row_net,
            realized_quota_tokens_saved=row_quota,
        ))

    run.period_end_ts = time.time()
    return run
