# SPDX-License-Identifier: MIT
"""Grounded verification (selection-mode) — the council's cleanest, highest-ceiling
lever, and the ONLY signal that is causally independent of model consensus.

Idea: for each candidate answer a model ALREADY produced, run a deterministic,
objective check DERIVED FROM THE QUERY ITSELF (not RA gold):
  • code  → extract the model's code, EXECUTE it against tests → pass/fail
  • math  → recompute a parseable computation independently → match/mismatch
  • chess → validate move legality with an engine (future)
Because passing an execution test is *causally* tied to correctness, this should
give the correctness SEPARATION that agreement lacked (agreement separation ≈ 0).

COMPLIANCE: checks use the query content + public tools + the model's own output.
No RA labels/accuracy/judge/oracle. This module is validated ONLY on
self-generated problems here; any RA use is a single downstream measurement.

This file: the code verifier + a SELF-GENERATED coding corpus + a separation
demo. If verification-pass strongly predicts correctness on self-gen data, the
mechanism is proven and worth extending to RA's verifiable slice.
"""
from __future__ import annotations

import io
import re
import signal
from contextlib import redirect_stdout


# ── Code extraction + execution ───────────────────────────────────────────────
def extract_code(text: str) -> str:
    """Pull the last fenced code block; fall back to the whole text."""
    blocks = re.findall(r"```(?:[a-zA-Z0-9_+-]*)\n(.*?)```", text or "", re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    return (text or "").strip()


class _Timeout(Exception):
    pass


def _run_functional(code: str, func: str, tests: list[tuple], timeout: int = 4):
    """Exec code, call func(*args) for each (args, expected); return (n_pass, n_total).
    Sandbox is best-effort (this is offline self-gen validation, not untrusted input)."""
    def _handler(signum, frame):
        raise _Timeout()
    ns: dict = {}
    try:
        signal.signal(signal.SIGALRM, _handler)
        signal.alarm(timeout)
        with redirect_stdout(io.StringIO()):
            exec(code, ns)
        fn = ns.get(func)
        if not callable(fn):
            # try any callable if the exact name isn't found (class-wrapped etc.)
            cands = [v for v in ns.values() if callable(v) and getattr(v, "__module__", None) is None]
            fn = cands[-1] if cands else None
        if fn is None:
            return 0, len(tests)
        npass = 0
        for args, expected in tests:
            try:
                with redirect_stdout(io.StringIO()):
                    out = fn(*args) if isinstance(args, (list, tuple)) else fn(args)
                if out == expected:
                    npass += 1
            except Exception:
                pass
        return npass, len(tests)
    except Exception:
        return 0, len(tests)
    finally:
        signal.alarm(0)


def verify_code(response: str, func: str, visible_tests: list[tuple]) -> float:
    """Fraction of VISIBLE tests the model's code passes (the routing signal)."""
    code = extract_code(response)
    npass, ntot = _run_functional(code, func, visible_tests)
    return npass / ntot if ntot else 0.0


# ── Self-generated coding corpus (computed refs + held-out tests) ─────────────
def _corpus():
    """Templated problems: (prompt, func_name, reference_fn, arg_generator)."""
    return [
        ("Write a Python function `sum_digits(n)` returning the sum of the decimal digits of a non-negative integer n. Put the function in a ```python code block.",
         "sum_digits", lambda n: sum(int(c) for c in str(n)), lambda r: [(r.randint(0, 99999),) for _ in range(6)]),
        ("Write a Python function `is_prime(n)` returning True iff n is prime (n>=2 may be prime; n<2 is not). Put it in a ```python code block.",
         "is_prime", lambda n: n >= 2 and all(n % d for d in range(2, int(n**0.5) + 1)), lambda r: [(r.randint(1, 200),) for _ in range(6)]),
        ("Write a Python function `count_vowels(s)` returning the number of vowels (a,e,i,o,u, case-insensitive) in string s. Use a ```python code block.",
         "count_vowels", lambda s: sum(c.lower() in "aeiou" for c in s), lambda r: [(r.choice(["Hello World", "AEIOU", "rhythm", "Programming"]),) for _ in range(6)]),
        ("Write a Python function `nth_fib(n)` returning the nth Fibonacci number with nth_fib(1)=1, nth_fib(2)=1. Use a ```python code block.",
         "nth_fib", lambda n: (lambda a, b, k: [((a := (b := (a + b)) - a)) for _ in range(k)] and b)(0, 1, n) if False else _fib(n), lambda r: [(r.randint(1, 20),) for _ in range(6)]),
        ("Write a Python function `gcd(a,b)` returning the greatest common divisor of positive integers a and b. Use a ```python code block.",
         "gcd", lambda a, b: __import__("math").gcd(a, b), lambda r: [(r.randint(2, 500), r.randint(2, 500)) for _ in range(6)]),
        ("Write a Python function `reverse_words(s)` returning s with the order of space-separated words reversed. Use a ```python code block.",
         "reverse_words", lambda s: " ".join(s.split()[::-1]), lambda r: [(r.choice(["the quick brown fox", "a b c d", "hello world"]),) for _ in range(6)]),
        ("Write a Python function `is_palindrome(s)` returning True iff string s reads the same forwards and backwards (case-sensitive, spaces count). Use a ```python code block.",
         "is_palindrome", lambda s: s == s[::-1], lambda r: [(r.choice(["racecar", "hello", "abba", "python"]),) for _ in range(6)]),
        ("Write a Python function `second_largest(lst)` returning the second-largest distinct value in a list of integers (assume at least two distinct values). Use a ```python code block.",
         "second_largest", lambda lst: sorted(set(lst))[-2], lambda r: [([r.randint(1, 50) for _ in range(6)],) for _ in range(6)]),
        ("Write a Python function `digit_product(n)` returning the product of the decimal digits of non-negative integer n. Use a ```python code block.",
         "digit_product", lambda n: __import__("math").prod(int(c) for c in str(n)), lambda r: [(r.randint(0, 9999),) for _ in range(6)]),
        ("Write a Python function `collatz_steps(n)` returning how many steps to reach 1 from positive integer n under the Collatz map (n->n/2 if even, 3n+1 if odd); collatz_steps(1)=0. Use a ```python code block.",
         "collatz_steps", lambda n: _collatz(n), lambda r: [(r.randint(1, 100),) for _ in range(6)]),
        ("Write a Python function `count_words(s)` returning the number of whitespace-separated words in string s. Use a ```python code block.",
         "count_words", lambda s: len(s.split()), lambda r: [(r.choice(["one two three", "  padded  words  ", "single", "a b c d e"]),) for _ in range(6)]),
    ]


def _collatz(n):
    steps = 0
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        steps += 1
    return steps


def _fib(n):
    a, b = 1, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return a


def build_coding_problems(seed: int = 20260706):
    import random
    r = random.Random(seed)
    out = []
    for prompt, func, ref, gen in _corpus():
        cases = []
        for args in gen(r):
            try:
                cases.append((args, ref(*args)))
            except Exception:
                pass
        # split into visible (verifier sees) and hidden (ground-truth for "correct")
        visible, hidden = cases[:3], cases[3:]
        out.append({"prompt": prompt, "func": func, "visible": visible, "hidden": hidden})
    return out


if __name__ == "__main__":
    # Offline self-test of the executor (no model, no API): a correct vs a wrong solution.
    probs = build_coding_problems()
    print(f"self-gen coding problems: {len(probs)}")
    correct_sol = "```python\ndef sum_digits(n):\n    return sum(int(c) for c in str(n))\n```"
    wrong_sol = "```python\ndef sum_digits(n):\n    return n % 9\n```"
    p = probs[0]
    print("correct sol — visible pass frac:", verify_code(correct_sol, p["func"], p["visible"]),
          "| hidden pass frac:", verify_code(correct_sol, p["func"], p["hidden"]))
    print("wrong   sol — visible pass frac:", verify_code(wrong_sol, p["func"], p["visible"]),
          "| hidden pass frac:", verify_code(wrong_sol, p["func"], p["hidden"]))
    print("\n→ if visible-pass tracks hidden-pass, verification is a valid correctness signal.")
