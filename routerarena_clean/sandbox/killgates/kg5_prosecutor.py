import os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memorytree"))
from _kgutil import call, key, correct   # noqa
from traps_gen import generate            # noqa
A="deepseek/deepseek-v4-flash"; B="deepseek/deepseek-v4-flash"; N=250
PROS=("You are a ruthless flaw-finder. You are given a PROBLEM and a proposed SOLUTION. "
      "Find any logical leap, arithmetic error, or ungrounded assumption. If the solution "
      "has a definite flaw, reply with EXACTLY the single word FLAW. If it is correct, reply "
      "with EXACTLY the single word OK. Reply with only one word.\n\nPROBLEM: {q}\n\nSOLUTION:\n{s}")
def main():
    k=key(); traps=generate(N); print(f"KG5: {len(traps)} traps",flush=True)
    def work(t):
        a=call(A,t["prompt"],k); ok=correct(a,t["answer"])
        b=call(B,PROS.format(q=t["prompt"],s=a[:1500]),k,mt=8)
        flag="FLAW" in (b or "").upper()[:12]
        return ok,flag
    rows=[];done=0;t0=time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work,t) for t in traps]):
            rows.append(f.result());done+=1
            if done%50==0: print(f"  {done}/{len(traps)} ({time.time()-t0:.0f}s)",flush=True)
    fail=[1-ok for ok,_ in rows]; flag=[fl for _,fl in rows]
    fr=sum(fail)/len(fail)
    lo=[fail[i] for i in range(len(rows)) if flag[i]]; hi=[fail[i] for i in range(len(rows)) if not flag[i]]
    sep=((sum(lo)/len(lo)) if lo else float('nan'))-((sum(hi)/len(hi)) if hi else float('nan'))
    fp=sum(1 for ok,fl in rows if ok and fl)/max(1,sum(1 for ok,_ in rows if ok))
    print(f"\n=== KG5 RESULT ===\n  cheap fail rate: {fr:.3f}")
    print(f"  SEPARATION (flag→fail) = {sep:.3f}  GATE(>=0.30): {'PASS' if sep>=0.30 else 'FAIL'}")
    print(f"  FALSE-POSITIVE rate (flag|correct) = {fp:.3f}  GATE(<=0.25): {'PASS' if fp<=0.25 else 'FAIL'}")
    print(f"  P(fail|flag)={sum(lo)/len(lo) if lo else float('nan'):.3f} (n={len(lo)}); P(fail|noflag)={sum(hi)/len(hi) if hi else float('nan'):.3f} (n={len(hi)})")
if __name__=="__main__": main()
