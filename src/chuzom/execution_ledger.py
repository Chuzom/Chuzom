"""Canonical execution ledger — the SINGLE append-only source of truth for cost.

Correctness-reset Phase 2. Every provider *attempt* that consumes billable tokens or
quota is recorded here exactly once as its own event, for every outcome (accepted,
rejected-by-gate, rejected-by-quality, retry, escalation, emergency-fallback,
timeout-with-known-usage, partial-with-known-usage). Route/session/period totals are
DERIVED from these events by the aggregation layer below — no surface may keep its own
cost arithmetic (see ``Docs/correctness-reset/01_FINAL_ACCEPTANCE_CONTRACT.md``).

Invariants enforced structurally here:
  * INV-COST-001 — every billable attempt is one ``attempt_*`` event.
  * INV-COST-002 — ``get_route_accounting(route_id).actual_cost_usd`` == Σ attempt costs.
  * INV-COST-003 — ``event_id`` is the PRIMARY KEY; re-recording an event is a no-op
    (``INSERT OR IGNORE``), so aggregation is idempotent and nothing is double-counted.
  * INV-COST-004 — the aggregation functions are the ONLY cost totals; surfaces delegate.
  * INV-ROUTE-004/005 — ``terminal_state`` is a first-class recorded field.

Storage: table ``execution_events`` inside ``~/.chuzom/usage.db`` (the existing SoT DB).
Writes are FAIL-OPEN and never raise into the routing path — a lost metric is not a lost
turn. Aggregation reads are strict: a reconciliation mismatch is surfaced, never coerced.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

SCHEMA_VERSION = 1

# ── Event taxonomy ────────────────────────────────────────────────────────────
EventType = Literal[
    "route_started",
    "directive_injected",
    "attempt_started",
    "attempt_completed",      # billable, accepted (won the route)
    "attempt_rejected",       # billable, rejected by gate/quality — STILL a cost
    "attempt_failed",         # provider error; cost only if usage is known
    "escalation_started",
    "fallback_started",
    "route_completed",
    "route_failed",
    "native_tool_override",
    "plain_text_override",
    "result_used",
    "result_discarded",
    "realization_unknown",
    "provider_health_changed",
]

# Event types that carry billable token/quota cost and therefore contribute to
# route/session actual-cost totals. An attempt that consumed tokens is billable
# whether or not its answer was kept.
_BILLABLE_EVENTS: frozenset[str] = frozenset(
    {"attempt_completed", "attempt_rejected", "attempt_failed"}
)

TerminalState = Literal[
    "accepted", "rejected", "failed", "cancelled", "bypassed", "overridden", "unknown",
]
RealizationStatus = Literal["verified_used", "verified_overridden", "unknown"]


@dataclass
class LedgerEvent:
    """One append-only execution event. ``event_id`` is unique (idempotent write)."""

    # Identity
    schema_version: int = SCHEMA_VERSION
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = 0.0                       # stamped on write if 0
    session_id: str = ""
    turn_id: str = ""
    route_id: str = ""
    attempt_id: str = ""
    event_type: EventType = "route_started"

    # Classification
    task_type: str = "unknown"
    routing_profile: str = "unknown"
    host_mode: str = "unknown"            # "subscription" | "metered" | "unknown"

    # Provider / model
    provider: str = ""
    model: str = ""

    # Tokens & cost (measured; None = unknown, never fabricated)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    measured_cost_usd: float | None = None
    baseline_equivalent_cost_usd: float | None = None

    # Orchestration overhead (INV-COST-005)
    hook_input_tokens: int | None = None
    hook_output_tokens: int | None = None

    # Outcome
    accepted: bool | None = None
    rejected: bool | None = None
    rejection_reason: str | None = None
    escalation_reason: str | None = None
    fallback_reason: str | None = None
    provider_failure_reason: str | None = None

    # Realization / override
    used_by_host: bool | None = None
    realization_status: RealizationStatus | None = None
    override_type: str | None = None      # "native_tool" | "plain_text" | None

    # Terminal state (INV-ROUTE-004/005) — set on route_completed/route_failed events
    terminal_state: TerminalState | None = None

    metadata: dict[str, Any] = field(default_factory=dict)


# ── Storage ───────────────────────────────────────────────────────────────────
def _db_path() -> Path:
    override = os.environ.get("CHUZOM_EXECUTION_LEDGER_DB")
    if override:
        return Path(override)
    return Path.home() / ".chuzom" / "usage.db"


_COLUMNS: tuple[str, ...] = (
    "schema_version", "event_id", "ts", "session_id", "turn_id", "route_id",
    "attempt_id", "event_type", "task_type", "routing_profile", "host_mode",
    "provider", "model", "input_tokens", "output_tokens", "cache_read_tokens",
    "cache_write_tokens", "measured_cost_usd", "baseline_equivalent_cost_usd",
    "hook_input_tokens", "hook_output_tokens", "accepted", "rejected",
    "rejection_reason", "escalation_reason", "fallback_reason",
    "provider_failure_reason", "used_by_host", "realization_status",
    "override_type", "terminal_state", "metadata",
)

_DDL = """
CREATE TABLE IF NOT EXISTS execution_events (
    schema_version INTEGER NOT NULL,
    event_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    session_id TEXT,
    turn_id TEXT,
    route_id TEXT,
    attempt_id TEXT,
    event_type TEXT NOT NULL,
    task_type TEXT,
    routing_profile TEXT,
    host_mode TEXT,
    provider TEXT,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    measured_cost_usd REAL,
    baseline_equivalent_cost_usd REAL,
    hook_input_tokens INTEGER,
    hook_output_tokens INTEGER,
    accepted INTEGER,
    rejected INTEGER,
    rejection_reason TEXT,
    escalation_reason TEXT,
    fallback_reason TEXT,
    provider_failure_reason TEXT,
    used_by_host INTEGER,
    realization_status TEXT,
    override_type TEXT,
    terminal_state TEXT,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_exec_route ON execution_events(route_id);
CREATE INDEX IF NOT EXISTS idx_exec_session ON execution_events(session_id);
CREATE INDEX IF NOT EXISTS idx_exec_ts ON execution_events(ts);
"""


def _connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # 30s busy-timeout (was 5s): under pathological CI-runner load, rapid open/write/
    # close cycles can transiently hold the WAL lock long enough that a 5s wait errored
    # with `database is locked`. A longer wait lets the writer drain instead of failing.
    conn = sqlite3.connect(str(p), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_DDL)
    return conn


def _row_to_value(field_name: str, ev: LedgerEvent) -> Any:
    v = getattr(ev, field_name)
    if field_name == "metadata":
        return json.dumps(v or {})
    if isinstance(v, bool):
        return int(v)
    return v


def record_event(ev: LedgerEvent, *, path: Path | None = None) -> bool:
    """Append *ev* to the canonical ledger. Idempotent on ``event_id`` (INV-COST-003).

    FAIL-OPEN: returns False on any error, never raises into the caller (routing path).
    """
    try:
        if not ev.ts:
            ev.ts = time.time()
        conn = _connect(path)
        try:
            placeholders = ",".join("?" for _ in _COLUMNS)
            values = [_row_to_value(c, ev) for c in _COLUMNS]
            conn.execute(
                f"INSERT OR IGNORE INTO execution_events ({','.join(_COLUMNS)}) "
                f"VALUES ({placeholders})",
                values,
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:  # noqa: BLE001 — a ledger failure must never break routing
        return False


def _load_rows(where: str, params: tuple, path: Path | None = None) -> list[dict[str, Any]]:
    conn = _connect(path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"SELECT {','.join(_COLUMNS)} FROM execution_events WHERE {where}", params
        )
        out = []
        for r in cur.fetchall():
            d = dict(r)
            d["metadata"] = json.loads(d.get("metadata") or "{}")
            out.append(d)
        return out
    finally:
        conn.close()


# ── Aggregation layer — the ONLY cost totals (INV-COST-002/004) ────────────────
@dataclass
class Accounting:
    """Derived totals for a route / turn / session / period. Read-model, never stored."""

    scope: str
    scope_id: str
    attempt_count: int = 0
    billable_attempt_count: int = 0
    accepted_attempt_count: int = 0
    rejected_attempt_count: int = 0
    actual_cost_usd: float = 0.0                # Σ measured_cost over billable attempts
    baseline_equivalent_cost_usd: float = 0.0   # Σ baseline_equivalent over billable attempts
    hook_input_tokens: int = 0
    hook_output_tokens: int = 0
    terminal_states: dict[str, int] = field(default_factory=dict)
    cost_unknown_attempts: int = 0              # billable attempts with measured_cost=None
    # ── Realization (Gate 18) ────────────────────────────────────────────────
    # A route's potential saving (baseline_equivalent − actual) is only REALIZED
    # if the routed result was verifiably used by the host. Routes whose
    # realization is `verified_overridden` (host went its own way) or `unknown`
    # (couldn't verify) must NOT be counted as realized savings.
    realized_routes: int = 0                     # realization_status == verified_used
    overridden_routes: int = 0                   # verified_overridden
    realization_unknown_routes: int = 0          # unknown (or never verified)
    potential_savings_usd: float = 0.0           # Σ max(0, baseline_eq − actual) over ALL routes
    realized_savings_usd: float = 0.0            # Σ that saving ONLY on verified_used routes

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _aggregate(scope: str, scope_id: str, rows: list[dict[str, Any]]) -> Accounting:
    acc = Accounting(scope=scope, scope_id=scope_id)
    # Gate 18: potential saving is per-ROUTE (baseline_eq − actual), and it's only
    # REALIZED when that route's realization is verified_used. Accumulate per route
    # so a single unknown/overridden route can't inflate the realized total.
    route_potential: dict[str, float] = {}       # route_id → Σ(baseline_eq − actual)
    route_realization: dict[str, str] = {}       # route_id → last realization_status seen
    for r in rows:
        et = r["event_type"]
        rid = r.get("route_id") or ""
        if et in _BILLABLE_EVENTS:
            acc.attempt_count += 1
            acc.billable_attempt_count += 1
            if et == "attempt_completed":
                acc.accepted_attempt_count += 1
            elif et == "attempt_rejected":
                acc.rejected_attempt_count += 1
            cost = r.get("measured_cost_usd")
            if cost is None:
                acc.cost_unknown_attempts += 1
            else:
                acc.actual_cost_usd += float(cost)
                route_potential[rid] = route_potential.get(rid, 0.0) - float(cost)
            base = r.get("baseline_equivalent_cost_usd")
            if base is not None:
                acc.baseline_equivalent_cost_usd += float(base)
                route_potential[rid] = route_potential.get(rid, 0.0) + float(base)
        # Realization tracking: the explicit status field wins; the
        # `realization_unknown` event type is a fallback signal for unknown.
        rs = r.get("realization_status")
        if rs:
            route_realization[rid] = rs
        elif et == "realization_unknown":
            route_realization.setdefault(rid, "unknown")
        if r.get("hook_input_tokens"):
            acc.hook_input_tokens += int(r["hook_input_tokens"])
        if r.get("hook_output_tokens"):
            acc.hook_output_tokens += int(r["hook_output_tokens"])
        ts = r.get("terminal_state")
        if ts:
            acc.terminal_states[ts] = acc.terminal_states.get(ts, 0) + 1
    acc.actual_cost_usd = round(acc.actual_cost_usd, 6)
    acc.baseline_equivalent_cost_usd = round(acc.baseline_equivalent_cost_usd, 6)

    # ── Realization-gated savings (Gate 18) ──────────────────────────────────
    # potential = every route's positive saving; realized = ONLY verified_used
    # routes. A route with realization `unknown` or `verified_overridden` — or no
    # realization event at all — contributes to potential but NEVER to realized,
    # so an unverified saving can never be reported as realized.
    for rid, delta in route_potential.items():
        acc.potential_savings_usd += max(0.0, delta)
        if route_realization.get(rid) == "verified_used":
            acc.realized_savings_usd += max(0.0, delta)
    for rs in route_realization.values():
        if rs == "verified_used":
            acc.realized_routes += 1
        elif rs == "verified_overridden":
            acc.overridden_routes += 1
        elif rs == "unknown":
            acc.realization_unknown_routes += 1
    acc.potential_savings_usd = round(acc.potential_savings_usd, 6)
    acc.realized_savings_usd = round(acc.realized_savings_usd, 6)
    return acc


def get_route_accounting(route_id: str, *, path: Path | None = None) -> Accounting:
    """INV-COST-002: actual cost == Σ measured cost over billable attempt events."""
    return _aggregate("route", route_id,
                      _load_rows("route_id = ?", (route_id,), path))


def get_turn_accounting(turn_id: str, *, path: Path | None = None) -> Accounting:
    return _aggregate("turn", turn_id, _load_rows("turn_id = ?", (turn_id,), path))


def get_session_accounting(session_id: str, *, path: Path | None = None) -> Accounting:
    return _aggregate("session", session_id,
                      _load_rows("session_id = ?", (session_id,), path))


def get_period_accounting(
    start_ts: float, end_ts: float, *, path: Path | None = None
) -> Accounting:
    return _aggregate(
        "period", f"{start_ts:.0f}-{end_ts:.0f}",
        _load_rows("ts >= ? AND ts < ?", (start_ts, end_ts), path),
    )


# ── Reconciliation (INV-COST-004) ──────────────────────────────────────────────
@dataclass
class Reconciliation:
    """Result of checking a surface's reported actual-cost against the canonical
    ledger total. INV-COST-004: no user-facing spend surface may report an
    actual-cost total different from the aggregation layer. A surface (or its test)
    calls ``reconcile_session`` with the number it displays; ``reconciled`` is False
    when it drifts from the ledger, or when any billable attempt has unknown cost
    (so "exact" would be a lie — see INV-COST-005 fail-behavior)."""

    scope_id: str
    canonical_actual_usd: float
    reported_actual_usd: float | None
    reconciled: bool
    cost_unknown_attempts: int
    delta_usd: float


def reconcile_session(
    session_id: str,
    reported_actual_usd: float | None = None,
    *,
    tol: float = 1e-6,
    path: Path | None = None,
) -> Reconciliation:
    """Reconcile a surface's ``reported_actual_usd`` against the canonical session
    total. With ``reported_actual_usd=None`` it reports only whether the ledger's own
    total is fully known (no cost_unknown attempts) — the self-consistency check."""
    acc = get_session_accounting(session_id, path=path)
    canonical = acc.actual_cost_usd
    reconciled = acc.cost_unknown_attempts == 0
    delta = 0.0
    if reported_actual_usd is not None:
        delta = round(float(reported_actual_usd) - canonical, 6)
        reconciled = reconciled and abs(delta) <= tol
    return Reconciliation(
        scope_id=session_id,
        canonical_actual_usd=canonical,
        reported_actual_usd=reported_actual_usd,
        reconciled=reconciled,
        cost_unknown_attempts=acc.cost_unknown_attempts,
        delta_usd=delta,
    )
