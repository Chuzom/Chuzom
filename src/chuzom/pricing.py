"""Canonical model pricing — the single source of truth for money in Chuzom.

Every price in this codebase comes from here. Nothing else may define one.

WHY THIS MODULE EXISTS
----------------------
An audit of v1.1.1 found the same stale Opus rate ($15/$75, which is Opus *3*
pricing) living in five independent tables, three of which fed user-visible
savings figures — a 3x overstatement. Git history shows that exact bug being
fixed locally four separate times and returning every time, because each fix
touched one table and left the others alone.

Two design decisions follow from that history, and both matter more than the
numbers themselves:

1. **Keyed by model ID, never by family alias.** The older tables keyed on
   ``"opus"``. That cannot be correct once two Opus versions have different
   prices — which is exactly what happened when Opus 4.5 cut the rate. A
   family-keyed table has no representation for "Opus, but which one", so it is
   guaranteed to be wrong for somebody. Aliases still resolve (see
   :func:`resolve`), but they resolve *to* a model ID; they never carry a price.

2. **Cache rates are derived, not stored.** Anthropic's cache pricing is a fixed
   ratio of the input rate (read 0.1x, write 1.25x at the 5-minute TTL). Storing
   four numbers per model where two plus a formula will do creates three more
   things to get out of sync. Verified against the previously-correct Sonnet
   entry: 3.00 input -> 0.30 read / 3.75 write, matching to the cent.

Enforced by ``scripts/lint_pricing.py`` in CI: a price literal anywhere outside
this module fails the build.

SOURCES
-------
Anthropic list pricing as of ``PRICES_AS_OF``. OpenAI/Google rates are carried
forward from the tables this module replaces and are marked ``verified=False``
where they were not independently confirmed during consolidation — see
:func:`unverified_models`. An unverified price is still a price; it is flagged so
nobody mistakes provenance for accuracy.
"""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass

__all__ = [
    "PRICES_AS_OF",
    "STALENESS_DAYS",
    "Price",
    "price_for",
    "resolve",
    "input_rate",
    "output_rate",
    "cache_read_rate",
    "cache_write_rate",
    "cost_usd",
    "is_free",
    "known_models",
    "unverified_models",
    "staleness_days",
    "is_stale",
]

# Date the Anthropic rates below were last confirmed against published pricing.
# Bump this ONLY when the numbers are re-checked, never as a formality — a stale
# date that says "fresh" is worse than an honest old one.
PRICES_AS_OF = _dt.date(2026, 8, 11)

#: Age at which the table is considered stale and callers should warn.
STALENESS_DAYS = 90

# Cache rate ratios, applied to the input rate. Anthropic publishes these as
# fixed multiples, so deriving them removes an entire class of drift.
_CACHE_READ_RATIO = 0.10
_CACHE_WRITE_RATIO = 1.25  # 5-minute TTL; the 1-hour TTL is 2.0x


@dataclass(frozen=True)
class Price:
    """Per-million-token rates for one model.

    ``cache_read``/``cache_write`` default to ``None`` and are derived from
    ``input`` on access. Set them explicitly only for a provider that does not
    follow the standard ratio.
    """

    model_id: str
    input: float
    output: float
    cache_read: float | None = None
    cache_write: float | None = None
    verified: bool = True
    note: str = ""

    @property
    def cache_read_rate(self) -> float:
        return self.cache_read if self.cache_read is not None else self.input * _CACHE_READ_RATIO

    @property
    def cache_write_rate(self) -> float:
        return self.cache_write if self.cache_write is not None else self.input * _CACHE_WRITE_RATIO


# Sonnet 5 runs introductory pricing through 2026-08-31, then reverts. Encoded
# rather than hardcoded to one side: picking "standard" understates cost today,
# picking "intro" overstates it from September. Both are resolved by date, and
# tests pass an explicit date so no test depends on the wall clock.
_SONNET_5_INTRO_UNTIL = _dt.date(2026, 8, 31)
_SONNET_5_INTRO = (2.00, 10.00)
_SONNET_5_STANDARD = (3.00, 15.00)

_PRICES: dict[str, Price] = {
    # ── Anthropic ────────────────────────────────────────────────────────────
    # $5/$25 across the current Opus line. The $15/$75 this replaces is Opus 3
    # pricing, retired 2026-01-05 — see the module docstring.
    "claude-opus-5": Price("claude-opus-5", 5.00, 25.00),
    "claude-opus-4-8": Price("claude-opus-4-8", 5.00, 25.00),
    "claude-opus-4-7": Price("claude-opus-4-7", 5.00, 25.00),
    "claude-opus-4-6": Price("claude-opus-4-6", 5.00, 25.00),
    "claude-opus-4-5": Price("claude-opus-4-5", 5.00, 25.00),
    "claude-sonnet-5": Price("claude-sonnet-5", *_SONNET_5_STANDARD, note="intro pricing until 2026-08-31"),
    "claude-sonnet-4-6": Price("claude-sonnet-4-6", 3.00, 15.00),
    "claude-sonnet-4-5": Price("claude-sonnet-4-5", 3.00, 15.00),
    # $1.00/$5.00. The 0.80, 0.25 and 0.25 values this replaces were all wrong.
    "claude-haiku-4-5": Price("claude-haiku-4-5", 1.00, 5.00),
    "claude-fable-5": Price("claude-fable-5", 10.00, 50.00),
    # ── OpenAI ───────────────────────────────────────────────────────────────
    "gpt-5.5": Price("gpt-5.5", 3.00, 12.00, verified=False),
    "gpt-5.4": Price("gpt-5.4", 5.00, 20.00, verified=False),
    "gpt-4o": Price("gpt-4o", 2.50, 10.00, verified=False),
    "gpt-4o-mini": Price("gpt-4o-mini", 0.15, 0.60, verified=False),
    "gpt-4.1": Price("gpt-4.1", 2.00, 8.00, verified=False),
    "gpt-4.1-mini": Price("gpt-4.1-mini", 0.10, 0.40, verified=False),
    "o3": Price("o3", 15.00, 60.00, verified=False),
    # ── Google ───────────────────────────────────────────────────────────────
    "gemini-2.5-flash": Price("gemini-2.5-flash", 0.075, 0.30, verified=False),
    "gemini-2.0-flash": Price("gemini-2.0-flash", 0.075, 0.30, verified=False),
    "gemini-2.0-pro": Price("gemini-2.0-pro", 1.25, 5.00, verified=False),
    # ── Local ────────────────────────────────────────────────────────────────
    # Genuinely zero, not "unknown". Callers must not conflate the two.
    "ollama": Price("ollama", 0.0, 0.0),
}

