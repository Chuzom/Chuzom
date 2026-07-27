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
    # The host frontier (Chuzom-OFF baseline) — priced at the canonical host rate
    # (5/25 per 1M = 0.005/0.025 per 1K), matching cost._HOST_INPUT/OUTPUT_PER_M
    # used across the rest of the accounting surfaces.
    "anthropic/claude-host": (0.005, 0.025),
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
    """The **real** Chuzom router (#5). Classifies the prompt exactly as the
    product does, then routes it through ``chuzom.router.route_and_call`` — the
    same signal → chain → dispatch → fallback path the CLI uses — so the benchmark
    measures the product, not a hand-rolled chain.

    The v0.0.1 stub (a hardcoded 3-model chain) is retired: it never exercised
    classification, the leaderboard-ordered chain, health filtering, or fallback,
    so a run against it measured a toy. Ledger writes are suppressed so a bench run
    never pollutes the real ``usage.db``.
    """

    name: str = "chuzom"
    allow_llm_classifier: bool = True  # faithful to the product's ambiguous-tail escalation

    async def route(self, prompt: str) -> RouterResult:
        start = time.perf_counter()
        try:
            from chuzom.classify import classify
            from chuzom.router import route_and_call

            sig = await classify(prompt, allow_llm=self.allow_llm_classifier)
            resp = await route_and_call(
                sig.task_type, prompt,
                complexity_hint=sig.complexity,
                suppress_ledger=True,  # a benchmark must not write the product ledger
            )
        except Exception as err:
            return RouterResult(
                router_name=self.name, model_chosen="<exhausted>", response="",
                input_tokens=0, output_tokens=0, cost_usd=0.0,
                latency_ms=int((time.perf_counter() - start) * 1000),
                notes={"strategy": "chuzom"}, error=f"{type(err).__name__}: {err}",
            )

        model = f"{resp.provider}/{resp.model}" if resp.provider and "/" not in resp.model else resp.model
        return RouterResult(
            router_name=self.name,
            model_chosen=model,
            response=resp.content,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=resp.cost_usd,
            latency_ms=int(resp.latency_ms or (time.perf_counter() - start) * 1000),
            notes={
                "strategy": "chuzom",
                "task_type": getattr(sig.task_type, "value", str(sig.task_type)),
                "complexity": getattr(sig.complexity, "value", str(sig.complexity)),
                "classification_method": sig.method,
                "chain_attempts": list(resp.chain_attempts),
                "cache_hit": resp.cache_hit,
                # routing_overhead_usd is intentionally omitted, not fabricated:
                # classify() does not return the classifier's own cost. The
                # heuristic path is genuinely $0; the LLM-classified tail's
                # overhead is a documented follow-up (09_BENCHMARK_HARNESS.md).
            },
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


def claude_host_router(model: str = "anthropic/claude-host") -> "FixedModelRouter":
    """The Chuzom-OFF control arm: the host frontier answers **every** prompt.

    This is the baseline routing is measured *against* for Gates 15/16/17 — "what
    would this corpus have cost, and scored, if Chuzom weren't routing and the
    host (Claude) did everything?" `always-premium` (GPT-4o) is a different
    endpoint; the honest control is the host frontier at the canonical host price.
    """
    return FixedModelRouter(name="always-claude-host", model=model)


def control_group_routers() -> list:
    """The A/B lineup for the savings verdict (bench.savings.evaluate_savings):
    Chuzom ON vs the Chuzom-OFF host control, on the same corpus."""
    return [ChuzomRouter(), claude_host_router()]
