"""Empirical token-shape calibration for a-priori cost projection.

Plan 07 — Category F (Cost realism).

The RouterArena 2026-06 exercise found that hardcoded output-token assumptions
(80 in legacy estimators, 500 in router.py budget-pressure check) under-predict
real output by 3x for many models. Claude Sonnet 4 on QUERY tasks averages
~250 output tokens with p95 hitting 2048. This module replaces those static
guesses with empirical per-(model, task_type) distributions.

Design principles:
- Pure function, zero I/O, zero global mutable state — trivially testable and
  hot-reloadable.
- Falls back to a static legacy assumption when no calibration data exists,
  so adoption is incremental — call sites can migrate one at a time without
  needing every (model, task) to be pre-calibrated.
- Provides ``projection_check`` for after-the-fact verification, surfacing
  miscalibrated entries via the standard logger. Telemetry layer (Cat E) can
  hook into this logger to retrain ``INITIAL_CALIBRATION`` automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from chuzom import pricing as _pricing
from chuzom.types import TaskType

__all__ = [
    "TokenShapeProfile",
    "INITIAL_CALIBRATION",
    "predict_cost",
    "cost_for_tokens",
    "projection_check",
]


@dataclass(frozen=True)
class TokenShapeProfile:
    """Empirical distribution of input/output tokens for a (model, task_type)."""

    model: str
    task_type: TaskType
    n_samples: int
    p50_output: int
    p95_output: int
    avg_input: int
    avg_output: int


# ── Seeded data from the RouterArena 2026-06 measurement run ──────────────────
#
# Add entries as telemetry produces them. Until Cat E (outcome telemetry) lands,
# this dict is hand-maintained from benchmark observations recorded in the
# Plan 07 design doc (lines 462-475).
# Keyed on the post-prefix-strip canonical model name used in cost tables
# (e.g. "claude-sonnet-4-6", not "anthropic/claude-sonnet-4-6"). The
# `_normalize_model_name` helper strips provider prefix at lookup time so
# callers can pass either form.
INITIAL_CALIBRATION: dict[tuple[str, TaskType], TokenShapeProfile] = {
    ("claude-sonnet-4-6", TaskType.QUERY): TokenShapeProfile(
        model="claude-sonnet-4-6",
        task_type=TaskType.QUERY,
        n_samples=1114,
        p50_output=230,
        p95_output=2048,
        avg_input=200,
        avg_output=250,
    ),
}


# Minimum sample count before empirical p50/p95 supersedes the static fallback.
# Below this threshold, distribution estimates are too noisy to trust over the
# conservative legacy assumption.
_N_SAMPLES_THRESHOLD = 30

# Legacy output-token assumption — preserved for the fallback path so calls
# referencing un-calibrated (model, task) pairs match historical projections.
_LEGACY_FALLBACK_OUTPUT = 80

# Per-million-token pricing, projected out of chuzom.pricing.
#
# WP-03: this was a local snapshot, justified in its own comment as keeping the
# module "pure" and free of cross-module dependencies, with an instruction to
# "update alongside cost.py BASELINE_PRICING". That instruction was not
# followed — and could not be, reliably: it asks a human to remember a second
# file. By the time of the audit this table held THREE separate retired rates
# ($15/$75 Opus, and Haiku at both $0.25/$1.25 and $0.80/$4.00 under two keys
# for the *same model*). Purity that costs correctness is not a good trade.
_CALIBRATED_MODELS: tuple[str, ...] = (
    # Anthropic — keys match src/chuzom/profiles.py chain entries after the
    # "anthropic/" prefix is stripped.
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-6",
    # OpenAI
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1",
    "gpt-4.1-mini",
    "o3",
    "o3-mini",
    # Google
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    # OpenRouter open-weight workhorse pool (Plan 06 Step 2). The cost_aggressive
    # policy references these and the bandit / policy-diff need a price to
    # compute expected value, so the entries must resolve; the exact numbers can
    # drift ~20% before the policy diff materially misranks.
    "qwen/qwen3-235b-a22b-2507",
    "deepseek/deepseek-v4-flash",
    "google/gemini-3.1-flash-lite",
    "qwen/qwen3-coder-next",
    "qwen/qwen3-next-80b-a3b-instruct",
    "x-ai/grok-4.3",
    "anthropic/claude-sonnet-4",
)

_PRICING_PER_M: dict[str, dict[str, float]] = {
    _m: {"input": _r["input"], "output": _r["output"]}
    for _m in _CALIBRATED_MODELS
    if (_r := _pricing.rates_per_m(_m)) is not None
}

_FREE_MODEL_PREFIXES = ("ollama", "codex", "gemini_cli")


def _normalize_model_name(model: str) -> str:
    """Strip a single provider prefix so lookups work with either form.

    ``"anthropic/claude-sonnet-4-6"`` → ``"claude-sonnet-4-6"``
    ``"claude-sonnet-4-6"``          → ``"claude-sonnet-4-6"``
    """
    return model.split("/", 1)[-1] if "/" in model else model


def _lookup_pricing(model: str) -> dict[str, float]:
    """Return per-million pricing for a model, treating local providers as free.

    Unknown models return zero rates — the caller (typically ``predict_cost``)
    decides whether to emit a calibration warning. Keeping this lookup
    permissive avoids raising on every novel model name introduced upstream.
    """
    if any(model.startswith(prefix) for prefix in _FREE_MODEL_PREFIXES):
        return {"input": 0.0, "output": 0.0}
    return _PRICING_PER_M.get(_normalize_model_name(model), {"input": 0.0, "output": 0.0})


def cost_for_tokens(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Compute USD cost for a call whose input/output token counts are known.

    Use this when both token counts are already in hand (post-call accounting,
    receipt logging). For *projection* — when output is unknown and must be
    estimated from the empirical distribution — call :func:`predict_cost`
    instead.

    Centralising the pricing dictionary here means session_spend, cost.py
    receipts, and any future cost-accounting callsite can share one source of
    truth. Unknown models return ``0.0`` (consistent with predict_cost) rather
    than a conservative fallback — the caller decides whether to floor.
    """
    pricing = _lookup_pricing(model)
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def predict_cost(
    model: str,
    task_type: TaskType,
    input_tokens: int,
    quantile: float = 0.5,
) -> float:
    """Predict USD cost of one call using empirical output-token distribution.

    Args:
        model: Provider/model identifier (with or without provider prefix).
            Both ``"anthropic/claude-sonnet-4-6"`` and ``"claude-sonnet-4-6"``
            resolve to the same calibration entry.
        task_type: Routing task type — distribution varies materially by task.
        input_tokens: Known input-token count for this prompt.
        quantile: 0.5 for median (typical projection), >=0.95 for worst-case
            (budget-pressure escalation checks should use 0.95).

    Returns:
        Predicted cost in USD. Returns 0.0 for unknown models (free providers
        or un-priced models); callers needing a conservative non-zero floor
        should apply it themselves.
    """
    pricing = _lookup_pricing(model)
    short = _normalize_model_name(model)
    profile = INITIAL_CALIBRATION.get((short, task_type))

    if profile is not None and profile.n_samples >= _N_SAMPLES_THRESHOLD:
        output_estimate = profile.p95_output if quantile >= 0.95 else profile.p50_output
    else:
        output_estimate = _LEGACY_FALLBACK_OUTPUT

    return (input_tokens * pricing["input"] + output_estimate * pricing["output"]) / 1_000_000


def projection_check(
    predicted: float,
    actual: float,
    threshold: float = 2.0,
) -> None:
    """Log a warning when actual cost exceeds ``threshold * predicted``.

    Side-effect-only — logs to ``chuzom.calibration``. Telemetry layer
    (Cat E) listens here to drive retraining of ``INITIAL_CALIBRATION``.

    Args:
        predicted: Predicted cost from ``predict_cost``.
        actual: Observed cost after the call returned.
        threshold: Ratio at or below which the prediction is considered fine.
            Default 2.0 means actual must exceed 2x predicted to warn.
    """
    if actual <= predicted * threshold:
        return

    log = logging.getLogger("chuzom.calibration")
    if predicted <= 0:
        log.warning(
            "Cost projection blown: predicted $%.5f (zero/negative), actual $%.5f",
            predicted, actual,
        )
        return

    ratio = actual / predicted
    log.warning(
        "Cost projection blown: predicted $%.5f, actual $%.5f (%.1fx, threshold=%.1fx)",
        predicted, actual, ratio, threshold,
    )
