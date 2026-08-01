import json, os, re, time, urllib.request
SCRATCH="/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
EP="https://openrouter.ai/api/v1/chat/completions"
def key():
    k=os.environ.get("OPENROUTER_API_KEY","").strip()
    if not k and os.path.exists(f"{SCRATCH}/.orkey"): k=open(f"{SCRATCH}/.orkey").read().strip()
    return k
def call(model,prompt,k,mt=1200,temp=0.0):
    p=json.dumps({"model":model,"messages":[{"role":"user","content":prompt}],"max_tokens":mt,"temperature":temp}).encode()
    req=urllib.request.Request(EP,data=p,headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req,timeout=120) as r:
                return json.loads(r.read())["choices"][0]["message"].get("content") or ""
        except Exception: time.sleep(2)
    return ""
_BOX=re.compile(r"\\boxed\{([^{}]+)\}")
def extract(raw):
    ms=_BOX.findall(raw or "")
    if ms: return ms[-1].strip().lower()
    nums=re.findall(r"-?\d[\d,]*\.?\d*",(raw or "").replace(",",""))
    return nums[-1] if nums else re.sub(r"[^a-z0-9 ]","",(raw or "").strip().lower().splitlines()[-1] if (raw or "").strip() else "")
def correct(raw,gold):
    c=extract(raw); g=str(gold).strip().lower()
    if c.replace(",","")==g: return 1
    try: return int(abs(float(c)-float(g))<1e-6)
    except: return 0
