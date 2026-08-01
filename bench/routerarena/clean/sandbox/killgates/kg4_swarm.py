# SPDX-License-Identifier: MIT
"""KG4 — Hallucination-Shield kill-gate: does swarm agreement predict correctness
of the consensus? Self-gen traps, own gold."""
import os, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memorytree"))
from _kgutil import call, key, extract, correct   # noqa
from traps_gen import generate                      # noqa
SWARM=["qwen/qwen3-235b-a22b-2507","deepseek/deepseek-v4-flash",
       "meta-llama/llama-3.3-70b-instruct","google/gemini-2.5-flash-lite",
       "qwen/qwen3-coder-30b-a3b-instruct"]; N=200
def main():
    k=key(); traps=generate(N)
    print(f"KG4: {len(traps)} traps | swarm={len(SWARM)} models", flush=True)
    def work(t):
        ans=[]
        for m in SWARM:
            e=extract(call(m,t["prompt"],k))
            if e: ans.append(e)
        if not ans: return None
        top,cnt=Counter(ans).most_common(1)[0]
        agree=cnt/len(ans)
        cons_ok=correct(f"\\boxed{{{top}}}", t["answer"])
        return agree, cons_ok
    rows=[]; done=0; t0=time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        for f in as_completed([pool.submit(work,t) for t in traps]):
            r=f.result()
            if r: rows.append(r)
            done+=1
            if done%40==0: print(f"  {done}/{len(traps)} ({time.time()-t0:.0f}s)",flush=True)
    fail=[1-ok for _,ok in rows]; agree=[a for a,_ in rows]
    fr=sum(fail)/len(fail)
    lo=[fail[i] for i in range(len(rows)) if agree[i]<0.8]; hi=[fail[i] for i in range(len(rows)) if agree[i]>=0.8]
    sep=((sum(lo)/len(lo)) if lo else float('nan'))-((sum(hi)/len(hi)) if hi else float('nan'))
    print(f"\n=== KG4 RESULT ===\n  consensus fail rate: {fr:.3f}  (n={len(rows)})")
    print(f"  P(consensus wrong | agree<0.8) = {sum(lo)/len(lo) if lo else float('nan'):.3f}  (n={len(lo)})")
    print(f"  P(consensus wrong | agree>=0.8)= {sum(hi)/len(hi) if hi else float('nan'):.3f}  (n={len(hi)})")
    print(f"  SEPARATION = {sep:.3f}  GATE(>=0.30): {'PASS' if sep>=0.30 else 'FAIL'}")
    print(f"  (prior: diverse-vote plateaued 0.7155; agreement wall=0.01)")
if __name__=="__main__": main()
