# SPDX-License-Identifier: MIT
"""P1.1 — build the label table over the SELF-GENERATED proxy.

Runs the model pool over every proxy item, grading each with RA's official
metrics (via grader.py). Output feeds:
  • the capability map (P1.2): per-model accuracy by general axis
  • the live-signal threshold calibration (P1.3): probe raw answers → agreement/
    entropy vs. correctness

COMPLIANCE: every label is model correctness on OUR self-generated, computed-answer
proxy. No RouterArena split/accuracy/judge/oracle, no RouterBench. This is exactly
the RA-independent supervision the PR-155 maintainer said is required.

Cost: only for measurement. Pool published OpenRouter pricing (verified via
/api/v1/models); token counts stored so cost is recomputable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # bench/routerarena/clean/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import Grader              # noqa: E402
from proxy_gen import generate_proxy   # noqa: E402
from router_core import extract_answer  # noqa: E402  (extract from FULL raw for agreement)

_HERE = Path(__file__).resolve().parent
_SCRATCH_KEY = Path(
    "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/"
    "c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad/.orkey"
)
EP = "https://openrouter.ai/api/v1/chat/completions"

# Pool: 2 cheap probes + 2 strong escalation candidates. $/M tokens (in, out).
POOL = ["qwen/qwen3-235b-a22b-2507", "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v3.2", "qwen/qwen3.7-plus"]
PRICE = {
    "qwen/qwen3-235b-a22b-2507": (0.09, 0.10),
    "deepseek/deepseek-v4-flash": (0.09, 0.18),
    "deepseek/deepseek-v3.2": (0.229, 0.343),
    "qwen/qwen3.7-plus": (0.32, 1.28),
}


def _key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k and _SCRATCH_KEY.exists():
        k = _SCRATCH_KEY.read_text().strip()
    if not k:
        raise RuntimeError("No OpenRouter key: set OPENROUTER_API_KEY or provide .orkey")
    return k


def call(model: str, prompt: str, key: str, max_tokens: int = 1500):
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(EP, data=payload, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
                # content can be null (e.g. a reasoning model that spent its whole
                # budget on thinking and emitted no answer) — coerce to "".
                msg = d["choices"][0]["message"].get("content") or ""
                u = d.get("usage", {})
                empty = None if msg.strip() else "EMPTY_CONTENT"
                return msg, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), empty
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if e.code in (401, 403):
                return "", 0, 0, f"AUTH_{e.code}:{body}"  # do not retry auth failures
            time.sleep(2)
            last = f"HTTP_{e.code}:{body}"
        except Exception as e:
            time.sleep(2)
            last = str(e)
    return "", 0, 0, last


def cost_of(model: str, pt: int, ct: int) -> float:
    pin, pout = PRICE[model]
    return (pt * pin + ct * pout) / 1e6


def build(n: int, workers: int, out: Path) -> dict:
    key = _key()
    g = Grader()
    proxy = generate_proxy(per_stratum=8)
    if n > 0:
        proxy = proxy[:n]

    # one job per (item, model)
    jobs = [(it, m) for it in proxy for m in POOL]
    results: dict[str, dict] = {it["id"]: {"item": it, "per_model": {}} for it in proxy}

    print(f"label table: {len(proxy)} items × {len(POOL)} models = {len(jobs)} calls "
          f"(workers={workers})", flush=True)

    def work(item, model):
        raw, pt, ct, err = call(model, item["prompt"], key)
        acc = 0.0 if err else g.grade_by_metric(raw, item["answer"], item["metric"])
        # extract from the FULL raw (before any truncation) so the agreement
        # signal is faithful — truncating raw first would cut a trailing \boxed{}.
        ext = "" if err else extract_answer(raw)
        return item["id"], model, {
            "correct": int(round(acc)), "acc": acc, "pt": pt, "ct": ct,
            "cost": cost_of(model, pt, ct), "ext": ext, "raw": raw[:600], "err": err,
        }

    t0, done, auth_fail = time.time(), 0, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(work, it, m): (it["id"], m) for it, m in jobs}
        for f in as_completed(futs):
            fid, fmodel = futs[f]
            try:
                iid, model, rec = f.result()
            except Exception as e:  # one bad call must never kill the whole build
                iid, model, rec = fid, fmodel, {
                    "correct": 0, "acc": 0.0, "pt": 0, "ct": 0, "cost": 0.0,
                    "ext": "", "raw": "", "err": f"WORKER:{type(e).__name__}:{e}"}
            results[iid]["per_model"][model] = rec
            done += 1
            if rec["err"] and rec["err"].startswith("AUTH_"):
                auth_fail += 1
            if done % 50 == 0:
                print(f"  {done}/{len(jobs)} ({time.time()-t0:.0f}s)", flush=True)
    if auth_fail:
        print(f"\n⚠️  {auth_fail} AUTH failures — the key is likely rotated/revoked. "
              "Update .orkey or OPENROUTER_API_KEY.", flush=True)

    # summaries
    per_model = {m: {"n": 0, "correct": 0, "cost": 0.0, "errors": 0} for m in POOL}
    for r in results.values():
        for m, rec in r["per_model"].items():
            s = per_model[m]
            s["n"] += 1
            s["correct"] += rec["correct"]
            s["cost"] += rec["cost"]
            s["errors"] += int(bool(rec["err"]))
    summary = {m: {"accuracy": round(s["correct"] / s["n"], 4) if s["n"] else 0.0,
                   "cost_per_1k": round(s["cost"] / s["n"] * 1000, 4) if s["n"] else 0.0,
                   "errors": s["errors"], "n": s["n"]}
               for m, s in per_model.items()}

    payload = {"models": POOL, "price": PRICE, "n_items": len(proxy),
               "summary": summary,
               "items": [{"id": r["item"]["id"], "domain": r["item"]["domain"],
                          "difficulty": r["item"]["difficulty"], "metric": r["item"]["metric"],
                          "answer": r["item"]["answer"], "per_model": r["per_model"]}
                         for r in results.values()]}
    out.write_text(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="0 = all proxy items")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--smoke", action="store_true", help="2 items only, key+path check")
    ap.add_argument("--out", default=str(_HERE / "label_table.json"))
    args = ap.parse_args()

    n = 2 if args.smoke else args.n
    out = Path(_HERE / "label_table_smoke.json") if args.smoke else Path(args.out)
    rep = build(n=n, workers=args.workers, out=out)
    print("\n=== per-model summary ===")
    print(json.dumps(rep["summary"], indent=2))
    print(f"\nwrote {out}")
