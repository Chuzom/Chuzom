# SPDX-License-Identifier: MIT
"""Approach #1 — capability-atlas TYPE router.

Route by INTRINSIC query content to the model that PUBLISHED benchmarks rank best
for that task type. Cheap (rule-based detection, one model call per query),
compliant (content-only detection + public-benchmark model priors — no RA prompt
fingerprints, no RA-outcome tuning).

Deliberately conservative: only two obvious "right-tool" diversions —
  • code  → a code-specialist (Qwen coders top public HumanEval/LiveCodeBench for size)
  • translation → a strong multilingual model (Gemini Flash leads public FLORES/WMT)
Everything else → a strong general default. Chess/knowledge/etc. are NOT given
bespoke routes (that would require the RA breakdown to justify — off-limits).

Model ids below are OpenRouter call names for the sub_10 preview; RA prices
(model_cost.json) are attached so the arena estimate matches server scoring.
"""
from __future__ import annotations

import re

# Intrinsic-content type cues (generic instructions, NOT RA templates).
_CODE = re.compile(
    r"```|\bdef\s+\w+\s*\(|\bclass\s+\w+\b|#include\b|\bimport\s+\w+|"
    r"\bwrite\s+(?:a|an)\s+(?:\w+\s+)?(?:function|program|script|code)\b|"
    r"\breturn\s+|\bstdin\b|\bstdout\b|\balgorithm\b", re.I)
_TRANSLATE = re.compile(r"\btranslat(?:e|es|ion|ing)\b", re.I)

# type -> (OpenRouter model id, RA price (in,out) $/M)
TYPE_MODELS: dict[str, tuple[str, tuple[float, float]]] = {
    "code":        ("qwen/qwen3-coder-30b-a3b-instruct", (0.07, 0.27)),
    "translation": ("google/gemini-2.5-flash-lite",      (0.10, 0.40)),
    "default":     ("deepseek/deepseek-v3.2",             (0.28, 0.42)),
}


def detect_type(query: str) -> str:
    if _CODE.search(query):
        return "code"
    if _TRANSLATE.search(query):
        return "translation"
    return "default"


def route(query: str) -> tuple[str, str, tuple[float, float]]:
    """Return (type_label, openrouter_model, ra_price)."""
    t = detect_type(query)
    model, price = TYPE_MODELS[t]
    return t, model, price


if __name__ == "__main__":
    tests = [
        "Translate the following sentence from German to English: Der Hund schläft.",
        "Write a Python function that returns the nth Fibonacci number.",
        "```python\nprint(sum(range(10)))\n```\nWhat does this output?",
        "What is the capital of Australia?",
        "Compute the derivative of x^2 + 3x.",
        "Which of the following is a noble gas? A) Oxygen B) Argon C) Nitrogen D) Carbon",
    ]
    for q in tests:
        t, m, _ = route(q)
        print(f"  [{t:11s}] {m.split('/')[-1]:32s} :: {q[:50]}")
