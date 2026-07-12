# SPDX-License-Identifier: MIT
"""LR.1+LR.2 — LLM-as-router harness + 150-subset evaluation.

An Anthropic model (sonnet-5 or opus-4.8) reads each query and picks the cheapest
model in the pool it thinks will answer correctly — a ZERO-SHOT router. The menu is
GENERIC (relative price + capability tier); it contains ZERO RA-derived content
(no per-dataset stats, no oracle hints, no dataset fingerprints). The prompt is
FROZEN below and is NOT tuned against sub_10 results (that would be RA tuning).

Answerer grades for all four models on the 150 subset are REUSED from
phase0_oracle.json, so this only pays for the router's own calls. We report the
arena RA would score (answering-model cost only) AND the router's true operating
cost (which RA does not count) so the economics are honest.

Usage:  <RA>/.venv/bin/python router_eval.py sonnet   # or: opus
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sandbox/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import arena_score  # noqa: E402

SCRATCH = "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
EP = "https://openrouter.ai/api/v1/chat/completions"
HERE = os.path.dirname(os.path.abspath(__file__))

ROUTER_MODELS = {"sonnet": "anthropic/claude-sonnet-5", "opus": "anthropic/claude-opus-4.8"}
ROUTER_PRICE = {"anthropic/claude-sonnet-5": (2.0, 10.0), "anthropic/claude-opus-4.8": (5.0, 25.0)}
# tier-2 answerer matches the router family (the chosen design)
TIER2_KEY = {"sonnet": ("son_ok", "son_cost"), "opus": ("opu_ok", "opu_cost")}
COH_TAU = 8  # coherence-judge threshold LOCKED from self-gen (calibrated_router), for reference only

# ── FROZEN router prompt — generic menu, no RA-derived content ────────────────
MENU = """You are a routing dispatcher. You are given a user query and three models you can send it to, listed cheapest to most expensive. Choose the CHEAPEST model that will answer THIS query correctly.

Models:
  A = a small, fast model (cheapest). Good for routine, short, or well-defined questions.
  B = a mid-tier reasoning model (~2x the cost of A). Good for multi-step reasoning and moderate difficulty.
  C = a frontier model (much more expensive). Reserve for genuinely hard, specialized, or high-precision questions where A and B would likely be wrong.

Judge the query's intrinsic difficulty, the domain expertise it needs, and how much careful reasoning it requires. Escalate only when a cheaper model would probably get it wrong; do not escalate easy questions.

Query:
\"\"\"{q}\"\"\"

