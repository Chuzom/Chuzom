"""Router protocol — the contract every benchmark contender implements.

A Router takes a prompt and returns a RouterResult capturing what model was
chosen, the response text, token usage, cost, and latency. Routers are
plug-in: drop a new class in, register it in the runner's REGISTRY, and it
competes head-to-head on the same corpus.

This is intentionally NOT tied to Chuzom internals — a LiteLLM router, an
OpenRouter API call, or a third-party gateway can all be wrapped as a
Router and benchmarked alongside Chuzom.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RouterResult:
    """What a router returns for a single prompt.

    Attributes:
        router_name: Identifier of the router that produced this.
        model_chosen: The provider/model that actually answered.
        response: The model's text response.
        input_tokens: Tokens in the prompt.
        output_tokens: Tokens in the response.
        cost_usd: Cost of this single call (in USD).
        latency_ms: Wall-clock latency from request to response.
        notes: Free-form router-specific metadata (chain attempted, signals
            that fired, fallback count, etc.). Surfaced in the report but
            doesn't affect ranking.
        error: Non-empty if the call failed; response should be empty.
    """

    router_name: str
    model_chosen: str
    response: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    notes: dict = field(default_factory=dict)
    error: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def failed(self) -> bool:
        return bool(self.error)


class Router(Protocol):
    """Every benchmark contender implements this.

    Routers must be **stateless across calls** for the benchmark to be
    reproducible — any internal caching must be reset between corpus runs
    or disclosed in notes.
    """

    name: str

    async def route(self, prompt: str) -> RouterResult:
        ...
