# SPDX-License-Identifier: MIT
"""Phase 1/1b/2 — build the persisted MemoryTree store.

Generates the self-gen trap corpus, runs the CHEAP model, labels success/fail,
embeds with bge-small-en, and saves the memory (embeddings + fail tags + prompts)
for the router to load. All self-generated; no RA data.

Run with the RA venv python.
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from traps_gen import generate            # noqa: E402
from killgate import call, grade, embed, key, CHEAP  # noqa: E402

N = 600
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    import numpy as np
    k = key()
    traps = generate(N)
    print(f"memory corpus: {len(traps)} traps | running {CHEAP}...", flush=True)

    labels = [None] * len(traps)
    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(call, t["prompt"], k): i for i, t in enumerate(traps)}
        for f in as_completed(futs):
            i = futs[f]
            labels[i] = grade(f.result(), traps[i]["answer"])
            done += 1
            if done % 150 == 0:
                print(f"  {done}/{len(traps)} ({time.time()-t0:.0f}s)", flush=True)

    fail = np.array([1 - x for x in labels], dtype=np.int8)
    print(f"cheap failure rate: {fail.mean():.3f}", flush=True)

    print("embedding memory...", flush=True)
    X, emb_name = embed([t["prompt"] for t in traps])
    X = np.asarray(X, dtype=np.float32)

    np.savez(f"{HERE}/memory.npz", emb=X, fail=fail)
    json.dump({"embedder": emb_name, "cheap": CHEAP, "n": len(traps),
               "fail_rate": float(fail.mean()), "dim": int(X.shape[1]),
               "prompts": [t["prompt"] for t in traps],
               "gen": [t["gen"] for t in traps]},
              open(f"{HERE}/memory_meta.json", "w"))
    print(f"saved memory.npz (emb {X.shape}, fail {fail.shape}) + memory_meta.json", flush=True)


if __name__ == "__main__":
    main()
