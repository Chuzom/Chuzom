# SPDX-License-Identifier: MIT
"""KG3 strict — require GENUINE relational/spatial/geometry structure, not keywords."""
import json, re
from collections import Counter
SCRATCH="/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
labels=json.load(open(f"{SCRATCH}/sub10_labels.json"))
pby={r["global index"]:r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
items=[{"ds":r["dataset"],"p":pby[r["gi"]]} for r in labels if r["gi"] in pby]
# genuine spatial relation between named entities, explicit graph edges, coordinate geometry
REL=re.compile(r"\b[A-Z]\w* is (?:to the (?:left|right)|directly (?:above|below)|next to|between)\b")
EDGE=re.compile(r"\bnode \w+ (?:is )?connect(?:s|ed)? to node \w+\b",re.I)
COORD=re.compile(r"\(\s*-?\d+\s*,\s*-?\d+\s*\)")           # coordinate pairs
GEOMQ=re.compile(r"\b(area|perimeter) of (?:the )?(triangle|rectangle|circle|square|polygon)\b",re.I)
SEAT=re.compile(r"\bsit(?:s|ting)? (?:to the (?:left|right)|next to|across from)\b",re.I)
def vis(p): return bool(REL.search(p) or EDGE.search(p) or (len(COORD.findall(p))>=2) or GEOMQ.search(p) or SEAT.search(p))
hits=[it for it in items if vis(it["p"])]
n,h=len(items),len(hits)
print(f"KG3 STRICT — genuinely visualizable: {h}/{n} = {h/n:.3f}   GATE(>=0.15): {'PASS' if h/n>=0.15 else 'FAIL'}")
print("by dataset:", dict(Counter(it["ds"] for it in hits).most_common(8)))
for it in hits[:3]: print(f"  [{it['ds']}] {it['p'][:100]}")
