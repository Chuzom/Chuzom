# SPDX-License-Identifier: MIT
"""Single-model sweep — GRADE stage (RA venv).

Grades the raw answers from single_model_calls.py with the sha-pinned RA metrics,
computes single-model arena on RA-150, and ranks vs the cached incumbents.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import Grader, arena_score  # noqa: E402

SCRATCH = "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
HERE = os.path.dirname(os.path.abspath(__file__))


def build_items():
    labels = json.load(open(f"{SCRATCH}/sub10_labels.json"))
    pby = {r["global index"]: r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
    items = [{"p": pby[r["gi"]], "ans": r["answer"], "ds": r["dataset"]}
             for r in labels if r["gi"] in pby]
    items.sort(key=lambda x: str(x["ds"]))
    return items


def main():
    g = Grader()
    items = build_items()
    data = json.load(open(f"{HERE}/single_new_150.json"))
    subset, results = data["subset"], data["results"]
    n = len(subset)

    # cached incumbents on the same 150
    ph0 = json.load(open(f"{HERE}/phase0_oracle.json"))
    cn = json.load(open(f"{HERE}/council_killgate.json"))["res"]
    rows0 = ph0["rows"]
    ranked = {}

    def arena(ok, cost):
        a = sum(ok) / n; c1 = sum(cost) / n * 1000
        return a, c1, arena_score(c1, a)

    for name, ok_k, co_k in [("deepseek-v4-flash", "c_ok", "c_cost"), ("deepseek-v3.2", "s_ok", "s_cost"),
                             ("claude-sonnet-5", "son_ok", "son_cost"), ("claude-opus-4.8", "opu_ok", "opu_cost")]:
        ranked[name] = arena([rows0[j][ok_k] for j in range(n)], [rows0[j][co_k] for j in range(n)])
    for name, mid in [("qwen3-235b", "qwen/qwen3-235b-a22b-2507"), ("gemini-2.5-flash", "google/gemini-2.5-flash")]:
        ranked[name] = arena([cn[str(subset[j])][mid]["ok"] for j in range(n)],
                             [cn[str(subset[j])][mid]["cost"] for j in range(n)])

    # new candidates: grade raws
    fails = {}
    for tag, blob in results.items():
        rows = blob["rows"]
        ok, cost, nfail = [], [], 0
        for j in range(n):
            r = rows[j] or {"raw": "", "cost": 0.0}
            if not r["raw"]:
                nfail += 1
            ok.append(int(round(g.grade_one(r["raw"], items[subset[j]]["ans"], items[subset[j]]["ds"]))))
            cost.append(r["cost"])
        ranked[tag] = arena(ok, cost)
        fails[tag] = nfail

    print("=== SINGLE-MODEL arena on RA-150 (all through Chuzom) — ranked ===")
    print("  full-809 incumbent target: deepseek-v3.2 = 0.6951 | shipped 8400 = 0.7061 | target 0.76\n")
    for name, (a, c1, ar) in sorted(ranked.items(), key=lambda kv: -kv[1][2]):
        star = f"  [empty:{fails[name]}]" if name in fails and fails[name] else ""
        new = " (NEW)" if name in results else ""
        print(f"  {name:20s} acc={a:.3f}  ${c1:.3f}/1k  arena={ar:.4f}{new}{star}")
    json.dump({k: {"acc": v[0], "c1k": v[1], "arena": v[2]} for k, v in ranked.items()},
              open(f"{HERE}/single_model_sweep.json", "w"), indent=2)


if __name__ == "__main__":
    main()
