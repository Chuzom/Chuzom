# SPDX-License-Identifier: MIT
"""KG3 — Visual Bypass kill-gate: what fraction of RA sub_10 queries are VISUALIZABLE
(spatial / graph / geometry / structural)? If <15%, the VLM path is irrelevant.
No model calls — pure content parse."""
import json, re
from collections import Counter
SCRATCH="/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
labels=json.load(open(f"{SCRATCH}/sub10_labels.json"))
pby={r["global index"]:r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
items=[{"ds":r["dataset"],"p":pby[r["gi"]]} for r in labels if r["gi"] in pby]

SPATIAL=re.compile(r"\b(left of|right of|above|below|next to|adjacent|beside|between|north|south|east|west|top row|bottom row|grid|seating|sits? (?:to|next))\b",re.I)
GRAPH=re.compile(r"\b(node|edge|vertex|vertices|graph|connected to|connects? to|network|shortest path|adjacency|tree with)\b",re.I)
GEOM=re.compile(r"\b(triangle|rectangle|circle|polygon|coordinate|\bplot\b|perimeter|area of the|angle of|vertices of|geometry)\b",re.I)
STRUCT=re.compile(r"\b(arrange .* in order|seating arrangement|schedule|floor plan|map of|diagram)\b",re.I)

def vis(p):
    return bool(SPATIAL.search(p) or GRAPH.search(p) or GEOM.search(p) or STRUCT.search(p))

hits=[it for it in items if vis(it["p"])]
n=len(items); h=len(hits)
print(f"KG3 — visualizable RA queries: {h}/{n} = {h/n:.3f}   GATE(>=0.15): {'PASS' if h/n>=0.15 else 'FAIL'}")
by=Counter(it["ds"] for it in hits)
print("by dataset (top visualizable):")
for d,c in by.most_common(10): print(f"  {c:3d}  {d}")
print("\nsample matches:")
for it in hits[:4]: print(f"  [{it['ds']}] {it['p'][:90]}")
