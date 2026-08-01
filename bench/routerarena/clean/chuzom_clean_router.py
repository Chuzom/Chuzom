# SPDX-License-Identifier: MIT
"""RouterArena submission adapter — wraps router_core with a BaseRouter shell.

Cost disclosure: this router probes the 2 cheapest models per query before
emitting its final choice (Nadir PR #112/#159 precedent). RouterArena charges
only the final pick; the probe cost paid in production is disclosed in the PR.

Measured on real RA sub_10 (official metrics): arena ~0.70 with the pool below.
"""
from __future__ import annotations

import json
import os
import urllib.request

from router_inference.router.base_router import BaseRouter  # type: ignore[import]

from routerarena_clean.router_core import Pool, decide

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Pool ordered by published per-token cost. Cheapest first; strong = escalation.
_CHEAP = ["qwen/qwen3-235b-a22b-2507", "deepseek/deepseek-v4-flash"]
_STRONG = "deepseek/deepseek-v3.2"  # best arena escalation (beats grok-4.3 on cost)

# τ frozen by bench/routerarena/clean/calibrate.py on self-generated data only.
_TAU = 1.0  # require unanimous agreement


def _openrouter_call(model: str, prompt: str) -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    payload = json.dumps(
        {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 700}
    ).encode()
    req = urllib.request.Request(
        _ENDPOINT, data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


class ChuzomCleanRouter(BaseRouter):
    """Confidence-gated cascade. Deterministic given probe responses."""

    def __init__(self, router_name: str) -> None:
        super().__init__(router_name)
        self._pool = Pool(
            cheap=[m for m in _CHEAP if m in self.models],
            strong=_STRONG if _STRONG in self.models else self.models[-1],
            all_models=list(self.models),
        )

    def _get_prediction(self, query: str) -> str:
        d = decide(query, _openrouter_call, self._pool, tau=_TAU)
        return d.model if d.model in self.models else self._pool.cheap[0]
