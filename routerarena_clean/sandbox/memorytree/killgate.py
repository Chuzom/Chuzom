# SPDX-License-Identifier: MIT
"""MemoryTree Phase 0 — the KILL-GATE.

Tests the make-or-break premise: does a query's SEMANTIC-embedding neighborhood
in a self-generated corpus predict whether the cheap model FAILS it?

Pipeline (all self-generated, no RA data):
  1. graded-difficulty traps → run cheap model → label correct/fail (own gold).
  2. embed prompts with bge-small-en.
  3. train/holdout split; KNN(k) failure-density on holdout.
  4. GATES: (a) cheap failure-rate in [0.10, 0.50] (a signal exists at all);
            (b) separation = P(fail|density>0.5) - P(fail|density<=0.5) >= 0.30
            (agreement got 0.01; grounded verification 1.00).

Run with the RA venv python (numpy/sklearn/torch/transformers):
  <RA>/.venv/bin/python killgate.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from traps_gen import generate  # noqa: E402

SCRATCH = "/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad"
EP = "https://openrouter.ai/api/v1/chat/completions"
CHEAP = "deepseek/deepseek-v4-flash"
N = 500
K = 5


def key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k and os.path.exists(f"{SCRATCH}/.orkey"):
        k = open(f"{SCRATCH}/.orkey").read().strip()
    return k


def call(prompt, k, max_tokens=2000):
    payload = json.dumps({"model": CHEAP, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(EP, data=payload, headers={
        "Authorization": f"Bearer {k}", "Content-Type": "application/json"})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["choices"][0]["message"].get("content") or ""
        except Exception:
            time.sleep(2)
    return ""


_BOX = re.compile(r"\\boxed\{([^{}]+)\}")


def grade(raw, gold):
    ms = _BOX.findall(raw or "")
    cand = ms[-1].strip() if ms else ""
    if not cand:  # fallback: last number
        nums = re.findall(r"-?\d[\d,]*\.?\d*", (raw or "").replace(",", ""))
        cand = nums[-1] if nums else ""
    g = str(gold).strip()
    if cand.replace(",", "") == g:
        return 1
    try:
        return int(abs(float(cand.replace(",", "")) - float(g)) < 1e-6)
    except Exception:
        return 0


def embed(prompts):
    """Semantic embeddings via bge-small-en; TF-IDF fallback if unavailable."""
    try:
        import torch
        from transformers import AutoTokenizer, AutoModel
        name = "BAAI/bge-small-en-v1.5"
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModel.from_pretrained(name).eval()
        vecs = []
        with torch.no_grad():
            for i in range(0, len(prompts), 32):
                batch = prompts[i:i + 32]
                enc = tok(batch, padding=True, truncation=True, max_length=256, return_tensors="pt")
                out = model(**enc)
                emb = out.last_hidden_state[:, 0]  # CLS pooling (bge convention)
                emb = torch.nn.functional.normalize(emb, dim=1)
                vecs.append(emb.cpu().numpy())
        import numpy as np
        return np.vstack(vecs), "bge-small-en"
    except Exception as e:
        sys.stderr.write(f"[embed] bge unavailable ({e}); falling back to TF-IDF\n")
        from sklearn.feature_extraction.text import TfidfVectorizer
        X = TfidfVectorizer(max_features=4096).fit_transform(prompts).toarray()
        return X, "tfidf"


def main():
    import numpy as np
    from sklearn.neighbors import NearestNeighbors
    from sklearn.metrics import roc_auc_score

    k = key()
    traps = generate(N)
    print(f"traps: {len(traps)} | running {CHEAP}...", flush=True)

    labels = [None] * len(traps)
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(call, t["prompt"], k): i for i, t in enumerate(traps)}
        for f in as_completed(futs):
            i = futs[f]
            labels[i] = grade(f.result(), traps[i]["answer"])
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(traps)} ({time.time()-t0:.0f}s)", flush=True)

    fail = np.array([1 - x for x in labels])
    fail_rate = float(fail.mean())
    print(f"\ncheap-model FAILURE rate: {fail_rate:.3f}  (need 0.10-0.50 for a signal)", flush=True)

    print("embedding...", flush=True)
    X, emb_name = embed([t["prompt"] for t in traps])
    print(f"embedder: {emb_name}, dim={X.shape[1]}", flush=True)

    rng = np.random.RandomState(7)
    idx = rng.permutation(len(traps))
    cut = int(0.7 * len(traps))
    tr, ho = idx[:cut], idx[cut:]

    nn = NearestNeighbors(n_neighbors=K, metric="cosine").fit(X[tr])
    _, nbr = nn.kneighbors(X[ho])
    density = np.array([fail[tr][row].mean() for row in nbr])  # neighbor failure density

    ho_fail = fail[ho]
    hi, lo = density > 0.5, density <= 0.5
    p_hi = ho_fail[hi].mean() if hi.any() else float("nan")
    p_lo = ho_fail[lo].mean() if lo.any() else float("nan")
    sep = p_hi - p_lo
    try:
        auc = roc_auc_score(ho_fail, density)
    except Exception:
        auc = float("nan")

    print("\n=== KILL-GATE RESULT ===")
    print(f"  cheap failure rate : {fail_rate:.3f}   gate(0.10-0.50): {'PASS' if 0.10 <= fail_rate <= 0.50 else 'FAIL'}")
    print(f"  P(fail | density>0.5)  = {p_hi:.3f}  (n={int(hi.sum())})")
    print(f"  P(fail | density<=0.5) = {p_lo:.3f}  (n={int(lo.sum())})")
    print(f"  SEPARATION = {sep:.3f}   gate(>=0.30): {'PASS' if sep >= 0.30 else 'FAIL'}   (agreement=0.01, grounded-verify=1.00)")
    print(f"  ROC-AUC(density→fail) = {auc:.3f}   (0.5=useless, >0.7=useful)")
    verdict = "PROMISING — build the pipeline" if (0.10 <= fail_rate <= 0.50 and sep >= 0.30) else "DEAD — same wall as agreement"
    print(f"\n  VERDICT: {verdict}")

    json.dump({"n": len(traps), "cheap": CHEAP, "fail_rate": fail_rate, "embedder": emb_name,
               "separation": float(sep), "auc": float(auc), "p_fail_hi": float(p_hi),
               "p_fail_lo": float(p_lo)}, open(f"{os.path.dirname(__file__)}/killgate_result.json", "w"), indent=2)


if __name__ == "__main__":
    main()
