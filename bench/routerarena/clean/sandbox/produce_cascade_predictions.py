# SPDX-License-Identifier: MIT
"""GO runner — generate the calibrated-cascade prediction file for RouterArena.

This is the `produce_fn` the seal (measure_ra_once.py) needs wired. It runs the
confidence-gated cascade (router_core.decide, the same τ=1.0 frozen router that
ChuzomCleanRouter wraps) over the RA prompts and writes an RA-format prediction
file. It does NOT score (that's llm_evaluation/run.py) and does NOT open a PR.

COST: real. Per prompt it calls the 2 cheap probes (qwen3-235b, deepseek-v4-flash)
and, on disagreement, the strong model (deepseek-v3.2) for the final answer —
~16k+ OpenRouter calls over 8,400 prompts. Requires OPENROUTER_API_KEY.

Dry-run (--dry) uses a stub call_fn (no network, no key, no cost) purely to
validate that the prompt loading + prediction schema are correct before the real,
paid run. The dry file is meaningless for scoring — it exists only to prove the
plumbing.

Usage:
    # format check, free:
    python produce_cascade_predictions.py --dry
    # real run (paid; needs OPENROUTER_API_KEY):
    OPENROUTER_API_KEY=... python produce_cascade_predictions.py --out cascade.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))  # routerarena_clean on path
from router_core import Pool, decide, extract_answer  # noqa: E402

# RA environment that survived from the prior session (harness + prompts).
_RA = Path("/private/tmp/claude-501/-Users-yaliandrona-Projects-Chuzom/"
           "c9a5b736-0e27-4199-8854-b3c25f17e7b5/scratchpad/RA")
# Prompts (+ global index) are carried by any prediction file; solo-v32 has all 8400.
_PROMPTS_SRC = _RA / "router_inference/predictions/chuzom-solo-v32.json"

_CHEAP = ["qwen/qwen3-235b-a22b-2507", "deepseek/deepseek-v4-flash"]
_STRONG = "deepseek/deepseek-v3.2"
_TAU = 1.0
_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def _load_env_file(path: Path = Path.home() / ".chuzom" / ".env") -> None:
    """Load KEY=VALUE lines from the user's ~/.chuzom/.env into os.environ.

    The user populates this file themselves; the runner reads it at call time.
    The value is never printed or otherwise surfaced — standard app config load.
    Existing env vars win (never overwrite).
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _openrouter_call(model: str, prompt: str) -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set — real run needs it")
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 700, "temperature": 0}).encode()
    req = urllib.request.Request(
        _ENDPOINT, data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def _stub_call(model: str, prompt: str) -> str:
    return ""  # dry-run: no network; validates schema only


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="stub calls, no key, no cost")
    ap.add_argument("--out", default=str(_HERE / "chuzom-cascade.json"))
    ap.add_argument("--limit", type=int, default=0, help="cap prompts (0=all)")
    args = ap.parse_args()

    if not args.dry:
        _load_env_file()  # pull OPENROUTER_API_KEY from the user's ~/.chuzom/.env

    if not _PROMPTS_SRC.is_file():
        print(f"RA prompts not found at {_PROMPTS_SRC} — the RA env is not present.",
              file=sys.stderr)
        return 1
    src = json.load(open(_PROMPTS_SRC))
    if args.limit:
        src = src[: args.limit]

    pool = Pool(cheap=_CHEAP, strong=_STRONG, all_models=_CHEAP + [_STRONG])
    call = _stub_call if args.dry else _openrouter_call

    preds, escalated = [], 0
    for i, row in enumerate(src):
        prompt = row["prompt"]
        d = decide(prompt, call, pool, tau=_TAU)
        escalated += int(d.escalated)
        # Final answer from the chosen model (dry: empty).
        answer = "" if args.dry else extract_answer(call(d.model, prompt))
        preds.append({
            "global index": row.get("global index", i),
            "prompt": prompt,
            "prediction": d.model,
            "generated_result": json.dumps({"generated_answer": answer}),
            "cost": None, "accuracy": None, "for_optimality": False,
        })
        if not args.dry and (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(src)} routed ({escalated} escalated)")

    Path(args.out).write_text(json.dumps(preds), encoding="utf-8")
    print(f"wrote {len(preds)} predictions → {args.out}  "
          f"(escalated {escalated}/{len(preds)} = {escalated/len(preds):.1%})"
          f"{'  [DRY — schema only, not for scoring]' if args.dry else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
