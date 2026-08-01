# SPDX-License-Identifier: MIT
"""Agreement-gated escalation — the signal the council surfaced.

Two similar-strength CHEAP models (deepseek-v4-flash + qwen3-235b) answer every
query. If they AGREE on the extracted answer, trust it (measured ~84% precise).
If they DISAGREE, escalate that query to a stronger model. Agreement here is a
binary gate (no RA-tuned threshold); pair + target chosen a priori. Fully from
cached grades — free. This is the decisive 150 test before any full-809 run.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import arena_score  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
cn = json.load(open(f"{HERE}/council_killgate.json"))
ph0 = json.load(open(f"{HERE}/phase0_oracle.json"))
subset, rows = ph0["subset"], ph0["rows"]  # rows aligned to subset order
res = cn["res"]
DS = "deepseek/deepseek-v4-flash"
QW = "qwen/qwen3-235b-a22b-2507"
n = len(subset)

# per-position arrays (rows[j] aligns to subset[j])
qw_cost = [res[str(subset[j])][QW]["cost"] for j in range(n)]
ds_ext = [res[str(subset[j])][DS]["ext"] for j in range(n)]
qw_ext = [res[str(subset[j])][QW]["ext"] for j in range(n)]
ds_ok = [rows[j]["c_ok"] for j in range(n)]        # deepseek-v4-flash == "cheap"
ds_cost = [rows[j]["c_cost"] for j in range(n)]

agree = [bool(ds_ext[j]) and ds_ext[j] == qw_ext[j] for j in range(n)]
na = sum(agree)
p_agree_right = sum(ds_ok[j] for j in range(n) if agree[j]) / max(na, 1)
p_dis_right = sum(ds_ok[j] for j in range(n) if not agree[j]) / max(n - na, 1)
print(f"agree {na}/{n} ({na/n:.0%}) | P(correct|agree)={p_agree_right:.3f} "
      f"P(correct|disagree,cheap)={p_dis_right:.3f} sep={p_agree_right - p_dis_right:.3f}\n")

TARGETS = {"strong(dsv3.2)": ("s_ok", "s_cost"),
           "sonnet": ("son_ok", "son_cost"),
           "opus": ("opu_ok", "opu_cost")}


def policy(tok, tcost):
    ok, cost = [], []
    for j in range(n):
        pair_c = ds_cost[j] + qw_cost[j]          # both cheap models always run
        if agree[j]:
            ok.append(ds_ok[j]); cost.append(pair_c)
        else:
            ok.append(rows[j][tok]); cost.append(pair_c + rows[j][tcost])
    a = sum(ok) / n; c1 = sum(cost) / n * 1000
    return a, c1, arena_score(c1, a)


print("=== agreement-gated escalation (agree→trust pair; disagree→target) — 150 ===")
print(f"  {'always-cheap':22s} acc=0.733 arena=0.7260   coherence@8 arena=0.7464   target=0.76")
best = 0
for name, (tok, tcost) in TARGETS.items():
    a, c1, ar = policy(tok, tcost)
    best = max(best, ar)
    print(f"  disagree→{name:16s} acc={a:.3f}  ${c1:.3f}/1k  arena={ar:.4f}")
# also: escalate disagree to the 3-model ORACLE-best (diagnostic ceiling)
ok, cost = [], []
for j in range(n):
    pair_c = ds_cost[j] + qw_cost[j]
    if agree[j]:
        ok.append(ds_ok[j]); cost.append(pair_c)
    else:
        r = rows[j]
        cands = [(r["s_ok"], r["s_cost"]), (r["son_ok"], r["son_cost"]), (r["opu_ok"], r["opu_cost"])]
        win = [(1, c) for o, c in cands if o]
        if win:
            ok.append(1); cost.append(pair_c + min(c for _, c in win))
        else:
            ok.append(0); cost.append(pair_c + min(c for _, c in cands))
a = sum(ok) / n; c1 = sum(cost) / n * 1000
print(f"  disagree→{'ORACLE(diag)':16s} acc={a:.3f}  ${c1:.3f}/1k  arena={arena_score(c1, a):.4f}  (ceiling if we picked perfectly on disagree)")
print(f"\n  GATE(best >= 0.76): {'PASS' if best >= 0.76 else 'no'}  best real arena={best:.4f}")
