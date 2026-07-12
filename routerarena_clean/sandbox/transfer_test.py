# SPDX-License-Identifier: MIT
"""Surface-transfer test — does a query-embedding correctness predictor survive
a change of wording? This is the falsifiable test of the hope that "synthetic
data + the new embedding router → high RouterArena score."

Method (controlled A/B, wording is the ONLY variable):
  1. Generate matched problem pairs: the SAME computed-answer problem phrased two
     ways — surface A and surface B. Same difficulty, same gold, different words.
  2. Measure a cheap model's correctness per problem (label: right/wrong).
  3. Embed every phrasing with nomic-embed-text (the new router's embedding).
  4. Build the new router's mechanism — a correct/wrong centroid pair — on
     TRAIN-split surface-A embeddings + labels.
  5. Score held-out items two ways:
       • in-distribution: held-out surface-A embeddings  → AUC_indist
       • cross-surface:   the SAME held-out items, surface-B → AUC_cross
  If AUC_indist is high but AUC_cross ≈ 0.5, the predictor keyed on WORDING, not
  difficulty — it will not transfer to RouterArena's different surface, and the
  high-score hope is falsified on self-generated data alone (no RA touched).

Pure-python (no ML deps); embeddings via local Ollama.
"""

from __future__ import annotations

import json
import math
import random
import urllib.request

_OLLAMA = "http://localhost:11434"
_EMBED_MODEL = "nomic-embed-text"
_CHEAP = "qwen2.5-coder:7b"


# ── matched problem pairs (answer, surface-A prompt, surface-B prompt) ─────────

def _pairs(rng: random.Random, n: int) -> list[dict]:
    out, seen = [], set()
    makers = [_gcd, _primefac, _base, _compound, _comb, _modpow, _work]
    while len(out) < n:
        ans, a, b = rng.choice(makers)(rng)
        if a in seen:
            continue
        seen.add(a)
        out.append({"answer": ans, "a": a, "b": b})
    return out


def _gcd(rng):
    x, y = rng.randint(24, 240), rng.randint(24, 240)
    g = math.gcd(x, y)
    return (str(g),
            f"What is the gcd of {x} and {y}? Number only.",
            f"Find the largest integer that divides both {x} and {y} exactly. Give just the number.")


def _primefac(rng):
    n = rng.choice([84, 120, 180, 210, 360, 495, 616, 900])
    c = 0
    m = n
    for p in range(2, n + 1):
        while m % p == 0:
            c += 1
            m //= p
    return (str(c),
            f"How many prime factors (with multiplicity) does {n} have? Number only.",
            f"Count the total prime factors of {n}, counting repeats. Just the count.")


def _base(rng):
    n = rng.randint(20, 250)
    b = rng.choice([2, 3, 8])
    digits = ""
    m = n
    while m:
        digits = str(m % b) + digits
        m //= b
    return (digits,
            f"Convert {n} to base {b}. Answer with only the digits.",
            f"Write the number {n} in base-{b} notation. Digits only, no spaces.")


def _compound(rng):
    p = rng.choice([100, 200, 500]); r = rng.choice([2, 5, 10]); t = rng.choice([2, 3])
    amt = round(p * (1 + r / 100) ** t, 2)
    return (str(amt),
            f"{p} grows at {r}% compounded yearly for {t} years. Final amount? Number only.",
            f"If you invest {p} at {r} percent annual compound interest for {t} years, what's the total? Number only.")


def _comb(rng):
    n, k = rng.randint(6, 14), rng.randint(2, 5)
    return (str(math.comb(n, k)),
            f"How many ways to choose {k} from {n} (order irrelevant)? Number only.",
            f"Count the distinct {k}-element subsets of a {n}-element set. Just the number.")


def _modpow(rng):
    base, e, m = rng.randint(2, 9), rng.randint(3, 6), rng.choice([7, 11, 13])
    return (str(pow(base, e, m)),
            f"What is {base}^{e} mod {m}? Number only.",
            f"Compute the remainder of {base} raised to the {e} when divided by {m}. Number only.")


def _work(rng):
    a, b = rng.choice([(4, 6), (3, 6), (2, 3), (6, 12)])
    # combined rate → time = ab/(a+b), keep integer-ish
    val = round(a * b / (a + b), 2)
    return (str(val),
            f"One worker takes {a}h, another {b}h. Together, hours to finish? Number only.",
            f"If job X needs {a} hours solo and job-mate Y needs {b} hours solo, how long together? Number only.")