# Family aliases and legacy spellings -> model ID. An alias NEVER carries a
# price: that is the defect this module exists to prevent. Family names resolve
# to the current member of that family, so "opus" tracks the ladder instead of
# freezing at whichever version was current when someone typed it.
_ALIASES: dict[str, str] = {
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5",
    "fable": "claude-fable-5",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5",
    "claude-opus-4-8-fast": "claude-opus-4-8",
    "claude-opus-5-fast": "claude-opus-5",
}


def _normalize(model: str) -> str:
    """Strip provider prefixes and vendor decorations, lowercase."""
    m = (model or "").strip().lower()
    for prefix in ("anthropic/", "openai/", "google/", "gemini/", "ollama/", "litellm/"):
        if m.startswith(prefix):
            m = m[len(prefix) :]
            break
    return m


def resolve(model: str) -> str | None:
    """Canonical model ID for ``model``, or ``None`` if unknown.

    ``None`` means *unknown*, which is not the same as free. Callers must
    surface unknown as unknown rather than coercing it to zero — a zero price
    silently turns missing knowledge into a favourable number.
    """
    m = _normalize(model)
    if m in _PRICES:
        return m
    if m in _ALIASES:
        return _ALIASES[m]
    if m.startswith("ollama") or ":" in m:
        # Ollama tags look like "qwen2.5-coder:7b" — local, and free.
        return "ollama"
    return None


def price_for(model: str, *, as_of: _dt.date | None = None) -> Price | None:
    """:class:`Price` for ``model``, or ``None`` when unknown.

    ``as_of`` selects time-dependent rates (currently only Sonnet 5's
    introductory period). Pass it explicitly in tests so no assertion depends on
    the wall clock.
    """
    key = resolve(model)
    if key is None:
        return None
    price = _PRICES[key]
    if key == "claude-sonnet-5":
        today = as_of or _dt.date.today()
        if today <= _SONNET_5_INTRO_UNTIL:
            return Price(key, *_SONNET_5_INTRO, note=f"introductory pricing through {_SONNET_5_INTRO_UNTIL}")
    return price


def input_rate(model: str, *, as_of: _dt.date | None = None) -> float | None:
    p = price_for(model, as_of=as_of)
    return None if p is None else p.input


def output_rate(model: str, *, as_of: _dt.date | None = None) -> float | None:
    p = price_for(model, as_of=as_of)
    return None if p is None else p.output


def cache_read_rate(model: str, *, as_of: _dt.date | None = None) -> float | None:
    p = price_for(model, as_of=as_of)
    return None if p is None else p.cache_read_rate


def cache_write_rate(model: str, *, as_of: _dt.date | None = None) -> float | None:
    p = price_for(model, as_of=as_of)
    return None if p is None else p.cache_write_rate


def cost_usd(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    *,
    as_of: _dt.date | None = None,
) -> float | None:
    """Total USD for a call, or ``None`` when the model's price is unknown.

    Returning ``None`` rather than ``0.0`` is deliberate and load-bearing: a
    caller that cannot price a call must say so. Coercing to zero is how an
    unpriced model silently becomes free and inflates reported savings.
    """
    p = price_for(model, as_of=as_of)
    if p is None:
        return None
    return (
        (input_tokens / 1_000_000) * p.input
        + (output_tokens / 1_000_000) * p.output
        + (cache_read_tokens / 1_000_000) * p.cache_read_rate
        + (cache_write_tokens / 1_000_000) * p.cache_write_rate
    )


def is_free(model: str) -> bool:
    """True only for models that are *known* to cost nothing.

    An unknown model is not free — it is unknown, and this returns False.
    """
    p = price_for(model)
    return p is not None and p.input == 0.0 and p.output == 0.0


def known_models() -> frozenset[str]:
    return frozenset(_PRICES)


def unverified_models() -> frozenset[str]:
    """Models whose rates were carried forward without independent confirmation."""
    return frozenset(k for k, v in _PRICES.items() if not v.verified)


def staleness_days(*, as_of: _dt.date | None = None) -> int:
    return ((as_of or _dt.date.today()) - PRICES_AS_OF).days


def is_stale(*, as_of: _dt.date | None = None) -> bool:
    """True when the table is older than :data:`STALENESS_DAYS`.

    Chuzom reports money to users. A price table nobody has re-checked in a
    quarter should say so out loud rather than quietly keep reporting.
    """
    if os.environ.get("CHUZOM_SUPPRESS_PRICING_STALENESS"):
        return False
    return staleness_days(as_of=as_of) > STALENESS_DAYS
