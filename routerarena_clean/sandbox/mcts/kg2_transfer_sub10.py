# SPDX-License-Identifier: MIT
"""#2 MCTS/trajectory RA-transfer test: does the coherence-judge signal (0.388 on
self-gen) survive on REAL RA sub_10 queries, and does coherence-routing beat the
baselines? tau=3 is calibrated on SELF-GEN (KG2), never on RA. Internal eval only."""
import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sandbox/
from grader import Grader, arena_score  # noqa
SCRATCH="/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
EP="https://openrouter.ai/api/v1/chat/completions"
CHEAP,STRONG,JUDGE="deepseek/deepseek-v4-flash","deepseek/deepseek-v3.2","qwen/qwen3-235b-a22b-2507"
PRICE={CHEAP:(0.14,0.28),STRONG:(0.28,0.42),JUDGE:(0.071,0.10)}
TAU=3  # self-gen calibrated (KG2 best threshold), NOT tuned on RA
def key():
    k=os.environ.get("OPENROUTER_API_KEY","").strip()
    if not k and os.path.exists(f"{SCRATCH}/.orkey"): k=open(f"{SCRATCH}/.orkey").read().strip()
    return k
def call(model,prompt,k,mt=1500):
    p=json.dumps({"model":model,"messages":[{"role":"user","content":prompt}],"max_tokens":mt,"temperature":0}).encode()
    req=urllib.request.Request(EP,data=p,headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req,timeout=120) as r:
                d=json.loads(r.read()); u=d.get("usage",{})
                return d["choices"][0]["message"].get("content") or "", u.get("prompt_tokens",0), u.get("completion_tokens",0)
        except Exception: time.sleep(2)
    return "",0,0
def cost(m,pt,ct): pin,pout=PRICE[m]; return (pt*pin+ct*pout)/1e6
def jscore(txt):
    m=re.search(r"\b(10|[0-9])\b",txt or ""); return int(m.group(1)) if m else 5
def pol(name,ok,c): n=len(ok); a=sum(ok)/n; c1=sum(c)/n*1000; return {"policy":name,"acc":round(a,4),"c1k":round(c1,4),"arena":round(arena_score(c1,a),4)}
def main():
    k=key(); g=Grader()
    labels=json.load(open(f"{SCRATCH}/sub10_labels.json"))
    pby={r["global index"]:r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
    items=[{"gi":r["gi"],"ds":r["dataset"],"ans":r["answer"],"p":pby[r["gi"]]} for r in labels if r["gi"] in pby]
    items.sort(key=lambda x:str(x["gi"]))
    print(f"#2 MCTS RA-transfer: {len(items)} sub_10 | cheap+judge+strong",flush=True)
    def work(i):
        it=items[i]
        cr,cpt,cct=call(CHEAP,it["p"],k)
        c_ok=int(round(g.grade_one(cr,it["ans"],it["ds"])))
        jp=(f"A student solved a problem. Rate ONLY the logical coherence and likely correctness "
            f"of their reasoning from 0 to 10 (10=clearly correct). Reply with ONLY the integer.\n\n"
            f"Problem: {it['p']}\n\nStudent's solution:\n{cr[:1500]}")
        jr,jpt,jct=call(JUDGE,jp,k,mt=10); coh=jscore(jr)
        sr,spt,sct=call(STRONG,it["p"],k)
        s_ok=int(round(g.grade_one(sr,it["ans"],it["ds"])))
        return i,{"c_ok":c_ok,"c_cost":cost(CHEAP,cpt,cct),"coh":coh,
                  "s_ok":s_ok,"s_cost":cost(STRONG,spt,sct),"j_cost":cost(JUDGE,jpt,jct)}
    res=[None]*len(items); done=0; t0=time.time()
    with ThreadPoolExecutor(max_workers=10) as pool:
        for f in as_completed([pool.submit(work,i) for i in range(len(items))]):
            i,d=f.result(); res[i]=d; done+=1
            if done%100==0: print(f"  {done}/{len(items)} ({time.time()-t0:.0f}s)",flush=True)
    c_ok=[r["c_ok"] for r in res]; s_ok=[r["s_ok"] for r in res]; coh=[r["coh"] for r in res]
    c_cost=[r["c_cost"] for r in res]; s_cost=[r["s_cost"] for r in res]; j_cost=sum(r["j_cost"] for r in res)
    reps=[pol("always-cheap",c_ok,c_cost),pol("always-strong",s_ok,s_cost)]
    orc_ok=[1 if c_ok[i] or s_ok[i] else 0 for i in range(len(res))]
    orc_c=[c_cost[i] if c_ok[i] else (s_cost[i] if s_ok[i] else c_cost[i]) for i in range(len(res))]
    reps.append(pol("ORACLE",orc_ok,orc_c))
    # MCTS route: coherence<TAU -> strong, else cheap
    mt_ok=[s_ok[i] if coh[i]<TAU else c_ok[i] for i in range(len(res))]
    mt_c=[s_cost[i] if coh[i]<TAU else c_cost[i] for i in range(len(res))]
    m=pol("MCTS-coh",mt_ok,mt_c); esc=sum(1 for i in range(len(res)) if coh[i]<TAU)
    m["esc_rate"]=round(esc/len(res),3); reps.append(m)
    # RA separation: does coherence<TAU predict cheap failure on real RA?
    cf=[1-x for x in c_ok]
    lo=[cf[i] for i in range(len(res)) if coh[i]<TAU]; hi=[cf[i] for i in range(len(res)) if coh[i]>=TAU]
    sep=((sum(lo)/len(lo)) if lo else float('nan'))-((sum(hi)/len(hi)) if hi else float('nan'))
    print("\n=== #2 MCTS RA-transfer (RA metrics + RA pricing) ===")
    for r in reps: print(f"  {r['policy']:14s} acc={r['acc']:.3f} ${r['c1k']:.3f}/1k arena={r['arena']:.4f}"+(f" esc={r['esc_rate']}" if 'esc_rate' in r else ""))
    print(f"\n  RA SEPARATION (coherence<{TAU} → cheap-fail) = {sep:.3f}   (self-gen KG2 was 0.388; agreement wall 0.01)")
    print(f"    P(cheap fail | coh<{TAU})={sum(lo)/len(lo) if lo else float('nan'):.3f} (n={len(lo)}); P(fail|coh>={TAU})={sum(hi)/len(hi) if hi else float('nan'):.3f} (n={len(hi)})")
    print(f"  judge probe cost (disclosed, not scored) = ${j_cost/len(res)*1000:.4f}/1k")
    json.dump({"reports":reps,"ra_separation":float(sep),"tau":TAU},open(f"{os.path.dirname(__file__)}/kg2_transfer_result.json","w"),indent=2)
if __name__=="__main__": main()