# ── ollama helpers ────────────────────────────────────────────────────────────

def _embed(text: str) -> list[float] | None:
    try:
        payload = json.dumps({"model": _EMBED_MODEL, "prompt": text}).encode()
        req = urllib.request.Request(f"{_OLLAMA}/api/embeddings", data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("embedding")
    except Exception:
        return None


def _answer(prompt: str) -> str:
    try:
        payload = json.dumps({"model": _CHEAP, "prompt": prompt + " /no_think",
                              "stream": False, "options": {"temperature": 0, "num_predict": 128}}).encode()
        req = urllib.request.Request(f"{_OLLAMA}/api/generate", data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("response", "")
    except Exception:
        return ""


def _extract_num(raw: str) -> str:
    import re
    nums = re.findall(r"-?\d+\.?\d*", raw.replace(",", ""))
    return nums[-1].rstrip(".") if nums else raw.strip().lower()


def _grade(raw: str, gold: str) -> int:
    ext = _extract_num(raw)
    try:
        return int(abs(float(ext) - float(gold)) < 1e-2)
    except ValueError:
        return int(ext == gold.lower())


# ── centroid mechanism + AUC ──────────────────────────────────────────────────

def _norm(v):
    m = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / m for x in v]


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def _centroid(vs):
    dim = len(vs[0])
    acc = [0.0] * dim
    for v in vs:
        for i, x in enumerate(v):
            acc[i] += x
    return _norm([x / len(vs) for x in acc])


def _auc(scores, labels):
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg:
        return None
    wins = sum((1 if p > n else 0.5 if p == n else 0) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def main() -> int:
    rng = random.Random(20260711)
    items = _pairs(rng, 120)
    print(f"generated {len(items)} matched pairs; labeling with {_CHEAP}...")

    # Label correctness per problem (measured on surface A), embed both surfaces.
    labeled = []
    for it in items:
        ea, eb = _embed(it["a"]), _embed(it["b"])
        if ea is None or eb is None:
            continue
        lab = _grade(_answer(it["a"]), it["answer"])
        labeled.append({"ea": _norm(ea), "eb": _norm(eb), "y": lab})
    n = len(labeled)
    base_rate = sum(d["y"] for d in labeled) / n
    print(f"labeled {n} items; cheap-correct base rate = {base_rate:.2f}")

    rng.shuffle(labeled)
    cut = int(n * 0.6)
    train, test = labeled[:cut], labeled[cut:]

    corr = [d["ea"] for d in train if d["y"] == 1]
    wrong = [d["ea"] for d in train if d["y"] == 0]
    if not corr or not wrong:
        print("degenerate labels (all same) — increase N or difficulty spread.")
        return 1
    c_ok, c_no = _centroid(corr), _centroid(wrong)

    # score = closeness-to-correct minus closeness-to-wrong (higher ⇒ predict OK)
    y = [d["y"] for d in test]
    s_indist = [_cos(d["ea"], c_ok) - _cos(d["ea"], c_no) for d in test]  # same surface (A)
    s_cross = [_cos(d["eb"], c_ok) - _cos(d["eb"], c_no) for d in test]   # other surface (B)

    auc_in = _auc(s_indist, y)
    auc_cr = _auc(s_cross, y)
    print("\n── surface-transfer result ──")
    print(f"  test items={len(test)}  base_rate={base_rate:.2f}")
    print(f"  AUC in-distribution (surface A, same wording): {auc_in}")
    print(f"  AUC cross-surface   (surface B, new wording):  {auc_cr}")
    print("\n── reading ──")
    if auc_in is None or auc_cr is None:
        print("  inconclusive (label imbalance).")
    elif auc_cr <= 0.58:
        print(f"  ✗ Predictor collapses to ~chance on new wording (AUC {auc_cr}).")
        print("    → keyed on SURFACE, not difficulty. Will NOT transfer to RA's")
        print("      different surface. The high-score hope is falsified, cleanly,")
        print("      on self-generated data — no RouterArena touched.")
    else:
        print(f"  ✓ Predictor holds across wording (AUC {auc_cr}).")
        print("    → captures real difficulty, not surface. Worth pursuing on RA.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
