"""Decision engine — first-match boolean composition over signal scores.

v0.0.1 ships the data model + a simple priority-ordered evaluator.
v0.0.2 will add the YAML loader and AND/OR/NOT operator nodes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tessera.signals.base import SignalScore

Operator = Literal["AND", "OR", "NOT", "SINGLE"]


@dataclass(frozen=True)
class Decision:
    """A single routing rule.

    Attributes:
        name: Rule identifier — surfaced in lineage.
        operator: How signal_refs combine.
        signal_refs: Names of signals to consult.
        action: Model identifier or chain alias to pick when this fires.
        priority: Lower wins. Ties broken by declaration order.
    """

    name: str
    operator: Operator
    signal_refs: tuple[str, ...]
    action: str
    priority: int = 100


@dataclass(frozen=True)
class DecisionResult:
    decision_name: str
    action: str
    fired_signals: tuple[str, ...]
    all_scores: tuple[SignalScore, ...]


class DecisionEngine:
    """Evaluate decisions against a bag of signal scores.

    Usage:
        engine = DecisionEngine(decisions=[d1, d2, ...])
        result = engine.choose(scores={"pii_secret": ..., "code_keywords": ...})
        result.action  -> "local_only" / "code_chain" / etc.
    """

    def __init__(self, decisions: list[Decision]) -> None:
        # Stable sort: priority asc, then declaration order.
        self._decisions = sorted(enumerate(decisions), key=lambda kv: (kv[1].priority, kv[0]))

    def choose(
        self, scores: dict[str, SignalScore], default_action: str = "default_chain"
    ) -> DecisionResult:
        for _, decision in self._decisions:
            fired = self._evaluate(decision, scores)
            if fired:
                return DecisionResult(
                    decision_name=decision.name,
                    action=decision.action,
                    fired_signals=tuple(s.name for s in fired),
                    all_scores=tuple(scores.values()),
                )
        return DecisionResult(
            decision_name="<default>",
            action=default_action,
            fired_signals=(),
            all_scores=tuple(scores.values()),
        )

    @staticmethod
    def _evaluate(decision: Decision, scores: dict[str, SignalScore]) -> list[SignalScore]:
        referenced = [scores[r] for r in decision.signal_refs if r in scores]
        if not referenced:
            return []
        fired = [s for s in referenced if s.fires]
        if decision.operator == "AND":
            return referenced if len(fired) == len(referenced) else []
        if decision.operator == "OR":
            return fired
        if decision.operator == "NOT":
            return [] if fired else referenced
        if decision.operator == "SINGLE":
            return fired[:1]
        raise ValueError(f"unknown operator: {decision.operator}")
