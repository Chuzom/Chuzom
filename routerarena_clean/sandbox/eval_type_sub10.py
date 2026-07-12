# SPDX-License-Identifier: MIT
"""RA sub_10 evaluation of Approach #1 (type router) — fixed, principled design.

Each query is routed by intrinsic content (router_type.route) to a specialist or
the default, called live via OpenRouter, graded with RA's official metrics, and
costed with RA's own pricing. Exploratory measurement on a fixed design.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # routerarena_clean/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import Grader, arena_score  # noqa: E402
from router_type import route            # noqa: E402

_HERE = Path(__file__).resolve().parent
SCRATCH = Path("/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/"
               "c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad")
EP = "https://openrouter.ai/api/v1/chat/completions"


def _key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k and (SCRATCH / ".orkey").exists():
        k = (SCRATCH / ".orkey").read_text().strip()
    if not k:
        raise RuntimeError("No OpenRouter key.")
    return k


def call(model, prompt, key, max_tokens=1500):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(EP, data=payload, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
                msg = d["choices"][0]["message"].get("content") or ""
                u = d.get("usage", {})
                return msg, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), None
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:150]
            if e.code in (400, 401, 403, 404):
                return "", 0, 0, f"HTTP_{e.code}:{body}"
            time.sleep(2); last = f"HTTP_{e.code}"
        except Exception as e:
            time.sleep(2); last = str(e)
    return "", 0, 0, last


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    key = _key()
    g = Grader()
    labels = json.load(open(SCRATCH / "sub10_labels.json"))
    full = json.load(open(SCRATCH / "chuzom-v3-pred.json"))
    prompt_by_gi = {r["global index"]: r["prompt"] for r in full}
    items = [{"gi": r["gi"], "dataset": r["dataset"], "answer": r["answer"],
              "prompt": prompt_by_gi[r["gi"]]}
             for r in labels if r["gi"] in prompt_by_gi]
    items.sort(key=lambda x: str(x["gi"]))
    if args.n > 0:
        items = items[:args.n]
    print(f"TYPE router (#1) sub_10: {len(items)} RA prompts (workers={args.workers}) "
          f"[RA-DATA TOUCH — fixed design]", flush=True)

    def work(it):
        t, model, (pin, pout) = route(it["prompt"])
        raw, pt, ct, err = call(model, it["prompt"], key)
        acc = 0.0 if err else g.grade_one(raw, it["answer"], it["dataset"])
        cost = (pt * pin + ct * pout) / 1e6
        return {"gi": it["gi"], "dataset": it["dataset"], "type": t, "model": model,
                "acc": acc, "cost": cost, "err": err}

    results, t0, done, errs = [], time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, it) for it in items]
        for f in as_completed(futs):
            r = f.result(); results.append(r); errs += int(bool(r["err"])); done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(items)} ({time.time()-t0:.0f}s) errs={errs}", flush=True)

    n = len(results)
    acc = sum(r["acc"] for r in results) / n
    cost_1k = sum(r["cost"] for r in results) / n * 1000
    arena = arena_score(cost_1k, acc)

    by_type = defaultdict(lambda: [0, 0.0, 0])  # count, acc_sum, err
    for r in results:
        b = by_type[r["type"]]; b[0] += 1; b[1] += r["acc"]; b[2] += int(bool(r["err"]))
    by_ds = defaultdict(list)
    for r in results:
        by_ds[r["dataset"]].append(r["acc"])

    report = {"approach": "type_router_#1", "n": n, "accuracy": round(acc, 4),
              "cost_per_1k_RA_pricing": round(cost_1k, 4), "arena_score": round(arena, 4),
              "errors": errs,
              "by_type": {t: {"n": v[0], "acc": round(v[1] / v[0], 3), "err": v[2]}
                          for t, v in by_type.items()}}
    (_HERE / "type_sub10_result.json").write_text(json.dumps(
        {"report": report, "by_dataset": {d: round(sum(v) / len(v), 3) for d, v in sorted(by_ds.items())},
         "results": results}, indent=2))
    print("\n=== TYPE ROUTER (#1) sub_10 (RA metrics + RA pricing) ===")
    print(json.dumps(report, indent=2))
    print("\nworst datasets:")
    for d, v in sorted(((d, sum(v) / len(v)) for d, v in by_ds.items()), key=lambda kv: kv[1])[:12]:
        print(f"  {v:.2f}  {d}")


if __name__ == "__main__":
    main()
