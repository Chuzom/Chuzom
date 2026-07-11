# SPDX-License-Identifier: MIT
"""Self-generated synthetic calibration corpus — zero benchmark text.

Every prompt has a programmatically COMPUTED answer, so ground truth is owned by
us and never copied from any dataset. Seeded for reproducibility.
"""
from __future__ import annotations

import random
import math


def _arith(rng):
    a, b = rng.randint(2, 99), rng.randint(2, 99)
    op = rng.choice(["+", "-", "*"])
    return f"What is {a} {op} {b}? Answer with only the number.", str({"+": a + b, "-": a - b, "*": a * b}[op])


def _percent(rng):
    p = rng.choice([10, 15, 20, 25, 40, 50]); n = rng.choice([40, 60, 80, 120, 200])
    return f"What is {p}% of {n}? Answer with only the number.", str(int(p * n / 100))


def _divisors(rng):
    n = rng.choice([12, 18, 24, 36, 48, 60, 72, 100])
    return f"How many positive divisors does {n} have? Answer with only the number.", str(sum(1 for i in range(1, n + 1) if n % i == 0))


def _reverse(rng):
    w = rng.choice(["router", "cascade", "gateway", "signal", "prompt", "vector", "kernel"])
    return f"Reverse the string '{w}'. Answer with only the reversed string.", w[::-1]


def _charcount(rng):
    w = rng.choice(["banana", "mississippi", "assessment", "committee", "balloon"])
    c = rng.choice(list(set(w)))
    return f"How many times does the letter {c} appear in '{w}'? Number only.", str(w.count(c))


def _factorial(rng):
    n = rng.choice([4, 5, 6, 7])
    return f"What is {n} factorial ({n}!)? Answer with only the number.", str(math.factorial(n))


def _speed(rng):
    d = rng.choice([60, 90, 120, 150, 180]); h = rng.choice([1.5, 2, 3])
    return f"A train travels {d} miles in {h} hours. Speed in mph? Number only.", str(int(d / h))


def _multistep(rng):
    a = rng.randint(3, 12); b = rng.randint(2, 9); c = rng.randint(5, 20)
    return f"A box has {a} rows of {b} apples. After selling {c}, how many remain? Number only.", str(a * b - c)


def _modular(rng):
    n = rng.randint(100, 999); m = rng.choice([7, 9, 11, 13])
    return f"What is the remainder when {n} is divided by {m}? Number only.", str(n % m)


def _bigmul(rng):
    a = rng.randint(23, 97); b = rng.randint(23, 97)
    return f"What is {a} times {b}? Answer with only the number.", str(a * b)


def _seq(rng):
    start = rng.randint(1, 5); step = rng.randint(2, 6)
    seq = [start + step * i + i * i for i in range(4)]
    return f"Next number in the sequence {', '.join(map(str, seq))}, ? Number only.", str(start + step * 4 + 16)


_GENERATORS = [_arith, _percent, _divisors, _reverse, _charcount, _factorial, _speed,
               _multistep, _modular, _bigmul, _seq]


def _gcd_lcm(rng):
    a, b = rng.randint(12, 400), rng.randint(12, 400)
    if rng.random() < 0.5:
        return f"What is the greatest common divisor of {a} and {b}? Answer with only the number.", str(math.gcd(a, b))
    return f"What is the least common multiple of {a} and {b}? Answer with only the number.", str(a * b // math.gcd(a, b))


def _primefactor(rng):
    n = rng.choice([84, 90, 126, 132, 156, 198, 210, 264, 315, 429])
    factors, m, d = [], n, 2
    while d * d <= m:
        while m % d == 0:
            factors.append(d); m //= d
        d += 1
    if m > 1:
        factors.append(m)
    return f"What is the largest prime factor of {n}? Answer with only the number.", str(max(factors))


def _linear2var(rng):
    x, y = rng.randint(2, 20), rng.randint(2, 20)
    a1, b1 = rng.randint(1, 5), rng.randint(1, 5)
    a2, b2 = rng.randint(1, 5), rng.randint(1, 5)
    if a1 * b2 - a2 * b1 == 0:
        return _linear2var(rng)
    c1, c2 = a1 * x + b1 * y, a2 * x + b2 * y
    return f"Solve for x: {a1}x + {b1}y = {c1} and {a2}x + {b2}y = {c2}. Answer with only the value of x.", str(x)


def _baseconvert(rng):
    n = rng.randint(50, 500)
    base = rng.choice([2, 8, 16])
    digs = "0123456789ABCDEF"
    m, out = n, ""
    while m:
        out = digs[m % base] + out; m //= base
    return f"Convert the decimal number {n} to base {base}. Answer with only the converted number (digits only, no prefix).", out


def _compoundinterest(rng):
    p = rng.choice([100, 200, 500, 1000]); r = rng.choice([5, 10, 20]); t = rng.choice([2, 3])
    amt = round(p * (1 + r / 100) ** t)
    return f"${p} is invested at {r}% annual compound interest for {t} years. What is the final amount, rounded to the nearest whole dollar? Number only.", str(amt)


def _workrate(rng):
    a, b = rng.choice([4, 6, 8, 10, 12]), rng.choice([4, 6, 8, 10, 12])
    if a == b:
        return _workrate(rng)
    hours = 1 / (1 / a + 1 / b)
    return (f"Pipe A fills a tank in {a} hours alone; pipe B fills it in {b} hours alone. "
            f"Working together, how many hours to fill the tank? Answer with only the number, rounded to 2 decimal places.", f"{hours:.2f}")


def _fibext(rng):
    start_a, start_b = rng.randint(1, 5), rng.randint(1, 5)
    n = rng.choice([9, 10, 11, 12])
    a, b = start_a, start_b
    for _ in range(n - 2):
        a, b = b, a + b
    return (f"A sequence starts {start_a}, {start_b} and each next term is the sum of the previous two. "
            f"What is the {n}th term? Number only.", str(b))


def _combinatorics(rng):
    n, k = rng.randint(5, 12), rng.randint(2, 4)
    return f"How many ways can you choose {k} items from a set of {n} distinct items (order doesn't matter)? Number only.", str(math.comb(n, k))


_HARD_GENERATORS = [_gcd_lcm, _primefactor, _linear2var, _baseconvert, _compoundinterest,
                     _workrate, _fibext, _combinatorics]


def generate(n: int = 200, seed: int = 20260704) -> list[dict]:
    rng = random.Random(seed)
    out, seen = [], set()
    while len(out) < n:
        prompt, ans = rng.choice(_GENERATORS)(rng)
        if prompt in seen:
            continue
        seen.add(prompt)
        out.append({"prompt": prompt, "answer": ans, "kind": "short"})
    return out


def generate_hard(n: int = 150, seed: int = 20260706) -> list[dict]:
    """Harder self-generated, computed-ground-truth corpus meant to discriminate
    reasoning quality between two strong models (the easy corpus saturates near
    100% for any capable model and can't tell them apart)."""
    rng = random.Random(seed)
    out, seen = [], set()
    while len(out) < n:
        prompt, ans = rng.choice(_HARD_GENERATORS)(rng)
        if prompt in seen:
            continue
        seen.add(prompt)
        out.append({"prompt": prompt, "answer": ans, "kind": "hard"})
    return out


if __name__ == "__main__":
    import json
    recs = generate()
    print(json.dumps(recs[:5], indent=2))
    print(f"... {len(recs)} total, seed-reproducible")
