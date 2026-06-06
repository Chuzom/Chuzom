# SPDX-FileCopyrightText: 2026 ypollak2
# SPDX-License-Identifier: MIT
"""Chuzom router for RouterArena.

This is the RouterArena-plug-in version of Chuzom. It re-implements
Chuzom's heuristic classifier + tier+subject selector inline so the
submission is self-contained — RouterArena's evaluation environment
doesn't need the full ``chuzom-router`` PyPI package installed.

Routing strategy (matches Chuzom's production fast-path):

* Keyword/length heuristic produces (task_type, complexity).
* Subject is inferred from a coarse domain → subject map keyed on the
  prompt's content. RouterArena prompts don't ship the dataset's Domain
  field at inference time, so we do a lightweight prefix/keyword pass
  here.
* (complexity, subject) → model name via a transparent override + tier
  table. Each pick is explainable from the source alone.

Selection rules:

1. ``subject == "code"`` → ``Qwen3-Coder-Next`` (specialist beats tier).
2. ``subject in {math, scientific, reasoning}`` AND complexity ≥ moderate
   → ``deepseek/deepseek-v4-flash`` (deepseek's sweet spot).
3. Tier by complexity:

   * simple        → ``google/gemini-3.1-flash-lite``
   * moderate      → ``gpt-4o-mini``
   * complex       → ``qwen/qwen3-235b-a22b-2507``
   * deep_reasoning → ``qwen/qwen3-235b-a22b-2507`` (pool has no o1-class)

Reference: github.com/ypollak2/chuzom (v0.1.0). The inlined classifier
mirrors ``src/chuzom/hooks/auto-route.py``'s ``classify_prompt`` /
``score_categories`` / ``classify_complexity`` functions.
"""

from __future__ import annotations

import re

from router_inference.router.base_router import BaseRouter


# ── Inlined heuristic classifier (mirrors src/chuzom/hooks/auto-route.py) ──

_COMPLEXITY_SIMPLE = re.compile(
    r"\b(what is|who is|when did|where is|define|name the|list the)\b",
    re.IGNORECASE,
)
_COMPLEXITY_COMPLEX = re.compile(
    r"\b(analyze|compare|evaluate|explain why|derive|prove|design|architect)\b",
    re.IGNORECASE,
)
_COMPLEXITY_DEEP = re.compile(
    r"\b(prove|theorem|lemma|optimi[sz]e|multi-step|step-by-step)\b",
    re.IGNORECASE,
)

_TASK_PATTERNS = {
    "code": re.compile(
        r"\b(function|class|method|implement|refactor|debug|algorithm|"
        r"loop|variable|return|python|javascript|java|rust|go|c\+\+)\b",
        re.IGNORECASE,
    ),
    "analyze": re.compile(
        r"\b(analyze|compare|evaluate|explain|root cause|tradeoff)\b",
        re.IGNORECASE,
    ),
    "research": re.compile(
        r"\b(research|find|search|latest|recent|news|study)\b",
        re.IGNORECASE,
    ),
    "generate": re.compile(
        r"\b(write|draft|compose|create|generate|narrate)\b",
        re.IGNORECASE,
    ),
}

