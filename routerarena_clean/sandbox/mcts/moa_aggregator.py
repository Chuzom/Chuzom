# SPDX-License-Identifier: MIT
"""Mixture-of-Agents aggregator — the strongest form of the council idea.

A judge model reads the question + all 4 cheap council candidate answers and
produces the final answer. Ceiling = council-ORACLE(4) = 0.7726 (clears 0.76).
Question: can the aggregator harvest it? Candidates are cached (their normalized
answers), so this costs only 150 aggregator calls. Compliant: a-priori aggregator,
no RA supervision. Reference: council-vote 0.7204, pair-agree ceiling 0.7528.

Run with the RA venv python.
"""
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import Grader, arena_score  # noqa: E402

SCRATCH = "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
EP = "https://openrouter.ai/api/v1/chat/completions"
HERE = os.path.dirname(os.path.abspath(__file__))
AGG = "deepseek/deepseek-v3.2"          # cheap, capable aggregator (a priori)
AGG_PRICE = (0.28, 0.42)
COUNCIL = ["deepseek/deepseek-v4-flash", "qwen/qwen3-235b-a22b-2507",
           "meta-llama/llama-3.3-70b-instruct", "mistralai/mistral-small-3.2-24b-instruct"]

AGG_PROMPT = """You are given a question and several candidate final answers proposed by different assistants. They may disagree. Decide the single correct answer.

Question:
{q}

Candidate answers:
{cands}

Think briefly if needed, then give ONLY the correct final answer, in the exact format the question asks for."""


def key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k and os.path.exists(f"{SCRATCH}/.orkey"):
        k = open(f"{SCRATCH}/.orkey").read().strip()
    return k


def call(model, prompt, k, mt=1200):
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


def build_items():
    labels = json.load(open(f"{SCRATCH}/sub10_labels.json"))
    pby = {r["global index"]: r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
    items = [{"p": pby[r["gi"]], "ans": r["answer"], "ds": r["dataset"]}
             for r in labels if r["gi"] in pby]
    items.sort(key=lambda x: str(x["ds"]))
    return items


def main():
    k = key()
    g = Grader()
    items = build_items()
    cn = json.load(open(f"{HERE}/council_killgate.json"))
    res, subset = cn["res"], cn["subset"]
    n = len(subset)
    council_cost = [sum(res[str(i)][m]["cost"] for m in COUNCIL) for i in subset]

    def work(pos):
        i = subset[pos]
        cands = "\n".join(f"- {res[str(i)][m]['ext'] or '(no answer)'}" for m in COUNCIL)
        raw, pt, ct = call(AGG, AGG_PROMPT.format(q=items[i]["p"], cands=cands), k)
        ok = int(round(g.grade_one(raw, items[i]["ans"], items[i]["ds"])))
        acost = (pt * AGG_PRICE[0] + ct * AGG_PRICE[1]) / 1e6
        return pos, ok, acost

    ok = [0] * n; acost = [0.0] * n
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work, p) for p in range(n)]):
            pos, o, ac = f.result(); ok[pos] = o; acost[pos] = ac; done += 1
            if done % 25 == 0:
                print(f"  {done}/{n} ({time.time()-t0:.0f}s)", flush=True)

    total_cost = [council_cost[j] + acost[j] for j in range(n)]
    a = sum(ok) / n; c1 = sum(total_cost) / n * 1000
    ar = arena_score(c1, a)
    print(f"\n=== MoA AGGREGATOR ({AGG}) on {n} ===")
    print(f"  MoA-aggregator   acc={a:.3f}  ${c1:.3f}/1k  arena={ar:.4f}")
    print(f"  refs: council-vote=0.7204  pair-agree ceiling=0.7528  council-ORACLE(4)=0.7726  coherence@8=0.7464")
    print(f"  bars: always-cheap=0.7260  target=0.76")
    print(f"  GATE(>=0.76): {'PASS' if ar >= 0.76 else 'FAIL'}  (vs council-oracle ceiling 0.7726)")
    json.dump({"acc": a, "c1k": c1, "arena": ar, "aggregator": AGG},
              open(f"{HERE}/moa_aggregator.json", "w"), indent=2)


if __name__ == "__main__":
    main()
