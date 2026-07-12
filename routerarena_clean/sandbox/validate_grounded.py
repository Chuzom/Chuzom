# SPDX-License-Identifier: MIT
"""Validate grounded code-verification on SELF-GENERATED problems (no RA data).

Measures the SEPARATION that agreement lacked:
  P(answer actually correct | passes all VISIBLE tests)  vs
  P(answer actually correct | fails a visible test)
"Actually correct" = passes the HELD-OUT hidden tests. If visible-pass strongly
predicts hidden-correctness, grounded verification is a real correctness signal
(agreement's separation was ~0.009).
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_ra_mechanism import call, key  # noqa: E402
from grounded_verify import build_coding_problems, verify_code  # noqa: E402

MODELS = ["qwen/qwen3.5-9b", "deepseek/deepseek-v4-flash", "qwen/qwen3-coder-30b-a3b-instruct"]


def main():
    k = key()
    probs = build_coding_problems()
    jobs = [(p, m) for p in probs for m in MODELS]

    # 1) fetch all responses in parallel (network-bound)
    def fetch(p, m):
        resp, *_ = call(m, p["prompt"], k, max_tokens=600)
        return (p, m, resp)
    fetched = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(fetch, p, m) for p, m in jobs]
        for f in as_completed(futs):
            fetched.append(f.result())

    # 2) verify SERIALLY in the main thread (signal-based timeout needs main thread)
    rows = []
    for p, m, resp in fetched:
        vis = verify_code(resp, p["func"], p["visible"])
        hid = verify_code(resp, p["func"], p["hidden"])
        rows.append({"func": p["func"], "model": m, "visible": vis, "hidden": hid,
                     "pass_visible": vis == 1.0, "correct": hid == 1.0})

    n = len(rows)
    passv = [r for r in rows if r["pass_visible"]]
    failv = [r for r in rows if not r["pass_visible"]]
    p_correct_given_pass = sum(r["correct"] for r in passv) / len(passv) if passv else float("nan")
    p_correct_given_fail = sum(r["correct"] for r in failv) / len(failv) if failv else float("nan")
    overall_correct = sum(r["correct"] for r in rows) / n

    print(f"self-gen coding answers: {n}  ({len(probs)} problems x {len(MODELS)} models)")
    print(f"overall correctness: {overall_correct:.3f}")
    print(f"passed all visible tests: {len(passv)}/{n} | failed: {len(failv)}/{n}")
    print()
    print(f"P(correct | passes all visible) = {p_correct_given_pass:.3f}   (n={len(passv)})")
    print(f"P(correct | fails a visible)    = {p_correct_given_fail:.3f}   (n={len(failv)})")
    sep = (p_correct_given_pass - p_correct_given_fail) if (passv and failv) else float("nan")
    print(f"SEPARATION = {sep:.3f}    (agreement's separation was 0.009)")
    print()
    # what a router gains: pick a model whose code passes visible; accuracy on that slice
    print("→ routing rule 'ship the model that passes all visible tests':")
    print(f"   accuracy among shippable answers = {p_correct_given_pass:.3f}")
    # per-model
    from collections import defaultdict
    by = defaultdict(lambda: [0, 0])
    for r in rows:
        by[r["model"]][0] += r["correct"]; by[r["model"]][1] += 1
    print("\nper-model self-gen coding accuracy:")
    for m, (c, t) in by.items():
        print(f"  {c/t:.2f}  {m.split('/')[-1]}")


if __name__ == "__main__":
    main()
