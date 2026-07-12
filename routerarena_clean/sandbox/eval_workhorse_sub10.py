# SPDX-License-Identifier: MIT
"""Local RA sub_10 PREVIEW of the fixed workhorse router (always qwen3-235b).

The design is LOCKED before this runs: single model qwen/qwen3-235b-a22b-2507,
chosen from PUBLISHED benchmarks (MMLU-Pro ~84.8%), not from RA. This measures
that fixed design ONCE on RA's sub_10 subset to decide whether an official
/evaluate submission is worth it. No A/B of models on RA (that would be the
PR-140/155 violation); no design change after seeing this number.

Cost is scored with RA's OWN pricing (model_cost.json) so the arena estimate
matches how the server would score it. Accuracy uses RA's official metrics.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import Grader, arena_score  # noqa: E402

_HERE = Path(__file__).resolve().parent
SCRATCH = Path("/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/"
               "c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad")
EP = "https://openrouter.ai/api/v1/chat/completions"

MODEL = "qwen/qwen3-235b-a22b-2507"
# RA's own price for this model (model_cost.json entry "qwen/qwen3-235b-a22b-2507").
RA_PRICE_IN, RA_PRICE_OUT = 0.071, 0.10  # $/M tokens


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
            if e.code in (401, 403):
                return "", 0, 0, f"AUTH_{e.code}:{body}"
            time.sleep(2); last = f"HTTP_{e.code}"
        except Exception as e:
            time.sleep(2); last = str(e)
    return "", 0, 0, last


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="0 = all sub_10")
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
    print(f"WORKHORSE sub_10 preview: {MODEL} over {len(items)} RA prompts "
          f"(workers={args.workers})  [RA-DATA TOUCH — fixed design]", flush=True)

    def work(it):
        raw, pt, ct, err = call(MODEL, it["prompt"], key)
        acc = 0.0 if err else g.grade_one(raw, it["answer"], it["dataset"])
        cost = (pt * RA_PRICE_IN + ct * RA_PRICE_OUT) / 1e6
        return {"gi": it["gi"], "dataset": it["dataset"], "acc": acc,
                "correct": int(round(acc)), "cost": cost, "err": err}

    results, t0, done, auth = [], time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, it) for it in items]
        for f in as_completed(futs):
            r = f.result(); results.append(r)
            auth += int(bool(r["err"]) and r["err"].startswith("AUTH_"))
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(items)} ({time.time()-t0:.0f}s)", flush=True)
    if auth:
        print(f"⚠️  {auth} AUTH failures — key rotated/revoked.", flush=True)

    n = len(results)
    acc = sum(r["acc"] for r in results) / n
    cost_1k = sum(r["cost"] for r in results) / n * 1000
    arena = arena_score(cost_1k, acc)

    from collections import defaultdict
    by = defaultdict(list)
    for r in results:
        by[r["dataset"]].append(r["acc"])
    by_ds = {d: round(sum(v) / len(v), 3) for d, v in sorted(by.items())}

    report = {"model": MODEL, "n": n, "accuracy": round(acc, 4),
              "cost_per_1k_RA_pricing": round(cost_1k, 4),
              "arena_score": round(arena, 4),
              "errors": sum(int(bool(r["err"])) for r in results)}
    (_HERE / "workhorse_sub10_result.json").write_text(
        json.dumps({"report": report, "by_dataset": by_ds, "results": results}, indent=2))
    print("\n=== WORKHORSE sub_10 PREVIEW (RA metrics + RA pricing) ===")
    print(json.dumps(report, indent=2))
    print("\nworst datasets:")
    for d, a in sorted(by_ds.items(), key=lambda kv: kv[1])[:12]:
        print(f"  {a:.2f}  {d}")


if __name__ == "__main__":
    main()
