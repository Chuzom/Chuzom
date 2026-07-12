# SPDX-License-Identifier: MIT
"""P1.3 — simulate the confidence-gated cascade from the label table (offline).

Because build_label_table.py already recorded every model's raw answer on every
proxy item, we can replay ANY cascade variant with ZERO new API calls and read
off its proxy arena score. This is the calibration surface for:
  • the live-signal escalation rule (agreement gate; extensible to entropy etc.)
  • the escalation TARGET (fixed strong vs capability-map axis-targeted)

Cost accounting mirrors RA: only the FINAL chosen model's tokens are charged
(the 2 cheap probes are production-only, disclosed). Cheap-ship reuses probe 0.

COMPLIANCE: everything here is measured on the self-generated proxy. No RA data.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # routerarena_clean/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # sandbox/
from router_core import extract_answer, answers_agree  # noqa: E402
from grader import arena_score                          # noqa: E402

CHEAP = ["qwen/qwen3-235b-a22b-2507", "deepseek/deepseek-v4-flash"]


def _sim(items, strong_selector, *, capability_map=None):
    """strong_selector(item) -> strong model name. Returns metrics dict."""
    n = len(items)
    correct = cost = escalated = 0
    for it in items:
        pm = it["per_model"]
        # prefer the stored extraction (from full raw); fall back for old tables
        exts = [pm[c].get("ext") or extract_answer(pm[c]["raw"]) for c in CHEAP if c in pm]
        unanimous, _, _ = answers_agree(exts)
        if unanimous:
            c0 = CHEAP[0]
            correct += pm[c0]["correct"]
            cost += pm[c0]["cost"]
        else:
            strong = strong_selector(it)
            correct += pm[strong]["correct"]
            cost += pm[strong]["cost"]
            escalated += 1
    acc = correct / n
    cost_1k = cost / n * 1000
    return {"accuracy": round(acc, 4), "cost_per_1k": round(cost_1k, 4),
            "escalation_rate": round(escalated / n, 3),
            "arena_score": round(arena_score(cost_1k, acc), 4)}


def run(label_table: dict, capability_map: dict | None = None) -> dict:
    items = label_table["items"]
    models = label_table["models"]
    strong_candidates = [m for m in models if m not in CHEAP]

    out = {"n": len(items), "fixed_target": {}, "map_targeted": None,
           "oracle_cheapish": None}

    # (a) fixed escalation target — one row per strong candidate
    for s in strong_candidates:
        out["fixed_target"][s] = _sim(items, lambda it, s=s: s)

    # (b) capability-map-targeted escalation: on disagreement route to the map's
    #     best-accuracy model for THIS item's axis (falls back to first strong).
    if capability_map:
        axes = capability_map["axes"]

        def map_select(it):
            dom = it["domain"]
            tgt = axes.get(dom, {}).get("best_accuracy_model")
            if tgt and tgt in it["per_model"] and tgt not in CHEAP:
                return tgt
            return strong_candidates[0]

        out["map_targeted"] = _sim(items, map_select)

    # (c) diagnostic oracle: cheapest model that is correct per item (upper edge)
    def oracle_cost_acc():
        n = len(items); correct = cost = 0
        for it in items:
            pm = it["per_model"]
            ok = [(pm[m]["cost"], m) for m in models if pm[m]["correct"]]
            if ok:
                correct += 1
                cost += min(ok)[0]
        acc = correct / n; c1k = cost / n * 1000
        return {"accuracy": round(acc, 4), "cost_per_1k": round(c1k, 4),
                "arena_score": round(arena_score(c1k, acc), 4)}
    out["oracle_cheapish"] = oracle_cost_acc()
    return out


if __name__ == "__main__":
    _HERE = Path(__file__).resolve().parent
    lt = json.loads((_HERE / "label_table.json").read_text())
    cmap = None
    for cand in ("capability_map.yaml", "capability_map.json"):
        p = _HERE / cand
        if p.exists():
            try:
                import yaml
                cmap = yaml.safe_load(p.read_text())
            except Exception:
                cmap = json.loads(p.read_text()) if cand.endswith(".json") else None
            break

    res = run(lt, cmap)
    print(f"proxy items: {res['n']}\n")
    print("=== fixed escalation target (cheap probes agree→ship; else→target) ===")
    for s, m in res["fixed_target"].items():
        print(f"  {s.split('/')[-1]:26s} acc={m['accuracy']:.3f} "
              f"${m['cost_per_1k']:.3f}/1k esc={m['escalation_rate']:.2f} "
              f"ARENA={m['arena_score']:.4f}")
    if res["map_targeted"]:
        m = res["map_targeted"]
        print(f"\n  {'MAP-TARGETED':26s} acc={m['accuracy']:.3f} "
              f"${m['cost_per_1k']:.3f}/1k esc={m['escalation_rate']:.2f} "
              f"ARENA={m['arena_score']:.4f}")
    o = res["oracle_cheapish"]
    print(f"\n  {'ORACLE(cheapest-correct)':26s} acc={o['accuracy']:.3f} "
          f"${o['cost_per_1k']:.3f}/1k  ARENA={o['arena_score']:.4f}  (upper edge)")
