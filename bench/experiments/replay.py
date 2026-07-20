"""E-1/E-2 — load recorded session traces and replay them offline.

Each trace is a list of turns. A turn is either:
  - route == "host"          : context-dependent / DIRECT SKIP — the host model
                               handled it, NO external call, no usage row.
  - route == "routed_local"  : routed to a free provider (ollama/gemini_cli),
                               cost_usd == 0.
  - route == "routed_paid"   : routed to a metered provider, cost_usd > 0.

Replaying seeds a throwaway usage.db via the REAL cost.log_usage path (so schema,
migrations, and the exact baseline recompute are exercised), then returns the
production get_savings_by_period() aggregate plus derived per-shape metrics.
Deterministic: the recorded token/cost per turn is the cassette.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus" / "sessions"

SHAPES = ("local_repo_audit", "stateless_qa", "mixed_agentic")


def load_trace(shape: str) -> list[dict]:
    path = CORPUS_DIR / f"{shape}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def _seed_and_measure(trace: list[dict], *, subscription: bool) -> dict:
    """Seed a fresh usage.db from a trace and return the production aggregate.

    Isolates CHUZOM_DB_PATH to a temp dir so nothing touches ~/.chuzom.
    """
    from chuzom import config as config_module
    from chuzom import cost
    from chuzom.types import LLMResponse, RoutingProfile, TaskType

    tmp = Path(tempfile.mkdtemp(prefix="chuzom-exp-"))
    _saved = {k: os.environ.get(k) for k in
              ("CHUZOM_DB_PATH", "CHUZOM_CLAUDE_SUBSCRIPTION", "CHUZOM_ALLOW_STUBS")}
    os.environ["CHUZOM_DB_PATH"] = str(tmp / "test_usage.db")
    os.environ["CHUZOM_ALLOW_STUBS"] = "1"
    os.environ["CHUZOM_CLAUDE_SUBSCRIPTION"] = "true" if subscription else "false"
    config_module._config = None
    try:
        routed = 0
        skipped = 0
        for turn in trace:
            if turn.get("route") == "host":
                skipped += 1
                continue
            routed += 1
            resp = LLMResponse(
                content="", model=turn["model"],
                input_tokens=int(turn["input_tokens"]),
                output_tokens=int(turn["output_tokens"]),
                cost_usd=float(turn["cost_usd"]), latency_ms=10.0,
                provider=turn["provider"],
            )
            await cost.log_usage(resp, TaskType.QUERY, RoutingProfile.BUDGET)

        data = await cost.get_savings_by_period()
        at = data["all_time"]
        total = routed + skipped
        return {
            "periods": data,
            "turns": total,
            "routed": routed,
            "direct_skipped": skipped,
            "routed_pct": round(100 * routed / total, 1) if total else 0.0,
            "direct_skip_pct": round(100 * skipped / total, 1) if total else 0.0,
            "baseline_avoided_usd": at["baseline_avoided_usd"],
            "real_dollars_avoided_usd": at["real_dollars_avoided_usd"],
            "actual_usd": at["actual_usd"],
        }
    finally:
        # Restore every env key we touched so successive replays / later tests
        # don't inherit leaked state.
        for k, v in _saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config_module._config = None


async def replay(shape: str, *, subscription: bool = True) -> dict:
    """Replay one session shape and return its measured savings + metrics."""
    return await _seed_and_measure(load_trace(shape), subscription=subscription)
