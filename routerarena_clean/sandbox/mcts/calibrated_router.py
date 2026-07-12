# SPDX-License-Identifier: MIT
"""Calibrated coherence-judge router (#2). Threshold tau is calibrated on SELF-GEN
(arena-optimal), then LOCKED and applied to sub_10. RA is only measured. Persists
per-query data so re-thresholding is free."""
import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sandbox/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memorytree"))
from grader import Grader, arena_score  # noqa
from traps_gen import generate           # noqa
SCRATCH="/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
EP="https://openrouter.ai/api/v1/chat/completions"
CHEAP,STRONG,JUDGE="deepseek/deepseek-v4-flash","deepseek/deepseek-v3.2","qwen/qwen3-235b-a22b-2507"
PRICE={CHEAP:(0.14,0.28),STRONG:(0.28,0.42)}
HERE=os.path.dirname(os.path.abspath(__file__))
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
                d=json.loads(r.read());u=d.get("usage",{})
                return d["choices"][0]["message"].get("content") or "",u.get("prompt_tokens",0),u.get("completion_tokens",0)
        except Exception: time.sleep(2)
    return "",0,0
def cost(m,pt,ct): pin,pout=PRICE[m]; return (pt*pin+ct*pout)/1e6
def jscore(t): m=re.search(r"\b(10|[0-9])\b",t or ""); return int(m.group(1)) if m else 5
_BOX=re.compile(r"\\boxed\{([^{}]+)\}")
def simple_ok(raw,gold):
    ms=_BOX.findall(raw or ""); c=ms[-1].strip().lower() if ms else ""
    if not c:
        nums=re.findall(r"-?\d[\d,]*\.?\d*",(raw or "").replace(",","")); c=nums[-1] if nums else ""
    g=str(gold).strip().lower()
    if c.replace(",","")==g: return 1
    try: return int(abs(float(c)-float(g))<1e-6)
    except: return 0
JP=("A student solved a problem. Rate ONLY the logical coherence and likely correctness of their "
    "reasoning from 0 to 10 (10=clearly correct). Reply with ONLY the integer.\n\nProblem: {q}\n\nStudent's solution:\n{s}")
def run_set(items, k, grade_fn, workers=10, tag=""):
    def work(i):
        it=items[i]; cr,cpt,cct=call(CHEAP,it["p"],k); c_ok=grade_fn(cr,it)
        coh=jscore(call(JUDGE,JP.format(q=it["p"],s=cr[:1500]),k,mt=10)[0])
        sr,spt,sct=call(STRONG,it["p"],k); s_ok=grade_fn(sr,it)
        return i,{"c_ok":c_ok,"s_ok":s_ok,"coh":coh,"c_cost":cost(CHEAP,cpt,cct),"s_cost":cost(STRONG,spt,sct)}
    res=[None]*len(items); done=0; t0=time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for f in as_completed([pool.submit(work,i) for i in range(len(items))]):
            i,d=f.result(); res[i]=d; done+=1
            if done%100==0: print(f"  {tag} {done}/{len(items)} ({time.time()-t0:.0f}s)",flush=True)
    return res
def arena_of(rows, tau):
    ok=[r["s_ok"] if r["coh"]<tau else r["c_ok"] for r in rows]
    c=[r["s_cost"] if r["coh"]<tau else r["c_cost"] for r in rows]
    a=sum(ok)/len(ok); c1=sum(c)/len(c)*1000; return arena_score(c1,a),a,c1,sum(1 for r in rows if r["coh"]<tau)/len(rows)
def main():
    k=key(); g=Grader()
    # Phase A: self-gen calibration
    traps=generate(300); sg=[{"p":t["prompt"],"ans":t["answer"]} for t in traps]
    print(f"Phase A: self-gen calibration ({len(sg)})",flush=True)
    sgr=run_set(sg,k,lambda raw,it:simple_ok(raw,it["ans"]),tag="A")
    json.dump(sgr,open(f"{HERE}/selfgen_perquery.json","w"))
    best=(-1,None)
    for tau in range(1,11):
        ar,_,_,_=arena_of(sgr,tau)
        if ar>best[0]: best=(ar,tau)
    tau_star=best[1]
    print(f"  self-gen arena-optimal tau* = {tau_star} (self-gen arena {best[0]:.4f})",flush=True)
    # Phase B: sub_10 eval with LOCKED tau*
    labels=json.load(open(f"{SCRATCH}/sub10_labels.json"))
    pby={r["global index"]:r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
    items=[{"p":pby[r["gi"]],"ans":r["answer"],"ds":r["dataset"]} for r in labels if r["gi"] in pby]
    items.sort(key=lambda x:str(x["ds"]))
    print(f"Phase B: sub_10 eval ({len(items)}), locked tau*={tau_star}",flush=True)
    sbr=run_set(items,k,lambda raw,it:int(round(g.grade_one(raw,it["ans"],it["ds"]))),tag="B")
    json.dump(sbr,open(f"{HERE}/sub10_perquery.json","w"))
    n=len(sbr)
    ac=sum(r["c_ok"] for r in sbr)/n; cc=sum(r["c_cost"] for r in sbr)/n*1000
    as_=sum(r["s_ok"] for r in sbr)/n; sc=sum(r["s_cost"] for r in sbr)/n*1000
    orc=sum(1 for r in sbr if r["c_ok"] or r["s_ok"])/n
    oc=sum((r["c_cost"] if r["c_ok"] else (r["s_cost"] if r["s_ok"] else r["c_cost"])) for r in sbr)/n*1000
    cal_ar,cal_a,cal_c,cal_esc=arena_of(sbr,tau_star)
    print("\n=== CALIBRATED #2 ROUTER (sub_10, RA metrics+pricing) ===")
    print(f"  always-cheap   acc={ac:.3f} ${cc:.3f}/1k arena={arena_score(cc,ac):.4f}")
    print(f"  always-strong  acc={as_:.3f} ${sc:.3f}/1k arena={arena_score(sc,as_):.4f}")
    print(f"  ORACLE         acc={orc:.3f} ${oc:.3f}/1k arena={arena_score(oc,orc):.4f}")
    print(f"  CALIBRATED-#2  acc={cal_a:.3f} ${cal_c:.3f}/1k arena={cal_ar:.4f}  tau*={tau_star} esc={cal_esc:.3f}")
    print("\n  (transparency) full tau-sweep on sub_10 — tau IS LOCKED from self-gen, this is not used to pick:")
    for tau in range(1,11):
        ar,a,c1,e=arena_of(sbr,tau); mark=" <- locked tau*" if tau==tau_star else ""
        print(f"    tau={tau:2d}: arena={ar:.4f} acc={a:.3f} esc={e:.2f}{mark}")
if __name__=="__main__": main()
