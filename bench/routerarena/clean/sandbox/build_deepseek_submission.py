# SPDX-License-Identifier: MIT
"""Build a clean single-model submission: route EVERYTHING to deepseek/deepseek-v3.2.

Reuses deepseek-v3.2 answers already present in chuzom-clean.json (3652 rows);
generates the remaining rows fresh (temp 0). Output is a full 8400-row prediction
file with prediction='deepseek/deepseek-v3.2' and generated_result populated.

Compliant: a single-model baseline router; no RA-derived supervision anywhere.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_ra_mechanism import key  # noqa: E402

RA = Path("/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/"
          "c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad/RA")
SRC = RA / "router_inference/predictions/chuzom-clean.json"
OUT = RA / "router_inference/predictions/chuzom-solo-v32.json"
MODEL = "deepseek/deepseek-v3.2"
EP = "https://openrouter.ai/api/v1/chat/completions"


def call(prompt, k, max_tokens=1024):
    payload = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(EP, data=payload, headers={
        "Authorization": f"Bearer {k}", "Content-Type": "application/json"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
                return d["choices"][0]["message"].get("content") or "", None
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return "", f"AUTH_{e.code}"
            time.sleep(2); last = f"HTTP_{e.code}"
        except Exception as e:
            time.sleep(2); last = str(e)
    return "", last


def main():
    k = key()
    rows = json.load(open(SRC))
    # rows already answered by deepseek keep their generated_result
    todo = [i for i, r in enumerate(rows) if r["prediction"] != MODEL or not r.get("generated_result")]
    print(f"total rows {len(rows)} | already have deepseek {len(rows)-len(todo)} | to generate {len(todo)}",
          flush=True)

    def work(i):
        msg, err = call(rows[i]["prompt"], k)
        return i, msg, err

    done, errs, t0 = 0, 0, time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(work, i) for i in todo]
        for f in as_completed(futs):
            i, msg, err = f.result()
            rows[i]["prediction"] = MODEL
            rows[i]["generated_result"] = msg
            rows[i]["cost"] = None
            rows[i]["accuracy"] = None
            errs += int(bool(err))
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(todo)} ({time.time()-t0:.0f}s) errs={errs}", flush=True)
                json.dump(rows, open(OUT, "w"))  # checkpoint
    # finalize: every row -> deepseek
    for r in rows:
        r["prediction"] = MODEL
    json.dump(rows, open(OUT, "w"))
    filled = sum(1 for r in rows if r.get("generated_result"))
    print(f"\nwrote {OUT}\nrows with generated_result: {filled}/{len(rows)} | errors: {errs}", flush=True)


if __name__ == "__main__":
    main()
