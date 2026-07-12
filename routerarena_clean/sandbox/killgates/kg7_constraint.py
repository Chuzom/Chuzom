import json, re
from collections import Counter
SCRATCH="/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
labels=json.load(open(f"{SCRATCH}/sub10_labels.json"))
pby={r["global index"]:r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
items=[{"ds":r["dataset"],"p":pby[r["gi"]]} for r in labels if r["gi"] in pby]
C=[re.compile(p,re.I) for p in [
    r"\b\d+[- ]letter\b", r"\bmust (?:not )?(?:use|contain|include|sum|equal|be)\b",
    r"\bsums? to \d+\b", r"\bexactly \d+\b", r"\bwithout (?:using|repeating)\b",
    r"\bpalindrome\b", r"\banagram\b", r"\bdivisible by \d+\b", r"\bat (?:most|least) \d+\b",
    r"\bin (?:ascending|descending|alphabetical) order\b", r"\bconsecutive\b"]]
def has_constraint(p): return any(c.search(p) for c in C)
hits=[it for it in items if has_constraint(it["p"])]
n,h=len(items),len(hits)
print(f"=== KG7 RESULT ===")
print(f"  extractable-constraint coverage: {h}/{n} = {h/n:.3f}   GATE(>=0.20): {'PASS' if h/n>=0.20 else 'FAIL'}")
print("  by dataset:", dict(Counter(it['ds'] for it in hits).most_common(8)))
for it in hits[:3]: print(f"  [{it['ds']}] {it['p'][:90]}")
