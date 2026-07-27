"""Control-group savings verdict (Phase 8 / #5 — Gates 15/16/17).

The head-to-head harness (``bench/runner.py``) produces per-prompt ``RunRow``s for
every router. This module turns two of those arms — **Chuzom ON** and the
**Chuzom-OFF control** (``always-claude-host``: the host model answers everything,
which is what routing is compared *against*) — into the three release-gate
judgements:

- **Gate 15 — positive net verified savings.** Σ(host cost) − Σ(chuzom cost),
  net of routing overhead, computed from **measured** tokens (never fabricated).
- **Gate 16 — quality within a non-inferiority margin.** Chuzom's mean judge
  score must not fall below the host's by more than ``margin``.
- **Gate 17 — no unclassified spend.** Every benchmark event must carry a
  *classified* cost. A non-free model priced at exactly $0 means its price was
  unknown (see ``bench.routers._price``) — that is unclassified spend and it
  fails the gate; genuinely-free local models (``ollama/…``) are classified $0.

This module is pure analysis over rows — it makes **no** API calls and asserts
nothing about the *sign* of the result. Whether Gate 15 actually passes is an
**empirical** outcome of running the harness with real spend; here we only make
the judgement honest and reproducible once those rows exist.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# Model-id prefixes that are genuinely free at the API boundary (local compute).
# A $0 cost on any OTHER model means the price was unknown → unclassified spend.
_FREE_PREFIXES: tuple[str, ...] = ("ollama/",)

CHUZOM_ARM = "chuzom"
CONTROL_ARM = "always-claude-host"


@dataclass(frozen=True)
class SavingsVerdict:
    n_prompts: int
    control_cost_usd: float          # Σ host baseline cost (Chuzom OFF)
    chuzom_cost_usd: float           # Σ Chuzom cost (ON)
    routing_overhead_usd: float      # Σ measured routing/classification overhead
    net_savings_usd: float           # control − chuzom − overhead  (the honest net)
    control_tokens: int
    chuzom_tokens: int
    control_quality: float           # mean judge score, host arm
    chuzom_quality: float            # mean judge score, Chuzom arm
    quality_delta: float             # chuzom − control (≥ −margin passes)
    non_inferiority_margin: float
    unclassified_events: list[str] = field(default_factory=list)  # corpus_ids

    # ── Gate judgements (empirical; None if the arm is missing) ──────────────
    @property
    def gate15_positive_net_savings(self) -> bool:
        return self.net_savings_usd > 0.0

    @property
    def gate16_quality_non_inferior(self) -> bool:
        return self.quality_delta >= -self.non_inferiority_margin

    @property
    def gate17_no_unclassified_spend(self) -> bool:
        return not self.unclassified_events

    @property
    def all_gates_pass(self) -> bool:
        return (self.gate15_positive_net_savings
                and self.gate16_quality_non_inferior
                and self.gate17_no_unclassified_spend)


def _is_unclassified(model_chosen: str, cost_usd: float) -> bool:
    """A non-free model reported at exactly $0 → its price was unknown."""
    if cost_usd > 0.0:
        return False
    if any(model_chosen.startswith(p) for p in _FREE_PREFIXES):
        return False  # local model, genuinely free — classified $0
    if model_chosen in ("", "<exhausted>"):
        return False  # a failure/exhaustion row carries no spend to classify
    return True


def _overhead_of(row) -> float:
    """Routing/classification overhead for a row, if the router recorded it in
    ``notes`` (e.g. classifier-latency cost). Absent → 0.0, never fabricated."""
    notes = getattr(row, "notes", None) or {}
    try:
        return float(notes.get("routing_overhead_usd", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def evaluate_savings(
    rows: Iterable,
    *,
    chuzom_arm: str = CHUZOM_ARM,
    control_arm: str = CONTROL_ARM,
    non_inferiority_margin: float = 0.5,
) -> SavingsVerdict:
    """Compute the Gate 15/16/17 verdict from benchmark ``RunRow``s.

    Args:
        rows: RunRow-like objects (need router_name, corpus_id, model_chosen,
            input_tokens, output_tokens, cost_usd, judge_score, notes).
        chuzom_arm / control_arm: which router_name is Chuzom-ON / the host
            control (Chuzom-OFF).
        non_inferiority_margin: max allowed drop in mean judge score (Gate 16).

    Raises:
        ValueError: if either arm is missing, or the two arms don't cover the
            same set of prompts (an unpaired A/B is not a valid comparison).
    """
    rows = list(rows)
    chuzom = [r for r in rows if r.router_name == chuzom_arm]
    control = [r for r in rows if r.router_name == control_arm]
    if not chuzom:
        raise ValueError(f"no rows for Chuzom arm {chuzom_arm!r}")
    if not control:
        raise ValueError(f"no rows for control arm {control_arm!r}")

    chuzom_ids = {r.corpus_id for r in chuzom}
    control_ids = {r.corpus_id for r in control}
    if chuzom_ids != control_ids:
        missing = (control_ids ^ chuzom_ids)
        raise ValueError(
            f"A/B arms cover different prompts — unpaired comparison; symmetric "
            f"difference: {sorted(missing)}")

    def _tokens(rs: Sequence) -> int:
        return sum(r.input_tokens + r.output_tokens for r in rs)

    def _cost(rs: Sequence) -> float:
        return sum(r.cost_usd for r in rs)

    def _quality(rs: Sequence) -> float:
        return sum(r.judge_score for r in rs) / len(rs) if rs else 0.0

    control_cost = _cost(control)
    chuzom_cost = _cost(chuzom)
    overhead = sum(_overhead_of(r) for r in chuzom)

    unclassified = sorted(
        r.corpus_id for r in rows
        if _is_unclassified(r.model_chosen, r.cost_usd)
    )

    control_q = _quality(control)
    chuzom_q = _quality(chuzom)

    return SavingsVerdict(
        n_prompts=len(chuzom_ids),
        control_cost_usd=control_cost,
        chuzom_cost_usd=chuzom_cost,
        routing_overhead_usd=overhead,
        net_savings_usd=control_cost - chuzom_cost - overhead,
        control_tokens=_tokens(control),
        chuzom_tokens=_tokens(chuzom),
        control_quality=control_q,
        chuzom_quality=chuzom_q,
        quality_delta=chuzom_q - control_q,
        non_inferiority_margin=non_inferiority_margin,
        unclassified_events=unclassified,
    )
