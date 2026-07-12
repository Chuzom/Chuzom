# SPDX-License-Identifier: MIT
"""P1.2 — derive the capability map from the label table.

Aggregates per-model correctness by general AXIS (our proxy domains) and by
difficulty. The map's job is escalation-TARGET selection: for a query's axis,
which model is most accurate, and which is the cheapest that's "good enough".

COMPLIANCE: keyed to general axes measured on the SELF-GENERATED proxy — never
RA's 44 categories, never RA per-category outcomes (PR-155 rule #3).
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def build_map(label_table: dict, good_enough_frac: float = 0.97) -> dict:
    models = label_table["models"]
    items = label_table["items"]

    def acc_cost(subset, m):
        recs = [it["per_model"][m] for it in subset if m in it["per_model"]]
        return _mean(r["correct"] for r in recs), _mean(r["cost"] for r in recs) * 1000

    # overall
    overall = {}
    for m in models:
        a, c = acc_cost(items, m)
        overall[m] = {"accuracy": round(a, 4), "cost_per_1k": round(c, 4)}

    # by axis (domain)
    by_axis = defaultdict(dict)
    domains = sorted({it["domain"] for it in items})
    axes = {}
    for dom in domains:
        subset = [it for it in items if it["domain"] == dom]
        ranked = []
        for m in models:
            a, c = acc_cost(subset, m)
            ranked.append({"model": m, "accuracy": round(a, 4), "cost_per_1k": round(c, 4)})
        ranked.sort(key=lambda r: (-r["accuracy"], r["cost_per_1k"]))
        best_acc = ranked[0]["accuracy"]
        # cheapest model reaching good_enough_frac of best accuracy
        thresh = good_enough_frac * best_acc
        cheap_ok = sorted([r for r in ranked if r["accuracy"] >= thresh],
                          key=lambda r: r["cost_per_1k"])
        axes[dom] = {
            "n": len(subset),
            "best_accuracy_model": ranked[0]["model"],
            "best_accuracy": best_acc,
            "cost_efficient_target": cheap_ok[0]["model"] if cheap_ok else ranked[0]["model"],
            "ranked": ranked,
        }

    # by difficulty (diagnostic)
    by_diff = {}
    for diff in ("easy", "medium", "hard"):
        subset = [it for it in items if it["difficulty"] == diff]
        by_diff[diff] = {m: round(acc_cost(subset, m)[0], 4) for m in models}

    return {"overall": overall, "axes": axes, "by_difficulty": by_diff,
            "provenance": "self-generated proxy (proxy_gen), computed answers, "
                          "RA-independent; measured by build_label_table.py"}


def _dump_yaml(obj, path: Path):
    try:
        import yaml
        path.write_text(yaml.safe_dump(obj, sort_keys=False, default_flow_style=False))
        return str(path)
    except Exception:
        j = path.with_suffix(".json")
        j.write_text(json.dumps(obj, indent=2))
        return str(j)


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else _HERE / "label_table.json"
    lt = json.loads(src.read_text())
    cmap = build_map(lt)
    out = _dump_yaml(cmap, _HERE / "capability_map.yaml")

    print("=== overall (accuracy @ cost_per_1k) ===")
    for m, s in sorted(cmap["overall"].items(), key=lambda kv: -kv[1]["accuracy"]):
        print(f"  {s['accuracy']:.3f}  ${s['cost_per_1k']:.3f}/1k  {m}")
    print("\n=== by difficulty (accuracy) ===")
    for diff, per in cmap["by_difficulty"].items():
        row = "  ".join(f"{m.split('/')[-1][:14]}={a:.2f}" for m, a in per.items())
        print(f"  {diff:6s}: {row}")
    print("\n=== per-axis best / cost-efficient target ===")
    for dom, ax in cmap["axes"].items():
        print(f"  {dom:18s} best={ax['best_accuracy_model'].split('/')[-1]:22s} "
              f"({ax['best_accuracy']:.2f})  cheap_ok={ax['cost_efficient_target'].split('/')[-1]}")
    print(f"\nwrote {out}")