Reply with ONLY a single letter: A, B, or C."""


def key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k and os.path.exists(f"{SCRATCH}/.orkey"):
        k = open(f"{SCRATCH}/.orkey").read().strip()
    return k


def call(model, prompt, k, mt=8):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": mt, "temperature": 0}).encode()
    req = urllib.request.Request(EP, data=payload, headers={
        "Authorization": f"Bearer {k}", "Content-Type": "application/json"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read()); u = d.get("usage", {})
                return (d["choices"][0]["message"].get("content") or "",
                        u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        except Exception:
            time.sleep(3)
    return "", 0, 0


def parse_choice(raw):
    m = re.search(r"\b([ABC])\b", (raw or "").upper())
    if m:
        return m.group(1)
    m = re.search(r"[ABC]", (raw or "").upper())
    return m.group(0) if m else "A"  # default cheapest on parse failure


def build_items():
    labels = json.load(open(f"{SCRATCH}/sub10_labels.json"))
    pby = {r["global index"]: r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
    items = [{"p": pby[r["gi"]], "ans": r["answer"], "ds": r["dataset"]}
             for r in labels if r["gi"] in pby]
    items.sort(key=lambda x: str(x["ds"]))
    return items


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "sonnet"
    router = ROUTER_MODELS[which]
    rpin, rpout = ROUTER_PRICE[router]
    t2_ok, t2_cost = TIER2_KEY[which]

    k = key()
    items = build_items()
    coh_cache = json.load(open(f"{HERE}/sub10_perquery.json"))
    ph0 = json.load(open(f"{HERE}/phase0_oracle.json"))
    subset, rows = ph0["subset"], ph0["rows"]  # rows aligned to subset order
    print(f"router={router}  pool={{cheap, strong, {which}}}  subset={len(subset)}", flush=True)

    # router decisions (the only paid work) — one call per query
    def work(j):
        i = subset[j]
        raw, pt, ct = call(router, MENU.format(q=items[i]["p"]), k)
        return j, parse_choice(raw), pt, ct

    choice = [None] * len(subset)
    rpt = rct = 0
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work, j) for j in range(len(subset))]):
            j, ch, pt, ct = f.result(); choice[j] = ch; rpt += pt; rct += ct; done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(subset)} ({time.time()-t0:.0f}s)", flush=True)

    n = len(subset)

    def rep(name, ok, cst):
        a = sum(ok) / n; c1 = sum(cst) / n * 1000
        return name, round(a, 4), round(c1, 4), round(arena_score(c1, a), 4)

    out = []
    out.append(rep("always-cheap", [r["c_ok"] for r in rows], [r["c_cost"] for r in rows]))
    out.append(rep("always-strong", [r["s_ok"] for r in rows], [r["s_cost"] for r in rows]))
    out.append(rep(f"always-{which}", [r[t2_ok] for r in rows], [r[t2_cost] for r in rows]))

    # coherence-judge @ locked tau=8 (cheap vs strong only), for reference
    coh_ok, coh_cost = [], []
    for j in range(n):
        cc = coh_cache[subset[j]]
        if cc["coh"] < COH_TAU:
            coh_ok.append(cc["s_ok"]); coh_cost.append(cc["s_cost"])
        else:
            coh_ok.append(cc["c_ok"]); coh_cost.append(cc["c_cost"])
    out.append(rep(f"coherence@{COH_TAU}", coh_ok, coh_cost))

    # THE LLM ROUTER
    MAP = {"A": ("c_ok", "c_cost"), "B": ("s_ok", "s_cost"), "C": (t2_ok, t2_cost)}
    r_ok, r_cost = [], []
    dist = {"A": 0, "B": 0, "C": 0}
    for j in range(n):
        ch = choice[j]; dist[ch] += 1
        okk, cok = MAP[ch]
        r_ok.append(rows[j][okk]); r_cost.append(rows[j][cok])
    out.append(rep(f"LLM-ROUTER({which})", r_ok, r_cost))

    # oracle over the 3-model pool
    orc_ok, orc_cost = [], []
    for j in range(n):
        r = rows[j]
        cands = [(r["c_ok"], r["c_cost"]), (r["s_ok"], r["s_cost"]), (r[t2_ok], r[t2_cost])]
        win = [(1, c) for ok, c in cands if ok]
        if win:
            orc_ok.append(1); orc_cost.append(min(c for _, c in win))
        else:
            orc_ok.append(0); orc_cost.append(min(c for _, c in cands))
    out.append(rep("ORACLE (3-model)", orc_ok, orc_cost))

    router_op_cost_1k = (rpt * rpin + rct * rpout) / 1e6 / n * 1000

    print(f"\n=== LLM-ROUTER ({which}) on 150 (RA metrics; answering cost only) ===")
    for name, a, c1, ar in out:
        star = "  <<<" if name.startswith("LLM-ROUTER") else ""
        print(f"  {name:20s} acc={a:.3f}  ${c1:.3f}/1k  arena={ar:.4f}{star}")
    print(f"\n  router choice distribution: A(cheap)={dist['A']} B(strong)={dist['B']} C({which})={dist['C']}")
    print(f"  router OPERATING cost (NOT in RA arena): ${router_op_cost_1k:.3f}/1k queries"
          f"  [tok in={rpt} out={rct}]")
    print(f"  reference bars: coherence-judge=0.7142(full809)  clean-submission=0.7061  target=0.76")

    json.dump({"which": which, "router": router, "reports":
               [{"policy": p, "acc": a, "c1k": c, "arena": ar} for p, a, c, ar in out],
               "choice_dist": dist, "router_op_cost_per_1k": router_op_cost_1k,
               "choices": choice, "subset": subset},
              open(f"{HERE}/router_eval_{which}.json", "w"), indent=2)
    print(f"\n  saved router_eval_{which}.json")


if __name__ == "__main__":
    main()