_SUBJECT_PATTERNS = {
    "code": re.compile(
        r"\b(python|javascript|java|rust|go\b|c\+\+|function|algorithm|"
        r"runtime|compile|api|sql|regex)\b",
        re.IGNORECASE,
    ),
    "math": re.compile(
        r"\b(equation|integral|derivative|theorem|lemma|matrix|vector|"
        r"polynomial|inequality|combinator(?:ic|y)|probability|"
        r"converg(?:e|ence|ent)|(?:infinite|geometric|power|fourier|"
        r"harmonic|taylor)\s+series|sum_?\{|n=1|limit\s+as|"
        r"sequence\s+of\s+(?:integers|reals|numbers)|recursion|fibonacci|"
        r"basel\s+problem)\b",
        re.IGNORECASE,
    ),
    "scientific": re.compile(
        r"\b(experiment|hypothesis|catalyst|reaction|mole|atom|electron|"
        r"protein|enzyme|cell|genome|circuit|voltage|momentum)\b",
        re.IGNORECASE,
    ),
    "reasoning": re.compile(
        r"\b(logic|syllogism|deduction|inference|premise|conclusion|"
        r"counterexample|contradicts?)\b",
        re.IGNORECASE,
    ),
    "language": re.compile(
        r"\b(grammar|syntax|tense|conjugat|translate|noun|verb|adjective)\b",
        re.IGNORECASE,
    ),
    "history": re.compile(
        r"\b(century|empire|dynasty|revolution|war|treaty|ancient|medieval)\b",
        re.IGNORECASE,
    ),
    "business": re.compile(
        r"\b(market|equity|revenue|profit|stakeholder|GDP|inflation|"
        r"interest rate|cost of capital)\b",
        re.IGNORECASE,
    ),
    "creative": re.compile(
        r"\b(novel|metaphor|sonnet|prose|character|protagonist|imagery)\b",
        re.IGNORECASE,
    ),
}


def _classify_complexity(text: str, task_type: str) -> str:
    """Mirror of chuzom.hooks.auto-route.classify_complexity."""
    if _COMPLEXITY_DEEP.search(text):
        return "deep_reasoning"
    if _COMPLEXITY_COMPLEX.search(text):
        return "complex"
    if _COMPLEXITY_SIMPLE.search(text):
        return "simple"
    if len(text) > 500:
        return "complex"
    if len(text) > 150:
        return "moderate"
    return "simple" if task_type == "query" else "moderate"


def _infer_task_type(text: str) -> str:
    """Pick the highest-scoring task category, default ``query``."""
    best = ("query", 0)
    for name, pat in _TASK_PATTERNS.items():
        score = len(pat.findall(text))
        if score > best[1]:
            best = (name, score)
    return best[0]


def _infer_subject(text: str) -> str:
    """Pick the highest-scoring subject pattern, default ``general``.

    Inline because RouterArena doesn't ship the dataset's Domain field at
    inference time — we read the same signals out of the prompt text.
    """
    best = ("general", 0)
    for name, pat in _SUBJECT_PATTERNS.items():
        score = len(pat.findall(text))
        if score > best[1]:
            best = (name, score)
    return best[0]


# ── ChuzomRouter ──────────────────────────────────────────────────────────


class ChuzomRouter(BaseRouter):
    """Three-axis (complexity × task_type × subject) router for RouterArena.

    Deterministic, offline, no API calls — each routing decision is a
    function of the prompt text and the configured model pool.
    """

    def _get_prediction(self, query: str) -> str:
        task_type = _infer_task_type(query)
        complexity = _classify_complexity(query, task_type)
        subject = _infer_subject(query)

        # Override 1: code specialist
        if subject == "code" and "Qwen/Qwen3-Coder-Next" in self.models:
            return "Qwen/Qwen3-Coder-Next"

        # Override 2: reasoning-heavy subjects → deepseek (its sweet spot)
        if (
            subject in {"math", "scientific", "reasoning"}
            and complexity in {"moderate", "complex", "deep_reasoning"}
            and "deepseek/deepseek-v4-flash" in self.models
        ):
            return "deepseek/deepseek-v4-flash"

        # Tier by complexity
        if complexity == "simple" and "google/gemini-3.1-flash-lite" in self.models:
            return "google/gemini-3.1-flash-lite"
        if complexity == "moderate" and "gpt-4o-mini" in self.models:
            return "gpt-4o-mini"
        if "qwen/qwen3-235b-a22b-2507" in self.models:
            return "qwen/qwen3-235b-a22b-2507"

        # Defensive: pool changed under us — pick the first model.
        return self.models[0]
