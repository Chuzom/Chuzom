"""Built-in benchmark routers — Chuzom + reference baselines.

v0.0.1 ships:
    - ChuzomRouter: signal-driven via chuzom.router (the real product)
    - AlwaysCheapRouter: always picks the cheapest local model (Ollama)
    - AlwaysPremiumRouter: always picks one premium model (GPT-4o default)
    - StaticChainRouter: fixed fallback list, no signal layer (for
      ablation: shows the value of signals vs raw cost-ordered chain)

v0.0.2 candidates: LiteLLMRouter, OpenRouterRouter, AggressiveChuzomRouter
(forcing a specific Chuzom policy profile).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from bench.router_api import RouterResult


# ── Token cost table (USD per 1K tokens) ──────────────────────────────────
# Source: provider pricing pages as of 2026-06. Update when models change.
# Local models (Ollama) are free at the API boundary but consume your CPU.
_PRICES_PER_1K: dict[str, tuple[float, float]] = {
    "ollama/qwen3.5:latest": (0.0, 0.0),
    "ollama/gemma:7b": (0.0, 0.0),
    "openai/gpt-4o": (0.0025, 0.010),
    "openai/gpt-4o-mini": (0.00015, 0.00060),
    "openai/o3": (0.060, 0.240),
    "anthropic/claude-3.5-haiku": (0.00080, 0.0040),
    "anthropic/claude-3.5-sonnet": (0.0030, 0.0150),
    "google/gemini-1.5-flash-8b": (0.0000375, 0.00015),
    "google/gemini-1.5-flash": (0.000075, 0.00030),
}


def _price(model: str, in_tok: int, out_tok: int) -> float:
    """Best-effort price lookup; unknown models return 0.0 with a hint."""
    if model in _PRICES_PER_1K:
        in_price, out_price = _PRICES_PER_1K[model]
        return (in_tok / 1000) * in_price + (out_tok / 1000) * out_price
    return 0.0


async def _call_litellm(model: str, prompt: str) -> tuple[str, int, int]:
    """Run one chat completion via litellm; return (text, input_tok, output_tok).

    Raises ``EmptyResponseError`` on whitespace-only / missing content so the
    cascade in :class:`ChuzomRouter` / :class:`StaticChainRouter` treats it
    the same as a provider exception — matching what the production router
    does at ``chuzom.providers._call_text`` (see Plan 07 §D.3 in
    ``inference_robustness.ensure_non_empty_content``).

    Before this fix the bench accepted ``""`` as a successful response —
    that's what produced the 3-of-5 empty-response rows in
    ``bench/results/20260606-150229.md``. The router would have cascaded;
    the bench simulation did not.
    """
    import litellm  # lazy import — harness tests use FakeRouter and never reach this
    from chuzom.inference_robustness import ensure_non_empty_content

    response = await litellm.acompletion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=512,
    )
    text = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    in_tok = getattr(usage, "prompt_tokens", 0) if usage else 0
    out_tok = getattr(usage, "completion_tokens", 0) if usage else 0
    # Mirror the production check so an empty completion triggers fallback.
    # EmptyResponseError(RuntimeError) bubbles up to the chain loop, which
    # already catches Exception and continues to the next model.
    text = ensure_non_empty_content(text, model)
    return text, in_tok, out_tok


# ─────────────────────────────────────────────────────────────────────────
# Chuzom router — uses the real product
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class ChuzomRouter:
    """The actual Chuzom router. v0.0.1 uses the inherited llm-router chain
    selection. v0.0.2 will exercise the signal/decision engine end-to-end.
    """

    name: str = "chuzom"
    profile: str = "balanced"

    async def route(self, prompt: str) -> RouterResult:
        # v0.0.1 stub: ask the chain to pick the cheapest model that works.
        # The chain is hardcoded here for the smoke; v0.0.2 wires this into
        # chuzom.router.Router.choose_chain(prompt, profile=self.profile).
        chain = [
            "ollama/qwen3.5:latest",
            "google/gemini-1.5-flash-8b",
            "openai/gpt-4o-mini",
        ]
        start = time.perf_counter()
        last_err = ""
        for model in chain:
            try:
                text, in_tok, out_tok = await _call_litellm(model, prompt)
                elapsed = int((time.perf_counter() - start) * 1000)
                return RouterResult(
                    router_name=self.name,
                    model_chosen=model,
                    response=text,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=_price(model, in_tok, out_tok),
                    latency_ms=elapsed,
                    notes={"chain": chain, "fallback_count": chain.index(model)},
                )
            except Exception as err:
                last_err = f"{type(err).__name__}: {err}"
                continue
        return RouterResult(
            router_name=self.name, model_chosen="<exhausted>", response="",
            input_tokens=0, output_tokens=0, cost_usd=0.0,
            latency_ms=int((time.perf_counter() - start) * 1000),
            notes={"chain": chain}, error=last_err or "all models failed",
        )


# ─────────────────────────────────────────────────────────────────────────
# Reference routers — fixed strategies for ablation
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class FixedModelRouter:
    """Always picks one model. Used to define cost / quality endpoints.

    Construct with model='ollama/qwen3.5:latest' for the cheap endpoint, or
    model='openai/gpt-4o' for the premium endpoint.
    """

    name: str
    model: str

    async def route(self, prompt: str) -> RouterResult:
        start = time.perf_counter()
        try:
            text, in_tok, out_tok = await _call_litellm(self.model, prompt)
            return RouterResult(
                router_name=self.name,
                model_chosen=self.model,
                response=text,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=_price(self.model, in_tok, out_tok),
                latency_ms=int((time.perf_counter() - start) * 1000),
                notes={"strategy": "fixed", "model": self.model},
            )
        except Exception as err:
            return RouterResult(
                router_name=self.name, model_chosen=self.model, response="",
                input_tokens=0, output_tokens=0, cost_usd=0.0,
                latency_ms=int((time.perf_counter() - start) * 1000),
                notes={"strategy": "fixed", "model": self.model},
                error=f"{type(err).__name__}: {err}",
            )


@dataclass
class StaticChainRouter:
    """Fallback chain with no signal layer. Demonstrates the value (or not)
    of Chuzom's signal-driven routing relative to a naïve cost-ordered
    chain.
    """

    name: str = "static-chain"
    chain: tuple[str, ...] = (
        "ollama/qwen3.5:latest",
        "google/gemini-1.5-flash-8b",
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
    )

    async def route(self, prompt: str) -> RouterResult:
        start = time.perf_counter()
        last_err = ""
        for model in self.chain:
            try:
                text, in_tok, out_tok = await _call_litellm(model, prompt)
                elapsed = int((time.perf_counter() - start) * 1000)
                return RouterResult(
                    router_name=self.name,
                    model_chosen=model,
                    response=text,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=_price(model, in_tok, out_tok),
                    latency_ms=elapsed,
                    notes={"strategy": "static_chain", "fallback_count": self.chain.index(model)},
                )
            except Exception as err:
                last_err = f"{type(err).__name__}: {err}"
                continue
        return RouterResult(
            router_name=self.name, model_chosen="<exhausted>", response="",
            input_tokens=0, output_tokens=0, cost_usd=0.0,
            latency_ms=int((time.perf_counter() - start) * 1000),
            notes={"strategy": "static_chain"}, error=last_err or "all models failed",
        )


def default_routers() -> list:
    """The v0.0.1 head-to-head lineup."""
    return [
        ChuzomRouter(),
        FixedModelRouter(name="always-cheap", model="ollama/qwen3.5:latest"),
        FixedModelRouter(name="always-premium", model="openai/gpt-4o"),
        StaticChainRouter(),
    ]
