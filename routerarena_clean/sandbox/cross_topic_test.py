# SPDX-License-Identifier: MIT
"""Cross-TOPIC transfer test — the real RouterArena condition.

The wording test (transfer_test.py) passed: within a topic, question embeddings
predict cheap-model correctness even after rephrasing. But RouterArena's
difficulty lives ACROSS topics, and the two topics differ in a decisive way:

  • MATH: difficulty is IN THE SURFACE. A gcd of two big coprime numbers *looks*
    hard — big numbers, certain operators. Embeddings can pick this up.
  • FACT: difficulty is OBSCURITY, which is NOT in the surface. "capital of
    France?" and "capital of Kiribati?" are near-identical strings/embeddings,
    yet one is easy and one is not. Nothing in the surface says which.

So: train the correctness predictor on one topic, test on the OTHER. If it
collapses to chance cross-topic (while working within-topic), that is exactly
why query-surface signals don't transfer to RA — proven on self-generated data,
no RA touched. All answers are computed or drawn from hand-authored fact tables
we own (not RA prompts).
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transfer_test import (  # noqa: E402  — reuse embedding/label/centroid/AUC helpers
    _answer, _auc, _centroid, _cos, _embed, _extract_num, _norm, _pairs,
)


def _grade_num(raw: str, gold: str) -> int:
    ext = _extract_num(raw)
    try:
        return int(abs(float(ext) - float(gold)) < 1e-2)
    except ValueError:
        return int(ext == gold.lower())


def _grade_contains(raw: str, gold: str) -> int:
    return int(gold.lower() in raw.lower())


# ── FACT topic: hand-authored tables (we own these; not RA prompts) ───────────
# Deliberately mixes well-known and obscure entries so the cheap model's
# correctness spreads — and the two are indistinguishable by surface.
_CAPITALS = {
    "France": "Paris", "Japan": "Tokyo", "Egypt": "Cairo", "Canada": "Ottawa",
    "Italy": "Rome", "Spain": "Madrid", "Greece": "Athens", "Russia": "Moscow",
    "Kenya": "Nairobi", "Peru": "Lima", "Norway": "Oslo", "Cuba": "Havana",
    # obscure
    "Bhutan": "Thimphu", "Kiribati": "Tarawa", "Eswatini": "Mbabane",
    "Suriname": "Paramaribo", "Brunei": "Bandar Seri Begawan", "Comoros": "Moroni",
    "Vanuatu": "Port Vila", "Tuvalu": "Funafuti", "Palau": "Ngerulmud",
    "Nauru": "Yaren", "Djibouti": "Djibouti", "Malawi": "Lilongwe",
    "Bhutan2": "Thimphu",
}
_SYMBOLS = {
    "gold": "Au", "oxygen": "O", "iron": "Fe", "sodium": "Na", "carbon": "C",
    "hydrogen": "H", "silver": "Ag", "copper": "Cu", "helium": "He", "neon": "Ne",
    # obscure
    "tungsten": "W", "antimony": "Sb", "molybdenum": "Mo", "rhenium": "Re",
    "yttrium": "Y", "niobium": "Nb", "tellurium": "Te", "hafnium": "Hf",
    "praseodymium": "Pr", "rubidium": "Rb", "cadmium": "Cd", "germanium": "Ge",
}


# Atomic numbers — numeric gold, and a 7b fumbles the obscure ones while nailing
# the common ones, giving real correctness variance where difficulty = OBSCURITY
# (not surface). "atomic number of tungsten?" and "…of oxygen?" look identical.
_ATOMIC = {
    "hydrogen": 1, "helium": 2, "carbon": 6, "nitrogen": 7, "oxygen": 8,
    "sodium": 11, "aluminum": 13, "silicon": 14, "sulfur": 16, "calcium": 20,
    "iron": 26, "copper": 29, "zinc": 30, "silver": 47, "gold": 79, "lead": 82,
    # obscure — the hard tail
    "scandium": 21, "vanadium": 23, "cobalt": 27, "gallium": 31, "arsenic": 33,
    "rubidium": 37, "yttrium": 39, "niobium": 41, "molybdenum": 42,
    "technetium": 43, "rhodium": 45, "cadmium": 48, "indium": 49, "antimony": 51,
    "tellurium": 52, "cesium": 55, "hafnium": 72, "tantalum": 73, "tungsten": 74,
    "rhenium": 75, "iridium": 77, "thallium": 81, "bismuth": 83, "neodymium": 60,
    "praseodymium": 59, "europium": 63, "terbium": 65, "holmium": 67, "thulium": 69,
}


def _fact_items(rng: random.Random) -> list[dict]:
    items = []
    for el, num in _ATOMIC.items():
        items.append({
            "prompt": f"What is the atomic number of {el}? Number only.",
            "answer": str(num), "metric": "num", "topic": "fact",
        })
    for country, cap in _CAPITALS.items():
        c = country.rstrip("2")
        items.append({
            "prompt": f"What is the capital city of {c}? Answer with only the city name.",
            "answer": cap, "metric": "contains", "topic": "fact",
        })
    rng.shuffle(items)
    return items


def _math_items(rng: random.Random, n: int) -> list[dict]:
    return [{"prompt": p["a"], "answer": p["answer"], "metric": "num", "topic": "math"}
            for p in _pairs(rng, n)]


def _label_and_embed(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        e = _embed(it["prompt"])
        if e is None:
            continue
        raw = _answer(it["prompt"])
        y = _grade_num(raw, it["answer"]) if it["metric"] == "num" else _grade_contains(raw, it["answer"])
        out.append({"e": _norm(e), "y": y, "topic": it["topic"]})
    return out


def _fit_score(train: list[dict], test: list[dict]) -> float | None:
    corr = [d["e"] for d in train if d["y"] == 1]
    wrong = [d["e"] for d in train if d["y"] == 0]
    if not corr or not wrong:
        return None
    c_ok, c_no = _centroid(corr), _centroid(wrong)
    scores = [_cos(d["e"], c_ok) - _cos(d["e"], c_no) for d in test]
    return _auc(scores, [d["y"] for d in test])


def main() -> int:
    rng = random.Random(20260711)
    math_items = _math_items(rng, 90)
    fact_items = _fact_items(rng)
    print(f"labeling {len(math_items)} math + {len(fact_items)} fact items with the cheap model...")

    M = _label_and_embed(math_items)
    F = _label_and_embed(fact_items)
    mr = sum(d["y"] for d in M) / len(M)
    fr = sum(d["y"] for d in F) / len(F)
    print(f"cheap-correct base rate: math={mr:.2f} (n={len(M)})  fact={fr:.2f} (n={len(F)})")

    rng.shuffle(M); rng.shuffle(F)
    mcut, fcut = int(len(M) * 0.6), int(len(F) * 0.6)
    M_tr, M_te = M[:mcut], M[mcut:]
    F_tr, F_te = F[:fcut], F[fcut:]

    within_m = _fit_score(M_tr, M_te)      # train math → test math
    within_f = _fit_score(F_tr, F_te)      # train fact → test fact
    cross_mf = _fit_score(M_tr, F_te)      # train MATH → test FACT   (the RA condition)
    cross_fm = _fit_score(F_tr, M_te)      # train FACT → test MATH

    print("\n── cross-topic transfer (AUC; 0.5 = chance) ──")
    print(f"  within math (baseline):     {within_m}")
    print(f"  within fact (baseline):     {within_f}")
    print(f"  MATH → FACT (cross-topic):  {cross_mf}")
    print(f"  FACT → MATH (cross-topic):  {cross_fm}")

    print("\n── reading ──")
    crosses = [x for x in (cross_mf, cross_fm) if x is not None]
    if not crosses:
        print("  inconclusive (label imbalance in a topic).")
    elif max(crosses) <= 0.60:
        print("  ✗ Cross-topic prediction collapses to ~chance.")
        print("    → A correctness signal learned on one topic does NOT carry to")
        print("      another. This is the RouterArena wall: query-surface signals")
        print("      can't tell which questions the cheap model will miss across")
        print("      topics. The high-score hope does NOT survive cross-topic.")
    else:
        print("  ✓ Cross-topic prediction holds above chance.")
        print("    → surprising and important: the signal generalises across")
        print("      topics. The RA hope is genuinely alive — pursue it.")
    if within_f is not None and within_f <= 0.60:
        print(f"  NB: even WITHIN fact, AUC={within_f} — obscurity isn't in the")
        print("      surface at all, so no amount of same-topic data learns it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
