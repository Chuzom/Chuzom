# SPDX-License-Identifier: MIT
"""KG2 — MCTS/trajectory kill-gate: does a cheap JUDGE's coherence score of the
cheap solver's reasoning predict correctness? Self-gen traps, own gold."""
import os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memorytree"))
from _kgutil import call, key, correct   # noqa
from traps_gen import generate            # noqa
SOLVER="deepseek/deepseek-v4-flash"; JUDGE="qwen/qwen3-235b-a22b-2507"; N=250
def judge_score(txt):
    m=re.search(r"\b(10|[0-9])\b", txt or "")
    return int(m.group(1)) if m else None
def main():
    k=key(); traps=generate(N)
    print(f"KG2: {len(traps)} traps | solver={SOLVER} judge={JUDGE}", flush=True)
    def work(t):
        sol=call(SOLVER,t["prompt"],k)
        ok=correct(sol,t["answer"])
        jp=(f"A student solved a problem. Rate ONLY the logical coherence and likely correctness "
            f"of their reasoning from 0 to 10 (10=clearly correct). Reply with ONLY the integer.\n\n"
            f"Problem: {t['prompt']}\n\nStudent's solution:\n{sol[:1500]}")
        coh=judge_score(call(JUDGE,jp,k,mt=10))
        return ok,coh
    rows=[]; done=0; t0=time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work,t) for t in traps]):
            rows.append(f.result()); done+=1
            if done%50==0: print(f"  {done}/{len(traps)} ({time.time()-t0:.0f}s)",flush=True)
    rows=[(ok,coh) for ok,coh in rows if coh is not None]
    fail=[1-ok for ok,_ in rows]; coh=[c for _,c in rows]
    fr=sum(fail)/len(fail)
    best=(-9,None)
    for thr in range(3,9):
        lo=[fail[i] for i in range(len(rows)) if coh[i]<thr]; hi=[fail[i] for i in range(len(rows)) if coh[i]>=thr]
        if lo and hi:
            sep=(sum(lo)/len(lo))-(sum(hi)/len(hi))
            if sep>best[0]: best=(sep,thr)
    print(f"\n=== KG2 RESULT ===\n  cheap fail rate: {fr:.3f}  (n={len(rows)})")
    print(f"  BEST SEPARATION = {best[0]:.3f} at coherence<{best[1]}  GATE(>=0.30): {'PASS' if best[0]>=0.30 else 'FAIL'}")
    print(f"  (agreement wall=0.01; MemoryTree in-dist=0.861, RA-transfer=0.024)")
if __name__=="__main__": main()
