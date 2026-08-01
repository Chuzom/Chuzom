# SPDX-License-Identifier: MIT
"""DISC.1 — generate discriminator TRAINING features on the synthetic corpus.

Every model call goes THROUGH CHUZOM (chuzom.providers.call_llm) — the user's
constraint: only Chuzom's routing. Per synthetic item we call cheap + qwen +
mistral (council 3rd) + coherence-judge, grade cheap vs self-computed gold
(cheap_fail label), and build the shared 8-feature vector. Writes synth_features.json.

Run with the CHUZOM .venv python (has chuzom+litellm), OPENROUTER_API_KEY set.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth_corpus import generate  # noqa: E402
from disc_features import norm_ans, build_features, FEATURE_NAMES  # noqa: E402

from chuzom.providers import call_llm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
N = int(os.environ.get("DISC_N", "2000"))
WORKERS = int(os.environ.get("DISC_WORKERS", "12"))
CALL_TIMEOUT = float(os.environ.get("DISC_TIMEOUT", "60"))

CHEAP = "openrouter/deepseek/deepseek-v4-flash"
QWEN = "openrouter/qwen/qwen3-235b-a22b-2507"
MIST = "openrouter/mistralai/mistral-small-3.2-24b-instruct"
JUDGE = "openrouter/qwen/qwen3-235b-a22b-2507"
JP = ("A student solved a problem. Rate ONLY the logical coherence and likely correctness of their "
      "reasoning from 0 to 10 (10=clearly correct). Reply with ONLY the integer.\n\n"
      "Problem: {q}\n\nStudent's solution:\n{s}")


def jscore(t):
    m = re.search(r"\b(10|[0-9])\b", t or "")
    return int(m.group(1)) if m else 5


def synth_grade(raw, gold):
    ms = re.findall(r"\\boxed\{([^{}]*)\}", raw or "")
    cand = ms[-1].strip() if ms else ""
    if not cand:
        lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
        cand = lines[-1] if lines else ""

    def nrm(s):
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).split()
    if nrm(cand) == nrm(str(gold)):
        return 1
    try:
        return int(abs(float(cand.replace(",", "")) - float(str(gold))) < 1e-6)
    except Exception:
        return 0


async def one(model, prompt, mt=1500):
    for _ in range(3):
        try:
            r = await asyncio.wait_for(
                call_llm(model, [{"role": "user", "content": prompt}],
                         temperature=0, max_tokens=mt),
                timeout=CALL_TIMEOUT)
            if r.content:
                return r.content, float(r.cost_usd or 0.0)
        except Exception as e:
            if os.environ.get("DISC_DEBUG"):
                sys.stderr.write(f"[{model.split('/')[-1]}] {type(e).__name__}: {str(e)[:80]}\n")
                sys.stderr.flush()
        await asyncio.sleep(1.0)
    return "", 0.0


async def work(item):
    p = item["prompt"]
    # stage 1: cheap/qwen/mistral concurrently (judge needs cheap's answer, runs after)
    (cheap_raw, cc), (qwen_raw, qc), (mist_raw, mc) = await asyncio.gather(
        one(CHEAP, p, 1500), one(QWEN, p, 1000), one(MIST, p, 1000))
    judge_raw, jc = await one(JUDGE, JP.format(q=p, s=cheap_raw[:1500]), mt=10)
    coh = jscore(judge_raw)
    ce, qe, me = norm_ans(cheap_raw), norm_ans(qwen_raw), norm_ans(mist_raw)
    feats = build_features(coh, ce, qe, me, p)
    cheap_fail = 0 if synth_grade(cheap_raw, item["answer"]) else 1
    return {"feats": feats, "label": cheap_fail, "kind": item["kind"],
            "cost": cc + qc + mc + jc}


def _dump(rows):
    json.dump({"feature_names": FEATURE_NAMES,
               "X": [r["feats"] for r in rows], "y": [r["label"] for r in rows],
               "kind": [r["kind"] for r in rows],
               "fail_rate": sum(r["label"] for r in rows) / max(len(rows), 1),
               "cost": sum(r["cost"] for r in rows), "n": len(rows)},
              open(f"{HERE}/synth_features.json", "w"))


async def main():
    corpus = generate(N)
    print(f"synthetic: {len(corpus)} items | {WORKERS} workers, calls via CHUZOM...", flush=True)
    rows = [None] * len(corpus)
    t0 = time.time()
    done = [0]
    q = asyncio.Queue()
    for i in range(len(corpus)):
        q.put_nowait(i)

    async def worker():
        while True:
            try:
                i = q.get_nowait()
            except asyncio.QueueEmpty:
                return
            rows[i] = await work(corpus[i])
            done[0] += 1
            if done[0] % 50 == 0:
                el = time.time() - t0
                rate = done[0] / el
                eta = (len(corpus) - done[0]) / rate if rate else 0
                print(f"  {done[0]}/{len(corpus)} ({el:.0f}s, {rate*60:.0f}/min, ETA {eta/60:.0f}m)", flush=True)
            if done[0] % 150 == 0:
                _dump([r for r in rows if r is not None])

    await asyncio.gather(*(worker() for _ in range(WORKERS)))

    fail_rate = sum(r["label"] for r in rows) / len(rows)
    total_cost = sum(r["cost"] for r in rows)
    ml_fail = [r["label"] for r in rows if r["kind"] == "ml"]
    tr_fail = [r["label"] for r in rows if r["kind"] == "trap"]
    print(f"\n  cheap FAIL rate: {fail_rate:.3f}  (trap={sum(tr_fail)/max(len(tr_fail),1):.3f} "
          f"ml={sum(ml_fail)/max(len(ml_fail),1):.3f})")
    print(f"  total Chuzom-routed cost: ${total_cost:.4f}")
    json.dump({"feature_names": FEATURE_NAMES,
               "X": [r["feats"] for r in rows],
               "y": [r["label"] for r in rows],
               "kind": [r["kind"] for r in rows],
               "fail_rate": fail_rate, "cost": total_cost, "n": len(rows)},
              open(f"{HERE}/synth_features.json", "w"))
    print(f"  saved synth_features.json ({len(rows)} rows)")


if __name__ == "__main__":
    asyncio.run(main())
