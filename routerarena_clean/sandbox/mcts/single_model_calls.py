# SPDX-License-Identifier: MIT
"""Single-model sweep — CALLS stage (Chuzom .venv).

Runs each candidate model SOLO on the RA-150 subset through Chuzom, saves raw
answers + cost. No routing, no training — pure model selection (the cleanest
possible RA submission: a uniform single model has zero fitted components).
Grading happens in single_model_grade.py (RA venv).

Run: CHUZOM .venv python, OPENROUTER_API_KEY set.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chuzom.providers import call_llm  # noqa: E402

SCRATCH = "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
HERE = os.path.dirname(os.path.abspath(__file__))
WORKERS = int(os.environ.get("SM_WORKERS", "12"))
TIMEOUT = float(os.environ.get("SM_TIMEOUT", "90"))

CANDIDATES = {
    "gpt-5-mini": ("openrouter/openai/gpt-5-mini", (0.25, 2.0)),
    "glm-4.6": ("openrouter/z-ai/glm-4.6", (0.43, 1.74)),
    "qwen3-max": ("openrouter/qwen/qwen3-max", (0.78, 3.9)),
    "kimi-k2-thinking": ("openrouter/moonshotai/kimi-k2-thinking", (0.60, 2.5)),
    "gpt-5": ("openrouter/openai/gpt-5", (1.25, 10.0)),
}


def build_items():
    labels = json.load(open(f"{SCRATCH}/sub10_labels.json"))
    pby = {r["global index"]: r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
    items = [{"p": pby[r["gi"]], "ans": r["answer"], "ds": r["dataset"]}
             for r in labels if r["gi"] in pby]
    items.sort(key=lambda x: str(x["ds"]))
    return items


async def one(model, prompt):
    for _ in range(3):
        try:
            r = await asyncio.wait_for(
                call_llm(model, [{"role": "user", "content": prompt}], temperature=0, max_tokens=2000),
                timeout=TIMEOUT)
            if r.content:
                return r.content, float(r.cost_usd or 0.0), r.input_tokens, r.output_tokens
        except Exception:
            pass
        await asyncio.sleep(1.0)
    return "", 0.0, 0, 0


async def run_model(tag, model, subset, items):
    out = [None] * len(subset)
    t0, done = time.time(), [0]
    q = asyncio.Queue()
    for j in range(len(subset)):
        q.put_nowait(j)

    async def worker():
        while True:
            try:
                j = q.get_nowait()
            except asyncio.QueueEmpty:
                return
            raw, cost, it_, ot = await one(model, items[subset[j]]["p"])
            out[j] = {"raw": raw, "cost": cost, "in": it_, "out": ot}
            done[0] += 1
            if done[0] % 50 == 0:
                el = time.time() - t0
                print(f"    {tag} {done[0]}/{len(subset)} ({el:.0f}s)", flush=True)

    await asyncio.gather(*(worker() for _ in range(WORKERS)))
    return out


async def main():
    items = build_items()
    subset = json.load(open(f"{HERE}/phase0_oracle.json"))["subset"]
    only = os.environ.get("SM_ONLY")  # optional CSV to run a subset of candidates
    cands = {k: v for k, v in CANDIDATES.items() if (not only or k in only.split(","))}
    results = {}
    # resume: keep previously-saved models
    path = f"{HERE}/single_new_150.json"
    if os.path.exists(path):
        results = json.load(open(path)).get("results", {})
    for tag, (model, price) in cands.items():
        if tag in results:
            print(f"  {tag}: cached, skip", flush=True)
            continue
        print(f"  running {tag} ({model})...", flush=True)
        rows = await run_model(tag, model, subset, items)
        results[tag] = {"price": price, "rows": rows}
        json.dump({"subset": subset, "results": results}, open(path, "w"))
        print(f"  saved {tag}", flush=True)
    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
