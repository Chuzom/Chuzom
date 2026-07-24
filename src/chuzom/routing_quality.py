"""North Star measurement: a fail-open per-route quality ledger.

The North Star is "route to the cheapest capable model, escalate on failure" — and
it must be MEASURED, not assumed. Every routed execution appends a :class:`RouteRecord`
to ``~/.chuzom/routing_quality.jsonl``; :func:`summarize` reads it back into
escalation / mis-route / completion rates and total savings.

Recording is FAIL-OPEN: a ledger write must never raise into the routing path. If
the ledger can't be written, the route still proceeds — we lose a metric, not a turn.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class RouteRecord:
    """One routed execution's measured outcome."""
    task_type: str
    chosen_tier: int | str          # tier that first attempted the work
    needed_escalation: bool         # did the initial tier fail and escalate?
    completion: bool                # did objective verification pass?
    tool_success: bool              # did tool execution succeed?
    actual_cost: float = 0.0
    baseline_cost: float = 0.0
    saved: float = 0.0
    mis_route: bool = False         # initial routing decision was wrong (needed escalation)
    ts: float = 0.0                 # unix time; stamped on write if 0


def _default_ledger() -> Path:
    return Path(os.environ.get("CHUZOM_ROUTING_LEDGER",
                               str(Path.home() / ".chuzom" / "routing_quality.jsonl")))


def record(rec: RouteRecord, path: str | None = None) -> bool:
    """Append *rec* to the ledger. FAIL-OPEN: returns False on any error, never raises."""
    try:
        if not rec.ts:
            rec.ts = time.time()
        p = Path(path) if path else _default_ledger()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(rec)) + "\n")
        return True
    except Exception:  # noqa: BLE001 — a ledger failure must never break routing
        return False


def summarize(path: str | None = None) -> dict[str, Any]:
    """Read the ledger into routing-quality metrics. Fail-open → {'routes': 0}."""
    try:
        p = Path(path) if path else _default_ledger()
        rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001 — missing/corrupt ledger reads as empty
        return {"routes": 0}
    n = len(rows)
    if n == 0:
        return {"routes": 0}

    def _rate(key: str) -> float:
        return sum(1 for r in rows if r.get(key)) / n

    return {
        "routes": n,
        "completion_rate": _rate("completion"),
        "tool_success_rate": _rate("tool_success"),
        "escalation_rate": _rate("needed_escalation"),
        "mis_route_rate": _rate("mis_route"),
        "total_saved": round(sum(float(r.get("saved", 0.0)) for r in rows), 4),
    }


def record_delegation(result: dict[str, Any], path: str | None = None) -> bool:
    """Build a RouteRecord from an MGEE delegation result and record it (fail-open).

    Escalation/mis-route are derived from which tiers cleared the milestones: any
    milestone cleared by a tier above the cheapest attempted one means the initial
    routing under-shot (mis_route)."""
    try:
        tiers = [m.get("achieved_by") for m in (result.get("milestones") or [])
                 if m.get("achieved_by") is not None]
        cheapest = min(tiers) if tiers else 0
        escalated = any(t > cheapest for t in tiers)
        savings = result.get("savings") or {}
        rec = RouteRecord(
            task_type="delegate",
            chosen_tier=cheapest,
            needed_escalation=escalated,
            completion=(result.get("outcome") == "complete"),
            tool_success=(result.get("outcome") in ("complete", "surfaced")),
            actual_cost=float(savings.get("actual_usd", 0.0) or 0.0),
            baseline_cost=float(savings.get("baseline_usd", 0.0) or 0.0),
            saved=float(savings.get("saved_usd", 0.0) or 0.0),
            mis_route=escalated,
        )
        return record(rec, path=path)
    except Exception:  # noqa: BLE001 — never break the delegation path
        return False
