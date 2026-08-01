# SPDX-License-Identifier: MIT
"""Phase 0 — ORACLE GATE for the LLM-as-router experiment.

Question: with Claude (sonnet-5 / opus-4.8) added as tier-2 answerer, does the
3-model oracle {deepseek-v4-flash, deepseek-v3.2, claude} clear 0.78 on RA?
If the oracle can't reach ~0.78 there is NO POINT running an LLM router (a router
can never beat its own pool's oracle), and we must swap tier-2.

DIAGNOSTIC ONLY: the oracle is an upper-bound we report; it is NEVER fed back to
supervise routing (that would be the forbidden RA-derived supervision). Cheap/strong
per-query grades are REUSED from the calibrated run (sub10_perquery.json), so this
only pays for Claude answers. Stratified 150-query subset across RA datasets.

Run with the RA venv python.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sandbox/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import Grader, arena_score  # noqa: E402

SCRATCH = "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
EP = "https://openrouter.ai/api/v1/chat/completions"
HERE = os.path.dirname(os.path.abspath(__file__))

# tier-2 answerer candidates (router==answerer family per the chosen design)
SONNET = "anthropic/claude-sonnet-5"
OPUS = "anthropic/claude-opus-4.8"
PRICE = {SONNET: (2.0, 10.0), OPUS: (5.0, 25.0)}  # $/M in,out (OpenRouter)
N_SUB = 150
SEED = 20260707


def key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k and os.path.exists(f"{SCRATCH}/.orkey"):
        k = open(f"{SCRATCH}/.orkey").read().strip()
    return k


def call(model, prompt, k, mt=2000):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": mt, "temperature": 0}).encode()
    req = urllib.request.Request(EP, data=payload, headers={
        "Authorization": f"Bearer {k}", "Content-Type": "application/json"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read()); u = d.get("usage", {})
                return (d["choices"][0]["message"].get("content") or "",
                        u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        except Exception:
            time.sleep(3)
    return "", 0, 0


def cost(model, pt, ct):
    pin, pout = PRICE[model]
    return (pt * pin + ct * pout) / 1e6


def build_items():
    """Reproduce calibrated_router's EXACT item construction + order (sort by ds),
    so cached cheap/strong grades in sub10_perquery.json align positionally."""
    labels = json.load(open(f"{SCRATCH}/sub10_labels.json"))
    pby = {r["global index"]: r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
    items = [{"p": pby[r["gi"]], "ans": r["answer"], "ds": r["dataset"]}
             for r in labels if r["gi"] in pby]
    items.sort(key=lambda x: str(x["ds"]))
    return items


def stratified_subset(items, n, seed):
    """Proportional-by-dataset sample of n indices, seeded (spans RA's mix)."""
    by_ds = {}
    for i, it in enumerate(items):
        by_ds.setdefault(str(it["ds"]), []).append(i)
    rng = random.Random(seed)
    total = len(items)
    picked = []
    for ds, idxs in sorted(by_ds.items()):
        take = max(1, round(n * len(idxs) / total))
        rng.shuffle(idxs)
        picked.extend(idxs[:take])
    rng.shuffle(picked)
    return picked[:n]


def main():
    k = key()
    g = Grader()
    items = build_items()
    cache = json.load(open(f"{HERE}/sub10_perquery.json"))
    assert len(cache) == len(items), f"cache {len(cache)} != items {len(items)} — order drift!"

    sub = stratified_subset(items, N_SUB, SEED)
    dsc = {}
    for i in sub:
        dsc[str(items[i]["ds"])] = dsc.get(str(items[i]["ds"]), 0) + 1
    print(f"subset: {len(sub)} queries across {len(dsc)} datasets: {dsc}", flush=True)

    # Claude answers (sonnet + opus) on the subset — the only paid work
    def work(i):
        it = items[i]
        out = {"i": i}
        for tag, model in (("son", SONNET), ("opu", OPUS)):
            raw, pt, ct = call(model, it["p"], k)
            out[f"{tag}_ok"] = int(round(g.grade_one(raw, it["ans"], it["ds"])))
            out[f"{tag}_cost"] = cost(model, pt, ct)
        return out

    res = {}
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work, i) for i in sub]):
            d = f.result(); res[d["i"]] = d; done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(sub)} ({time.time()-t0:.0f}s)", flush=True)

    # assemble per-query rows: cheap/strong from cache + claude fresh
    rows = []
    for i in sub:
        c = cache[i]; r = res[i]
        rows.append({"c_ok": c["c_ok"], "s_ok": c["s_ok"],
                     "c_cost": c["c_cost"], "s_cost": c["s_cost"],
                     "son_ok": r["son_ok"], "son_cost": r["son_cost"],
                     "opu_ok": r["opu_ok"], "opu_cost": r["opu_cost"]})
    n = len(rows)

    def report(name, ok, cst):
        a = sum(ok) / n; c1 = sum(cst) / n * 1000
        return name, a, c1, arena_score(c1, a)

    def oracle(models):
        """cheapest-correct among the given (ok,cost) model keys; else cheapest attempt."""
        ok, cst = [], []
        for r in rows:
            best = None
            for okk, cok in models:
                if r[okk]:
                    cc = r[cok]
                    if best is None or cc < best[1]:
                        best = (1, cc)
            if best is None:  # none correct → cheapest attempt (cheap)
                best = (0, min(r[cok] for _, cok in models))
            ok.append(best[0]); cst.append(best[1])
        return ok, cst

    lines = []
    lines.append(report("always-cheap", [r["c_ok"] for r in rows], [r["c_cost"] for r in rows]))
    lines.append(report("always-strong", [r["s_ok"] for r in rows], [r["s_cost"] for r in rows]))
    lines.append(report("always-sonnet", [r["son_ok"] for r in rows], [r["son_cost"] for r in rows]))
    lines.append(report("always-opus", [r["opu_ok"] for r in rows], [r["opu_cost"] for r in rows]))

    o2 = oracle([("c_ok", "c_cost"), ("s_ok", "s_cost")])
    o3s = oracle([("c_ok", "c_cost"), ("s_ok", "s_cost"), ("son_ok", "son_cost")])
    o3o = oracle([("c_ok", "c_cost"), ("s_ok", "s_cost"), ("opu_ok", "opu_cost")])
    o4 = oracle([("c_ok", "c_cost"), ("s_ok", "s_cost"), ("son_ok", "son_cost"), ("opu_ok", "opu_cost")])
    lines.append(report("ORACLE {c,s}", *o2))
    lines.append(report("ORACLE {c,s,sonnet}", *o3s))
    lines.append(report("ORACLE {c,s,opus}", *o3o))
    lines.append(report("ORACLE {c,s,son,opu}", *o4))

    print("\n=== PHASE-0 ORACLE GATE (150-query stratified sub_10, RA metrics) ===")
    for name, a, c1, ar in lines:
        print(f"  {name:22s} acc={a:.3f}  ${c1:.3f}/1k  arena={ar:.4f}")

    best_oracle = max(l[3] for l in lines if l[0].startswith("ORACLE {c,s,"))
    gate = best_oracle >= 0.78
    print(f"\n  best 3-model oracle arena = {best_oracle:.4f}   GATE(>=0.78): {'PASS' if gate else 'FAIL'}")
    print("  (router can never beat this; PASS = 0.76 is reachable, proceed to Sonnet router)")

    json.dump({"subset": sub, "rows": rows,
               "reports": [{"policy": n_, "acc": a, "c1k": c1, "arena": ar} for n_, a, c1, ar in lines],
               "best_oracle": best_oracle, "gate_pass": gate,
               "sonnet": SONNET, "opus": OPUS},
              open(f"{HERE}/phase0_oracle.json", "w"), indent=2)
    print("\n  saved phase0_oracle.json")


if __name__ == "__main__":
    main()
