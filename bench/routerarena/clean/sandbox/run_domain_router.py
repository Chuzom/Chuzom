# SPDX-License-Identifier: MIT
"""Stage 3+4: the vLLM-style domain router, run over RA sub_10 / full.

Per query: embed → score the 14-domain centroids (benchmark-trained, hash-audited)
→ pick the domain → look up the public-priors domain→model map → call THAT model
once. No probes, no cascade → 1 call/query (a cost advantage over the cascade's
2.33). Cost = the chosen model's cost. Graded by grader.py with RA's official
metrics. A deliberate, sealed RA-data touch.

Reuses: eval_ra_mechanism.run/cost_of, semantic_classify embedding + scoring.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from eval_ra_mechanism import cost_of, run  # noqa: E402
from chuzom.semantic_classify import _embed, _norm, _score_head  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
_ART = json.loads((_ROOT / "src/chuzom/data/domain_centroids.json").read_text())
_MAP = json.loads((_ROOT / "bench/routerarena/clean/domain_model_map.json").read_text())

_PROTOS = _ART["domain"]
_T = _ART["temperature"]
_FLOOR = _ART["confidence_floor"]
_MODEL = _ART["embedding_model"]
_DMAP = _MAP["domain"]
_DEFAULT = _MAP["default"]


def route_and_answer(query, call, key):
    v = _embed(query, _MODEL)
    if v:
        dom, conf, _ = _score_head(_norm(v), _PROTOS, _T)
        model = _DMAP.get(dom, _DEFAULT) if conf >= _FLOOR else _DEFAULT
    else:
        model = _DEFAULT  # embedding backend down → safe default
    msg, pt, ct, _err = call(model, query, key)
    return {"chosen_model": model, "raw": msg, "cost": cost_of(model, pt, ct),
            "escalated": False, "n_calls": 1}


def _load_env() -> None:
    p = Path.home() / ".chuzom" / ".env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, val = line.split("=", 1)
        k, val = k.strip(), val.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = val


if __name__ == "__main__":
    _load_env()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    labels_file = sys.argv[2] if len(sys.argv) > 2 else "sub10_labels.json"
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    name = "chuzom-domain-full" if "full" in labels_file else "chuzom-domain"
    run(name, route_and_answer, n=n, workers=workers, labels_file=labels_file)
