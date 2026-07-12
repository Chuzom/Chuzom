# SPDX-License-Identifier: MIT
"""Shared RA sub_10 harness for mechanism approaches (#2 self-consistency, #4 hedge).

A mechanism provides `route_and_answer(query, call, key) -> dict` with keys
chosen_model, raw, cost, escalated, n_calls. This harness loads RA sub_10, runs
the mechanism per query, grades with RA's official metrics, and reports arena
using RA pricing. Exploratory measurement on a FIXED, principled design.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import Grader, arena_score  # noqa: E402

SCRATCH = Path("/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/"
               "c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad")
EP = "https://openrouter.ai/api/v1/chat/completions"

# RA pricing (model_cost.json) $/M (in,out), keyed by OpenRouter model id.
RA_PRICE = {
    "qwen/qwen3-235b-a22b-2507": (0.071, 0.10),
    "deepseek/deepseek-v4-flash": (0.14, 0.28),
    "deepseek/deepseek-v3.2": (0.28, 0.42),
    "qwen/qwen3-coder-30b-a3b-instruct": (0.07, 0.27),
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
    "deepseek/deepseek-r1": (0.28, 0.42),  # RA "deepseek-reasoner" price (reasoning tiebreak)
}


def key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k and (SCRATCH / ".orkey").exists():
        k = (SCRATCH / ".orkey").read_text().strip()
    if not k:
        raise RuntimeError("No OpenRouter key.")
    return k


def call(model, prompt, k, max_tokens=1500, temperature=0.0):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens, "temperature": temperature}).encode()
    req = urllib.request.Request(EP, data=payload, headers={
        "Authorization": f"Bearer {k}", "Content-Type": "application/json"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
                msg = d["choices"][0]["message"].get("content") or ""
                u = d.get("usage", {})
                return msg, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), None
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:120]
            if e.code in (400, 401, 403, 404):
                return "", 0, 0, f"HTTP_{e.code}:{body}"
            time.sleep(2); last = f"HTTP_{e.code}"
        except Exception as e:
            time.sleep(2); last = str(e)
    return "", 0, 0, last


def cost_of(model, pt, ct):
    pin, pout = RA_PRICE.get(model, (0.3, 0.5))
    return (pt * pin + ct * pout) / 1e6


import re  # noqa: E402


def robust_extract(raw: str) -> str:
    """Extraction that finds the answer even inside reasoning — does NOT strip
    <think> blocks (that dropped reasoning models' trailing \\boxed). Used for the
    self-consistency AGREEMENT signal (same model, so formats are consistent)."""
    if not raw:
        return ""
    boxed = re.findall(r"\\boxed\{([^{}]+)\}", raw)
    if boxed:
        return boxed[-1].strip().lower()
    m = re.search(r"(?:final answer|answer)\s*(?:is|:)?\s*([^\n.]+)", raw, re.I)
    if m:
        return m.group(1).strip().lower()
    nums = re.findall(r"-?\d[\d,]*\.?\d*", raw.replace(",", ""))
    if nums:
        return nums[-1].rstrip(".")
    lines = [ln for ln in raw.strip().splitlines() if ln.strip()]
    return re.sub(r"[^a-z0-9 ]", "", lines[-1].lower()).strip() if lines else ""


# Base/escalation for the mechanism approaches (#2, #4): cheap general base,
# stronger general escalation. Both justified by published general benchmarks;
# NOT chosen from RA outcomes.
MECH_BASE = "deepseek/deepseek-v4-flash"
MECH_STRONG = "deepseek/deepseek-v3.2"


def run(name, route_and_answer, n=0, workers=8, labels_file="sub10_labels.json"):
    k = key()
    g = Grader()
    labels = json.load(open(SCRATCH / labels_file))
    full = json.load(open(SCRATCH / "chuzom-v3-pred.json"))
    pby = {r["global index"]: r["prompt"] for r in full}
    items = [{"gi": r["gi"], "dataset": r["dataset"], "answer": r["answer"], "prompt": pby[r["gi"]]}
             for r in labels if r["gi"] in pby]
    items.sort(key=lambda x: str(x["gi"]))
    if n > 0:
        items = items[:n]
    print(f"{name} sub_10: {len(items)} RA prompts (workers={workers}) [RA-DATA TOUCH — fixed design]",
          flush=True)

    def work(it):
        res = route_and_answer(it["prompt"], call, k)
        acc = g.grade_one(res["raw"], it["answer"], it["dataset"])
        return {"gi": it["gi"], "dataset": it["dataset"], "chosen": res["chosen_model"],
                "escalated": res.get("escalated", False), "n_calls": res.get("n_calls", 1),
                "acc": acc, "cost": res["cost"]}

    results, t0, done = [], time.time(), 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(work, it) for it in items]
        for f in as_completed(futs):
            results.append(f.result()); done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(items)} ({time.time()-t0:.0f}s)", flush=True)

    nn = len(results)
    acc = sum(r["acc"] for r in results) / nn
    cost_1k = sum(r["cost"] for r in results) / nn * 1000
    esc = sum(r["escalated"] for r in results) / nn
    calls = sum(r["n_calls"] for r in results) / nn
    by_ds = defaultdict(list)
    for r in results:
        by_ds[r["dataset"]].append(r["acc"])
    report = {"approach": name, "n": nn, "accuracy": round(acc, 4),
              "cost_per_1k_RA_pricing": round(cost_1k, 4),
              "arena_score": round(arena_score(cost_1k, acc), 4),
              "escalation_rate": round(esc, 3), "calls_per_query": round(calls, 2)}
    Path(f"{name}_sub10_result.json").write_text(json.dumps(
        {"report": report, "by_dataset": {d: round(sum(v) / len(v), 3) for d, v in sorted(by_ds.items())},
         "results": results}, indent=2))
    print(f"\n=== {name} sub_10 (RA metrics + RA pricing) ===")
    print(json.dumps(report, indent=2))
    print("\nworst datasets:")
    for d, v in sorted(((d, sum(v) / len(v)) for d, v in by_ds.items()), key=lambda kv: kv[1])[:12]:
        print(f"  {v:.2f}  {d}")
    return report
