# SPDX-License-Identifier: MIT
"""Phase 3/4 — the DECISIVE cross-distribution test: does the self-gen MemoryTree
predict cheap-model failure on REAL RA sub_10 queries, and does routing on it beat
the baselines?

For every sub_10 query: run CHEAP + STRONG, grade with RA's official metrics, and
compute the failure-density + OOD-distance from the self-gen memory. Then score four
policies with RA pricing: always-cheap, always-strong, oracle, and MemoryTree-routed.

This is an INTERNAL evaluation (RA grader on the sub_10 preview) — no submission.
Run with the RA venv python.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sandbox/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # memorytree/
from grader import Grader, arena_score  # noqa: E402
from killgate import embed, key         # noqa: E402

SCRATCH = "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
EP = "https://openrouter.ai/api/v1/chat/completions"
CHEAP, STRONG = "deepseek/deepseek-v4-flash", "deepseek/deepseek-v3.2"
PRICE = {CHEAP: (0.14, 0.28), STRONG: (0.28, 0.42)}
HERE = os.path.dirname(os.path.abspath(__file__))
K = 5


def call(model, prompt, k, max_tokens=1500):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(EP, data=payload, headers={
        "Authorization": f"Bearer {k}", "Content-Type": "application/json"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read()); u = d.get("usage", {})
                return d["choices"][0]["message"].get("content") or "", u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
        except Exception:
            time.sleep(2)
    return "", 0, 0


def cost(model, pt, ct):
    pin, pout = PRICE[model]; return (pt * pin + ct * pout) / 1e6


def policy_metrics(name, chosen_correct, chosen_cost):
    n = len(chosen_correct)
    acc = sum(chosen_correct) / n
    c1k = sum(chosen_cost) / n * 1000
    return {"policy": name, "accuracy": round(acc, 4), "cost_per_1k": round(c1k, 4),
            "arena": round(arena_score(c1k, acc), 4)}


def main():
    import numpy as np
    from sklearn.neighbors import NearestNeighbors

    k = key()
    g = Grader()
    mem = np.load(f"{HERE}/memory.npz")
    mem_emb, mem_fail = mem["emb"].astype(np.float32), mem["fail"]
    print(f"memory: {mem_emb.shape} | fail-rate {mem_fail.mean():.3f}", flush=True)

    labels = json.load(open(f"{SCRATCH}/sub10_labels.json"))
    full = json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))
    pby = {r["global index"]: r["prompt"] for r in full}
    items = [{"gi": r["gi"], "dataset": r["dataset"], "answer": r["answer"], "prompt": pby[r["gi"]]}
             for r in labels if r["gi"] in pby]
    items.sort(key=lambda x: str(x["gi"]))
    print(f"sub_10 items: {len(items)} | running CHEAP+STRONG...", flush=True)

    def work(i):
        it = items[i]
        cr, cpt, cct = call(CHEAP, it["prompt"], k)
        sr, spt, sct = call(STRONG, it["prompt"], k)
        return i, {"c_ok": int(round(g.grade_one(cr, it["answer"], it["dataset"]))),
                   "c_cost": cost(CHEAP, cpt, cct),
                   "s_ok": int(round(g.grade_one(sr, it["answer"], it["dataset"]))),
                   "s_cost": cost(STRONG, spt, sct)}

    res = [None] * len(items)
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(work, i) for i in range(len(items))]
        for f in as_completed(futs):
            i, d = f.result(); res[i] = d; done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(items)} ({time.time()-t0:.0f}s)", flush=True)

    # embed queries + KNN into memory
    print("embedding sub_10 queries...", flush=True)
    Q, _ = embed([it["prompt"] for it in items]); Q = np.asarray(Q, dtype=np.float32)
    nn = NearestNeighbors(n_neighbors=K, metric="cosine").fit(mem_emb)
    dist, nbr = nn.kneighbors(Q)
    density = mem_fail[nbr].mean(axis=1)          # predicted cheap-failure density
    mean_dist = dist.mean(axis=1)                  # OOD signal (higher = less coverage)

    # OOD threshold calibrated on MEMORY's own internal neighbor distances (self-gen)
    dd, _ = NearestNeighbors(n_neighbors=K + 1, metric="cosine").fit(mem_emb).kneighbors(mem_emb)
    tau_ood = float(np.percentile(dd[:, 1:].mean(axis=1), 90))
    print(f"tau_ood (90th pct self-gen NN dist) = {tau_ood:.3f}", flush=True)

    c_ok = [r["c_ok"] for r in res]; s_ok = [r["s_ok"] for r in res]
    c_cost = [r["c_cost"] for r in res]; s_cost = [r["s_cost"] for r in res]

    # policies
    reports = []
    reports.append(policy_metrics("always-cheap", c_ok, c_cost))
    reports.append(policy_metrics("always-strong", s_ok, s_cost))
    # oracle: cheapest-correct
    orc_ok, orc_cost = [], []
    for i in range(len(items)):
        if c_ok[i]: orc_ok.append(1); orc_cost.append(c_cost[i])
        elif s_ok[i]: orc_ok.append(1); orc_cost.append(s_cost[i])
        else: orc_ok.append(0); orc_cost.append(c_cost[i])
    reports.append(policy_metrics("ORACLE", orc_ok, orc_cost))
    # MemoryTree: OOD -> strong; else density>0.5 -> strong; else cheap
    def route(i):
        if mean_dist[i] > tau_ood: return "s"
        return "s" if density[i] > 0.5 else "c"
    mt_ok, mt_cost, esc, ood = [], [], 0, 0
    for i in range(len(items)):
        r = route(i)
        if mean_dist[i] > tau_ood: ood += 1
        if r == "s": mt_ok.append(s_ok[i]); mt_cost.append(s_cost[i]); esc += 1
        else: mt_ok.append(c_ok[i]); mt_cost.append(c_cost[i])
    mt = policy_metrics("MemoryTree", mt_ok, mt_cost)
    mt["escalation_rate"] = round(esc / len(items), 3); mt["ood_rate"] = round(ood / len(items), 3)
    reports.append(mt)

    # density validity on RA: does predicted density correlate with cheap failure on RA?
    import numpy as _np
    cf = _np.array([1 - x for x in c_ok])
    hi = density > 0.5; lo = density <= 0.5
    ra_sep = (cf[hi].mean() if hi.any() else float('nan')) - (cf[lo].mean() if lo.any() else float('nan'))

    print("\n=== MEMORYTREE sub_10 (RA metrics + RA pricing) ===")
    for r in reports:
        print(f"  {r['policy']:14s} acc={r['accuracy']:.3f} ${r['cost_per_1k']:.3f}/1k arena={r['arena']:.4f}"
              + (f"  esc={r.get('escalation_rate')} ood={r.get('ood_rate')}" if 'escalation_rate' in r else ""))
    print(f"\n  RA cross-distribution SEPARATION (density→cheap-fail on real RA) = {ra_sep:.3f}")
    print(f"    (kill-gate in-distribution was 0.861; this is the number that matters for RA)")
    json.dump({"reports": reports, "ra_separation": float(ra_sep), "tau_ood": tau_ood,
               "cheap": CHEAP, "strong": STRONG},
              open(f"{HERE}/memorytree_sub10_result.json", "w"), indent=2)


if __name__ == "__main__":
    main()
