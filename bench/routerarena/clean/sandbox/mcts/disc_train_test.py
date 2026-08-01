# SPDX-License-Identifier: MIT
"""DISC.2 — train the discriminator on SYNTHETIC features, freeze, test on RA-150.

Train: gradient-boosting on synth_features.json (features -> cheap_fail). Report
in-dist AUC + feature importances. Threshold picked on a SYNTHETIC holdout
(Youden's J) — RA-independent. FREEZE, then on RA-150 (features from cache):
predict escalate; escalated -> sonnet (cached grades/cost), else cheap. Report
the transfer SEPARATION (analog to MemoryTree's 0.024) and the RA arena vs
coherence@8 (0.7464) and the 0.76 target. A RA-150 threshold sweep is printed for
transparency only (NOT used to pick — that would be RA tuning).

Run with the RA venv python.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sandbox/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import arena_score  # noqa: E402
from disc_features import build_features, FEATURE_NAMES  # noqa: E402

SCRATCH = "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
HERE = os.path.dirname(os.path.abspath(__file__))
CHEAP_ID = "deepseek/deepseek-v4-flash"
QWEN_ID = "qwen/qwen3-235b-a22b-2507"
MIST_ID = "mistralai/mistral-small-3.2-24b-instruct"


def build_items():
    labels = json.load(open(f"{SCRATCH}/sub10_labels.json"))
    pby = {r["global index"]: r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
    items = [{"p": pby[r["gi"]], "ans": r["answer"], "ds": r["dataset"]}
             for r in labels if r["gi"] in pby]
    items.sort(key=lambda x: str(x["ds"]))
    return items


def ra150_matrix():
    """Build the RA-150 feature matrix + escalation grades entirely from cache."""
    items = build_items()
    ph0 = json.load(open(f"{HERE}/phase0_oracle.json"))
    subset, rows = ph0["subset"], ph0["rows"]
    coh = json.load(open(f"{HERE}/sub10_perquery.json"))
    cn = json.load(open(f"{HERE}/council_killgate.json"))["res"]
    X, meta = [], []
    for j, i in enumerate(subset):
        r = cn[str(i)]
        ce = r[CHEAP_ID]["ext"]; qe = r[QWEN_ID]["ext"]; me = r[MIST_ID]["ext"]
        feats = build_features(coh[i]["coh"], ce, qe, me, items[i]["p"])
        X.append(feats)
        meta.append({"c_ok": rows[j]["c_ok"], "c_cost": rows[j]["c_cost"],
                     "son_ok": rows[j]["son_ok"], "son_cost": rows[j]["son_cost"],
                     "coherence": coh[i]["coh"]})
    return np.array(X, dtype=float), meta


def arena_of(ok, cost):
    n = len(ok); a = sum(ok) / n; c1 = sum(cost) / n * 1000
    return round(a, 4), round(c1, 4), round(arena_score(c1, a), 4)


def policy_escalate(meta, escalate):
    ok, cost = [], []
    for m, e in zip(meta, escalate):
        if e:
            ok.append(m["son_ok"]); cost.append(m["c_cost"] + m["son_cost"])  # pair cost: cheap ran too
        else:
            ok.append(m["c_ok"]); cost.append(m["c_cost"])
    return arena_of(ok, cost)


def main():
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score, roc_curve

    d = json.load(open(f"{HERE}/synth_features.json"))
    X = np.array(d["X"], dtype=float); y = np.array(d["y"], dtype=int)
    print(f"synthetic: {len(y)} rows, fail-rate {y.mean():.3f}, features {FEATURE_NAMES}", flush=True)

    Xtr, Xva, ytr, yva = train_test_split(X, y, test_size=0.25, random_state=7, stratify=y)
    clf = GradientBoostingClassifier(random_state=7, n_estimators=200, max_depth=3, learning_rate=0.05)
    clf.fit(Xtr, ytr)
    pva = clf.predict_proba(Xva)[:, 1]
    auc = roc_auc_score(yva, pva) if len(set(yva)) > 1 else float("nan")
    # Youden's J threshold on synthetic holdout (RA-independent operating point)
    fpr, tpr, thr = roc_curve(yva, pva)
    tau = float(thr[np.argmax(tpr - fpr)])
    print(f"  in-dist AUC={auc:.3f}  |  Youden tau (synthetic) = {tau:.3f}")
    imp = sorted(zip(FEATURE_NAMES, clf.feature_importances_), key=lambda t: -t[1])
    print("  feature importances: " + ", ".join(f"{n}={v:.2f}" for n, v in imp))

    # refit on ALL synthetic, freeze
    clf.fit(X, y)

    # ---- apply to RA-150 (frozen) ----
    Xr, meta = ra150_matrix()
    pr = clf.predict_proba(Xr)[:, 1]
    esc = pr > tau
    cfail = np.array([1 - m["c_ok"] for m in meta])
    hi, lo = esc, ~esc
    sep = (cfail[hi].mean() if hi.any() else float("nan")) - (cfail[lo].mean() if lo.any() else float("nan"))

    print(f"\n=== DISCRIMINATOR on RA-150 (frozen; tau from synthetic) ===")
    print(f"  escalation rate={esc.mean():.2%}  |  TRANSFER SEPARATION (pred-fail -> cheap-fail) = {sep:.3f}")
    print(f"    (MemoryTree transfer was 0.024; coherence single-feature ~0.66)")
    ac, cc, arc = arena_of([m["c_ok"] for m in meta], [m["c_cost"] for m in meta])
    print(f"  always-cheap        acc={ac:.3f} ${cc:.3f}/1k arena={arc:.4f}")
    a, c1, ar = policy_escalate(meta, esc)
    print(f"  DISC->sonnet        acc={a:.3f} ${c1:.3f}/1k arena={ar:.4f}   <<< (tau locked on synthetic)")

    # reference: coherence-only threshold (single feature) escalate->sonnet
    for t in (8,):
        e = np.array([m["coherence"] < t for m in meta])
        a2, c2, ar2 = policy_escalate(meta, e)
        print(f"  coherence<{t}->sonnet acc={a2:.3f} ${c2:.3f}/1k arena={ar2:.4f}  (single-feature baseline)")

    print(f"\n  bars: always-cheap=0.7260  coherence@8->strong=0.7464  target=0.76")
    print(f"  GATE(DISC arena >= 0.7464): {'PASS' if ar >= 0.7464 else 'FAIL'}  clears 0.76: {'YES' if ar >= 0.76 else 'no'}")

    # transparency: RA-150 tau sweep (NOT used to pick)
    print("\n  (transparency) RA-150 tau sweep — NOT used to select tau:")
    for q in (0.3, 0.4, 0.5, 0.6, 0.7):
        e = pr > q
        _, _, arq = policy_escalate(meta, e)
        print(f"    tau={q:.2f}: esc={e.mean():.2f} arena={arq:.4f}")

    json.dump({"in_dist_auc": auc, "tau": tau, "transfer_sep": float(sep),
               "disc_arena": ar, "importances": dict(imp)},
              open(f"{HERE}/disc_result.json", "w"), indent=2)
    print("\n  saved disc_result.json")


if __name__ == "__main__":
    main()
