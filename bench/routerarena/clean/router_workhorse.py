# SPDX-License-Identifier: MIT
"""Workhorse router — lean on one cheap-but-strong model; route only trivially
easy queries down. Content-based only; no RA fingerprinting, no RA-outcome tuning.

Rationale (see sandbox analysis): the arena score is a weighted harmonic mean of
accuracy and log-cost with beta=0.1, so at low cost (~$0.07/1k) it only rewards
~77% accuracy to clear 0.76. A cheap-but-strong model (qwen3-235b-a22b-2507:
MMLU-Pro ~84.8%, RA cost $0.071/$0.10) used as the DEFAULT beats a cascade that
ships to weak models to save cost — cost-saving the arena formula barely rewards
while the accuracy loss is heavily penalized.

Compliance: routing decisions use INTRINSIC query content only (length + simple
structural cues). No prompt-template fingerprints, no per-dataset rules, no
supervision derived from RouterArena accuracy/judge/oracle. Model-capability
priors come from PUBLISHED benchmarks (public knowledge).
"""
from __future__ import annotations

import re

# Primary: strong AND cheap on RA. Everything routes here by default.
WORKHORSE = "qwen/qwen3-235b-a22b-2507"
# Optional down-route for trivially-easy queries (cheaper, no accuracy loss on
# genuinely trivial items). DISABLED by default — accuracy-max v1 uses workhorse
# for everything; enable only if the one-shot shows cost headroom to trade.
EASY_MODEL = "qwen/qwen3.5-9b"

# Name variants RA may expose for the workhorse, in preference order.
_WORKHORSE_ALIASES = [
    "qwen/qwen3-235b-a22b-2507",
    "qwen_qwen3-235b-a22b-2507",
    "Qwen/Qwen3-235B-A22B-Instruct-2507",
]

# Intrinsic "trivially easy" cues — short, single-clause, factual/arithmetic.
# Deliberately CONSERVATIVE: a misclassified hard query costs accuracy, which we
# cannot afford, so the gate errs strongly toward the workhorse.
_TRIVIAL_MAXWORDS = 12
_TRIVIAL_ARITH = re.compile(r"^\s*(?:what\s+is\s+)?\d[\d\s\+\-\*/×÷=\.]*\??\s*$", re.I)
_MULTISENTENCE = re.compile(r"[.!?].+[.!?]")
_HARD_CUES = re.compile(
    r"```|\\boxed|\\frac|\btranslate\b|\bprove\b|\banalyze\b|\bexplain\b|"
    r"passage|paragraph|following|step[- ]by[- ]step", re.I)


def is_trivially_easy(query: str) -> bool:
    """Intrinsic-content gate — true only for obviously trivial short queries."""
    q = query.strip()
    if _HARD_CUES.search(q) or _MULTISENTENCE.search(q):
        return False
    if _TRIVIAL_ARITH.match(q):
        return True
    return len(q.split()) <= _TRIVIAL_MAXWORDS and "\n" not in q


def _resolve(name_or_aliases, available: set[str]) -> str | None:
    if isinstance(name_or_aliases, str):
        name_or_aliases = [name_or_aliases]
    for n in name_or_aliases:
        if n in available:
            return n
    return None


def pick_model(query: str, available_models, *, enable_easy: bool = False) -> str:
    """Return the model id to answer `query`. Falls back gracefully if the
    preferred model isn't in RA's available set."""
    avail = set(available_models)
    workhorse = _resolve(_WORKHORSE_ALIASES, avail)
    if workhorse is None:  # workhorse absent — pick the cheapest capable present
        workhorse = _fallback_workhorse(avail) or next(iter(avail), WORKHORSE)
    if enable_easy:
        easy = _resolve(EASY_MODEL, avail)
        if easy and is_trivially_easy(query):
            return easy
    return workhorse


def _fallback_workhorse(avail: set[str]) -> str | None:
    """If the primary workhorse is unavailable, prefer other cheap-strong models."""
    for cand in ("openai_gpt-oss-120b", "qwen/qwen3.5-flash-02-23",
                 "deepseek/deepseek-v4-flash", "deepseek-v3.2",
                 "qwen/qwen3-30b-a3b-instruct-2507"):
        if cand in avail:
            return cand
    return None


if __name__ == "__main__":
    # Sanity: exercise the policy on a spread of query shapes (no API, no RA).
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from synthetic_gen import generate, generate_hard
    avail = {WORKHORSE, EASY_MODEL, "deepseek-v3.2"}
    samples = [r["prompt"] for r in generate(30)] + [r["prompt"] for r in generate_hard(20)]
    samples += ["What is 2+2?", "Capital of France?",
                "Translate the following sentence into German: The cat sleeps.",
                "Prove that sqrt(2) is irrational.", "```def f(x): return x```"]
    from collections import Counter
    off = Counter(pick_model(q, avail, enable_easy=False) for q in samples)
    on = Counter(pick_model(q, avail, enable_easy=True) for q in samples)
    print("workhorse-only (v1):", {k.split('/')[-1]: v for k, v in off.items()})
    print("easy-enabled       :", {k.split('/')[-1]: v for k, v in on.items()})
    print("\ntrivially-easy examples routed down:")
    for q in samples:
        if is_trivially_easy(q):
            print("  EASY :", q[:60])
