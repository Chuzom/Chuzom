"""In-process routing SDK — ``from chuzom import route``.

For Python agents that prefer a direct call over the HTTP gateway. Same router
(``build_chain`` + ``execute_chain``), same metering into ``usage.db``, no server:

    from chuzom import route
    r = route("Summarize this 10-K risk section ...")
    print(r.text, "via", r.model)

Returns a :class:`RouteResult`. Raises :class:`RoutingError` if the model chain
is exhausted (so callers can fall back to a direct provider if they wish).
"""
from __future__ import annotations

from dataclasses import dataclass


class RoutingError(RuntimeError):
    """All models in the chain failed to produce a response."""


@dataclass(frozen=True)
class RouteResult:
    text: str
    model: str          # "provider/model", e.g. "gemini/gemini-2.5-flash"
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def route(prompt: str, *, task_type: str | None = None,
          complexity: str | None = None, timeout: int = 150) -> RouteResult:
    """Route one prompt through Chuzom and return the answer + routing metadata.

    task_type / complexity are inferred from the prompt when omitted.
    """
    # Lazy imports keep ``import chuzom`` cheap.
    from chuzom.gateway import _classify
    from chuzom.hooks.chain_builder import build_chain, get_current_pressure
    from chuzom.hooks.direct_executor import execute_chain

    if not prompt or not prompt.strip():
        raise ValueError("prompt is empty")
    if not task_type or not complexity:
        _t, _c = _classify(prompt)
        task_type, complexity = task_type or _t, complexity or _c

    zone, _pct = get_current_pressure()
    chain = build_chain(complexity, zone, task_type)
    result = execute_chain(prompt, chain, task_type, timeout=timeout)
    if result is None:
        raise RoutingError("Chuzom routing failed — model chain exhausted")

    try:  # meter, like the gateway/hook paths
        from chuzom.hooks.savings_logger import log_direct_savings, log_direct_to_db
        log_direct_to_db(result=result, prompt=prompt, task_type=task_type,
                         complexity=complexity, classifier_type="sdk", session_id="sdk")
        log_direct_savings(result=result, task_type=task_type, complexity=complexity,
                           session_id="sdk", host="sdk")
    except Exception:
        pass

    return RouteResult(
        text=result.text,
        model=f"{result.model.provider}/{result.model.model}",
        provider=result.model.provider,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=int(result.latency_ms or 0),
    )
