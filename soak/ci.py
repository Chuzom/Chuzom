"""Bootstrap confidence intervals for the Phase 0 soak report.

Small, dependency-free (stdlib ``random`` only) percentile bootstrap. Used to
put a 95% CI around per-row figures collected by ``replay.py`` (net realized
$ savings for metered rows, realized quota-tokens for subscription rows).
"""

from __future__ import annotations

import random
import statistics
from typing import TypedDict


class BootstrapResult(TypedDict):
    point: float
    ci95: list[float]


def bootstrap_ci(
    values: list[float],
    *,
    n_resamples: int = 10_000,
    seed: int = 0,
) -> BootstrapResult:
    """Percentile bootstrap 95% CI over ``values``.

    ``point`` is the sample mean of ``values`` (not a resample mean) --
    the CI band brackets it. An empty or single-value input degenerates
    gracefully to a zero-width interval rather than raising, since a soak
    corpus slice for one host_mode may legitimately be empty.
    """
    if not values:
        return {"point": 0.0, "ci95": [0.0, 0.0]}

    point = statistics.fmean(values)
    if len(values) == 1:
        return {"point": round(point, 6), "ci95": [round(point, 6), round(point, 6)]}

    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    for _ in range(n_resamples):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.fmean(resample))
    means.sort()

    def _pct(p: float) -> float:
        idx = min(n_resamples - 1, max(0, round(p / 100.0 * (n_resamples - 1))))
        return means[idx]

    lo = _pct(2.5)
    hi = _pct(97.5)
    return {"point": round(point, 6), "ci95": [round(lo, 6), round(hi, 6)]}
