import json, os, re, sys, subprocess, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sandbox/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import Grader   # noqa
from _kgutil import call, key   # noqa
SCRATCH="/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
CHEAP="deepseek/deepseek-v4-flash"; N=300
FORCE=("Solve the following by writing a COMPLETE Python program that COMPUTES and prints ONLY the "
       "final answer on the last line. Do not hardcode the answer as a literal — actually compute it. "
       "Output ONLY one ```python code block.\n\nQuestion: {q}")
_CODE=re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)
def extract_code(t):
    m=_CODE.findall(t or ""); return (m[-1].strip() if m else "")
def is_trivial(code):
    # trivial = essentially print of a literal, no real computation
    body=re.sub(r"#.*","",code)
    has_compute=bool(re.search(r"[-+*/%]|for |while |def |import |\.sort|range\(|sum\(|len\(|map\(|\[.*for", body))
    return not has_compute
def run(code):
    try:
        p=subprocess.run(["python3","-c",code],capture_output=True,text=True,timeout=5)
        out=(p.stdout or "").strip().splitlines()
        return (out[-1].strip() if out else ""), p.returncode==0
    except Exception:
        return "", False
def main():
    k=key(); g=Grader()
    labels=json.load(open(f"{SCRATCH}/sub10_labels.json"))
    pby={r["global index"]:r["prompt"] for r in json.load(open(f"{SCRATCH}/chuzom-v3-pred.json"))}
    items=[{"ds":r["dataset"],"ans":r["answer"],"p":pby[r["gi"]]} for r in labels if r["gi"] in pby]
    items.sort(key=lambda x:str(x["ds"])); items=items[:N]
    print(f"KG6: {len(items)} sub_10 | code-as-reasoning",flush=True)
    def gen(it):
        resp,_,_=call(CHEAP,FORCE.format(q=it["p"]),k,mt=1200) if False else (call(CHEAP,FORCE.format(q=it["p"]),k) ,0,0)
        return it, resp
    # fetch (network) parallel, execute serial
    fetched=[]; done=0; t0=time.time()
    def fetch(it): return it, call(CHEAP, FORCE.format(q=it["p"]), k)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(fetch,it) for it in items]):
            fetched.append(f.result()); done+=1
            if done%75==0: print(f"  fetched {done}/{len(items)} ({time.time()-t0:.0f}s)",flush=True)
    cov=0; runnable=0; code_ok=0; run_ok_slice=[]
    for it,resp in fetched:
        code=extract_code(resp)
        triv=is_trivial(code) if code else True
        out,ran=run(code) if code and not triv else ("",False)
        nontrivial_runnable = (code!="" and not triv and ran)
        if not triv and code: cov+=1
        if nontrivial_runnable:
            runnable+=1
            ok=int(round(g.grade_one(out, it["ans"], it["ds"])))
            code_ok+=ok; run_ok_slice.append(ok)
    n=len(fetched)
    coverage=cov/n
    acc_on_runnable=(code_ok/runnable) if runnable else float('nan')
    print(f"\n=== KG6 RESULT ===")
    print(f"  non-trivial code coverage: {cov}/{n} = {coverage:.3f}   GATE(>=0.25): {'PASS' if coverage>=0.25 else 'FAIL'}")
    print(f"  runnable non-trivial: {runnable}/{n} = {runnable/n:.3f}")
    print(f"  code-as-reasoning accuracy on runnable slice: {acc_on_runnable:.3f}")
if __name__=="__main__": main()
