# SPDX-License-Identifier: MIT
"""Graded-difficulty self-generated traps (computed gold, RA-disjoint).

Purpose: produce a corpus where a capable cheap model has a MIX of success/fail
(a real difficulty gradient), so the kill-gate can test whether embedding
neighborhoods predict failure. All answers are computed — no dataset lookup.
"""
from __future__ import annotations

import math
import random


def chain(r, steps):
    start = r.randint(3, 20); v = start; parts = []
    for _ in range(steps):
        op = r.choice(["+", "-", "*"]); k = r.randint(2, 12)
        parts.append(f"{op} {k}"); v = {"+": v + k, "-": v - k, "*": v * k}[op]
    return f"Start at {start}, then apply in order: {', '.join(parts)}. Result?", str(v)


def modexp(r, mag):
    base = r.randint(3, 9); exp = r.randint(5, 5 + mag * 8); mod = r.choice([97, 100, 101, 1000, 10007])
    return f"Compute {base}^{exp} mod {mod}.", str(pow(base, exp, mod))


def bigmul(r, digits):
    a = r.randint(10 ** (digits - 1), 10 ** digits - 1); b = r.randint(10 ** (digits - 1), 10 ** digits - 1)
    return f"Compute the exact product {a} × {b}.", str(a * b)


def determinant(r, n):
    m = [[r.randint(-6, 6) for _ in range(n)] for _ in range(n)]
    def det(mat):
        if len(mat) == 1: return mat[0][0]
        s = 0
        for j in range(len(mat)):
            minor = [row[:j] + row[j + 1:] for row in mat[1:]]
            s += ((-1) ** j) * mat[0][j] * det(minor)
        return s
    return f"Find the determinant of the {n}×{n} integer matrix {m}.", str(det(m))


def stack_sim(r, ops):
    seq = []; st = []
    for _ in range(ops):
        if st and r.random() < 0.4:
            st.pop(); seq.append("pop")
        else:
            x = r.randint(1, 99); st.append(x); seq.append(f"push {x}")
    top = st[-1] if st else 0
    return (f"Simulate a stack. Operations in order: {'; '.join(seq)}. "
            f"What is the top of the stack at the end (0 if empty)?", str(top))


def nested(r, depth):
    def build(d):
        if d == 0: return str(r.randint(2, 12)), r.randint(2, 12)
        le, lv = build(d - 1); re_, rv = build(d - 1)
        op = r.choice(["+", "-", "*"])
        val = {"+": lv + rv, "-": lv - rv, "*": lv * rv}[op]
        return f"({le} {op} {re_})", val
    expr, val = build(depth)
    return f"Evaluate exactly: {expr}", str(val)


def count_occ(r, length):
    letters = "abcdefg"; s = "".join(r.choice(letters) for _ in range(length))
    c = r.choice(letters)
    return f"In the string '{s}', how many times does the letter '{c}' appear?", str(s.count(c))


def word_problem(r, steps):
    # multi-step arithmetic word problem, computed gold
    a = r.randint(5, 40); rate = r.randint(2, 9); extra = r.randint(1, 20)
    if steps <= 2:
        return (f"A store has {a} boxes with {rate} items each. How many items total?", str(a * rate))
    sub = r.randint(1, a * rate // 2)
    return (f"A warehouse starts with {a} pallets of {rate} crates each. "
            f"{sub} crates are shipped out and {extra} new crates arrive. How many crates remain?",
            str(a * rate - sub + extra))


def logic_deduction(r, n):
    names = r.sample(["Ann", "Bob", "Cy", "Dee", "Eve", "Fin"], min(n, 6))
    truth = r.choice(names); who = r.choice(names)
    return (f"Exactly one of {', '.join(names)} always tells the truth: it is {truth}. "
            f"Does {who} always tell the truth? Answer Yes or No.", "Yes" if who == truth else "No")


def string_op(r, length):
    w = "".join(r.choice("abcdefghijklmnop") for _ in range(length))
    op = r.choice(["reverse", "rot"])
    if op == "reverse":
        return (f"Reverse the string '{w}'.", w[::-1])
    k = r.randint(1, length - 1)
    return (f"Rotate the string '{w}' left by {k} positions.", w[k:] + w[:k])


def sort_kth(r, length):
    lst = r.sample(range(1, 200), length); k = r.randint(1, length)
    return (f"Sort the list {lst} in ascending order. What is the {k}th smallest value?",
            str(sorted(lst)[k - 1]))


def sequence_next(r, mag):
    start = r.randint(1, 9); step = r.randint(2, 3 + mag)
    kind = r.choice(["arith", "geom", "quad"])
    if kind == "arith":
        seq = [start + step * i for i in range(4)]; nxt = start + step * 4
    elif kind == "geom":
        seq = [start * (step ** i) for i in range(4)]; nxt = start * (step ** 4)
    else:
        seq = [start + i * i * step for i in range(4)]; nxt = start + 16 * step
    return (f"What is the next number in the sequence {', '.join(map(str, seq))}, ?", str(nxt))


def code_trace(r, iters):
    a = r.randint(1, 9); b = r.randint(1, 5)
    lines = f"x = {a}\nfor i in range({iters}):\n    x = x * {b} + i\nprint(x)"
    ns = {}; exec(lines.replace("print(x)", "res = x"), ns)  # noqa: S102
    return (f"What does this Python program print?\n```python\n{lines}\n```", str(ns["res"]))


# difficulty tier -> list of (generator, param) producing progressively harder items
def _tiered(r):
    return [
        (chain, 3), (chain, 6), (chain, 10), (chain, 16), (chain, 24),
        (modexp, 1), (modexp, 2), (modexp, 4), (modexp, 6),
        (bigmul, 2), (bigmul, 3), (bigmul, 4), (bigmul, 5),
        (determinant, 2), (determinant, 3), (determinant, 4),
        (stack_sim, 8), (stack_sim, 16), (stack_sim, 30),
        (nested, 2), (nested, 3), (nested, 4),
        (count_occ, 20), (count_occ, 60), (count_occ, 120),
        # broadened difficulty modes (still computed-answer, RA-disjoint)
        (word_problem, 2), (word_problem, 4),
        (logic_deduction, 3), (logic_deduction, 5),
        (string_op, 6), (string_op, 12), (string_op, 20),
        (sort_kth, 5), (sort_kth, 9), (sort_kth, 14),
        (sequence_next, 1), (sequence_next, 3), (sequence_next, 5),
        (code_trace, 3), (code_trace, 6), (code_trace, 10),
    ]


def generate(n=500, seed=20260707):
    r = random.Random(seed)
    variants = _tiered(r)
    out, seen = [], set()
    i = 0
    while len(out) < n:
        fn, param = r.choice(variants)
        q, a = fn(r, param)
        if q in seen:
            continue
        seen.add(q)
        out.append({"id": f"trap-{i:05d}", "gen": fn.__name__, "difficulty": param,
                    "prompt": q + " Put your final answer in \\boxed{}.", "answer": a})
        i += 1
    return out


if __name__ == "__main__":
    import json
    from collections import Counter
    recs = generate(30)
    print("by generator:", dict(Counter(x["gen"] for x in recs)))
    for x in recs[:4] + recs[-2:]:
        print(json.dumps({k: x[k] for k in ("gen", "difficulty", "prompt", "answer")}))
