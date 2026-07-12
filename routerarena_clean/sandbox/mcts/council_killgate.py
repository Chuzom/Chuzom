# SPDX-License-Identifier: MIT
"""COUNCIL kill-gate — a NEW lever: improve the ANSWER on the easy/medium bulk via
a cheap multi-model ensemble (Mixture-of-Agents / self-consistency), instead of
trying to DETECT cheap-model failure (which every router approach has failed at).

Core hypothesis: a council of diverse CHEAP models, majority-voted, beats a single
cheap model's accuracy on RA — because independent errors cancel under a vote. If
true, the base tier gets more accurate and arena rises (cost stays low, ~3x cheap).

COMPLIANCE: members chosen a priori by family diversity, NOT by RA accuracy. Pure
inference-time answering strategy, no RA supervision, no tuning. Grader sha-pinned.

Reports (150-subset, RA metrics): each single member, council-VOTE (realistic),
council-ORACLE (any-member-correct upper bound), all with real ensemble cost.
GATE: council-vote arena >= 0.7464 (beats the coherence judge) and ideally >= 0.76.

Run with the RA venv python.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sandbox/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import Grader, arena_score  # noqa: E402

SCRATCH = "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
EP = "https://openrouter.ai/api/v1/chat/completions"
HERE = os.path.dirname(os.path.abspath(__file__))

# 4 cheapest, maximally-diverse families (a priori — not RA-selected)
COUNCIL = [
    ("deepseek/deepseek-v4-flash", (0.09, 0.18)),
    ("qwen/qwen3-235b-a22b-2507", (0.09, 0.10)),
    ("meta-llama/llama-3.3-70b-instruct", (0.10, 0.32)),
    ("mistralai/mistral-small-3.2-24b-instruct", (0.07, 0.20)),
]
# optional 5th for extra diversity (pricier out) — reported as a variant
GEMINI = ("google/gemini-2.5-flash", (0.30, 2.50))


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
            with urllib.request.urlopen(req, timeout=150) as r:
                d = json.loads(r.read()); u = d.get("usage", {})
                return (d["choices"][0]["message"].get("content") or "",
                        u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        except Exception:
            time.sleep(3)
    return "", 0, 0


def price_of(pr, pt, ct):
    return (pt * pr[0] + ct * pr[1]) / 1e6


_BOX = re.compile(r"\\boxed\{([^{}]+)\}")
_FINAL = re.compile(r"(?:final answer|answer)\s*[:\-]?\s*\**([A-Za-z0-9][^\n.*]{0,60})", re.I)


def norm_ans(raw):
    """Generic short-answer normalizer for VOTE clustering (not grading)."""
    t = raw or ""
    m = _BOX.findall(t)
    if m:
        return m[-1].strip().lower().replace(" ", "")
    m = _FINAL.findall(t)
    if m:
        return m[-1].strip().lower().rstrip(".)").replace(" ", "")
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if lines:
        last = lines[-1]
        mc = re.match(r"^\(?([A-Ea-e])\)?[\).:\s]", last)
        if mc:
            return mc.group(1).lower()
        return last[:60].lower().replace(" ", "")
    return ""


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
    subset = json.load(open(f"{HERE}/phase0_oracle.json"))["subset"]
    members = COUNCIL + [GEMINI]
    print(f"council={[m for m,_ in COUNCIL]} (+gemini variant)  subset={len(subset)}", flush=True)

    def work(i):
        it = items[i]
        rec = {"i": i}
        for model, pr in members:
            raw, pt, ct = call(model, it["p"], k)
            rec[model] = {"ok": int(round(g.grade_one(raw, it["ans"], it["ds"]))),
                          "cost": price_of(pr, pt, ct), "ext": norm_ans(raw)}
        return rec

    res = {}
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work, i) for i in subset]):
            r = f.result(); res[r["i"]] = r; done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(subset)} ({time.time()-t0:.0f}s)", flush=True)

    n = len(subset)

    def arena_of(ok, cost):
        a = sum(ok) / n; c1 = sum(cost) / n * 1000
        return round(a, 4), round(c1, 4), round(arena_score(c1, a), 4)

    print(f"\n=== COUNCIL kill-gate ({n} queries, RA metrics) ===")
    # single members
    for model, _ in members:
        ok = [res[i][model]["ok"] for i in subset]; cost = [res[i][model]["cost"] for i in subset]
        a, c1, ar = arena_of(ok, cost)
        print(f"  single {model:42s} acc={a:.3f} ${c1:.3f}/1k arena={ar:.4f}")

    def council_report(mem, tag):
        anchor = mem[0][0]  # deepseek as tie-breaker
        vote_ok, vote_cost, orc_ok = [], [], []
        for i in subset:
            r = res[i]
            allcost = sum(r[m]["cost"] for m, _ in mem)
            # majority vote on normalized answers
            exts = [(m, r[m]["ext"]) for m, _ in mem if r[m]["ext"]]
            if exts:
                cnt = Counter(e for _, e in exts)
                top, ntop = cnt.most_common(1)[0]
                # pick a member holding the plurality answer; tie -> anchor if it holds top
                winners = [m for m, e in exts if e == top]
                win = anchor if anchor in winners else winners[0]
            else:
                win = anchor
            vote_ok.append(r[win]["ok"]); vote_cost.append(allcost)
            orc_ok.append(1 if any(r[m]["ok"] for m, _ in mem) else 0)
        a, c1, ar = arena_of(vote_ok, vote_cost)
        ao, co, aro = arena_of(orc_ok, vote_cost)
        print(f"\n  [{tag}] council-VOTE   acc={a:.3f} ${c1:.3f}/1k arena={ar:.4f}")
        print(f"  [{tag}] council-ORACLE acc={ao:.3f} ${co:.3f}/1k arena={aro:.4f}  (any-member-correct upper bound)")
        return {"tag": tag, "vote": [a, c1, ar], "oracle": [ao, co, aro]}

    r4 = council_report(COUNCIL, "4-cheap")
    r5 = council_report(members, "5-with-gemini")

    print(f"\n  bars: always-cheap=0.7260  coherence@8=0.7464  best-single≈0.733  target=0.76")
    best_vote = max(r4["vote"][2], r5["vote"][2])
    print(f"  GATE(council-vote arena >= 0.7464): {'PASS' if best_vote >= 0.7464 else 'FAIL'}"
          f"   clears 0.76: {'YES' if best_vote >= 0.76 else 'no'}   (best vote arena={best_vote:.4f})")

    json.dump({"subset": subset,
               "res": {str(i): res[i] for i in subset},
               "council4": r4, "council5": r5},
              open(f"{HERE}/council_killgate.json", "w"), indent=2)
    print("\n  saved council_killgate.json")


if __name__ == "__main__":
    main()
