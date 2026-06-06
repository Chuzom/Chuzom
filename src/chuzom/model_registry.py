"""Model registry — benchmark-derived metadata for every routable model.

Sourced primarily from https://artificialanalysis.ai/leaderboards/models
which publishes quality scores, prices, latency p50, and capabilities
across all major LLMs. We ship a static snapshot under
``config/models.yaml`` so the registry works offline; it's refreshed
periodically via ``scripts/refresh-model-registry.py``.

The router consumes this registry to:
    - Tag each routing decision with the chosen model's tier + quality
    - Compute "could we have used something cheaper at the same quality?"
    - Build the cost-vs-quality Pareto frontier in the benchmark harness
    - Drive empirical lookup tables (v0.0.3 quality_gap derivation)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from chuzom.lineage import Tier


@dataclass(frozen=True)
class ModelMetadata:
    """One row of the registry — everything the router needs to decide."""

    id: str  # canonical id, e.g. "openai/gpt-4o-mini"
    provider: str  # "openai", "anthropic", "google", "ollama", ...
    tier: Tier
    quality_score: float  # 0.0–1.0, normalized from artificialanalysis.ai
    price_per_1m_input_usd: float
    price_per_1m_output_usd: float
    latency_p50_ms: int = 0  # observed median latency
    context_window: int = 0  # in tokens
    capabilities: tuple[str, ...] = ()  # "vision", "function-calling", "json", ...
    source: str = "artificialanalysis.ai"  # provenance
    notes: str = ""

    @property
    def cost_efficiency(self) -> float:
        """Quality per dollar (per 1M tokens, weighted output-heavy)."""
        avg_price = (
            self.price_per_1m_input_usd * 0.3
            + self.price_per_1m_output_usd * 0.7
        )
        if avg_price <= 0:
            return float("inf")  # free models top the chart
        return self.quality_score / avg_price


@dataclass
class ModelRegistry:
    """Lookup + filter operations over a set of ModelMetadata."""

    models: dict[str, ModelMetadata] = field(default_factory=dict)

    @classmethod
    def from_models(cls, models: Iterable[ModelMetadata]) -> "ModelRegistry":
        return cls(models={m.id: m for m in models})

    @classmethod
    def from_yaml(cls, path: Path) -> "ModelRegistry":
        import yaml

        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict) or "models" not in raw:
            raise ValueError(f"{path}: expected top-level 'models:' list")
        return cls.from_models(_parse(m) for m in raw["models"])

    @classmethod
    def load_default(cls) -> "ModelRegistry":
        """Load config/models.yaml from the project root.

        Falls back to a hardcoded minimal registry if the file is absent
        (so the import never breaks Chuzom).
        """
        # Project-level config
        candidates = [
            Path.cwd() / "config" / "models.yaml",
            Path(__file__).resolve().parent.parent.parent / "config" / "models.yaml",
        ]
        for path in candidates:
            if path.exists():
                return cls.from_yaml(path)
        return cls.from_models(_BUNDLED_DEFAULTS)

    # ── Lookup ─────────────────────────────────────────────────────────

    def get(self, model_id: str) -> ModelMetadata | None:
        return self.models.get(model_id)

    def all(self) -> list[ModelMetadata]:
        return list(self.models.values())

    def by_tier(self, tier: Tier) -> list[ModelMetadata]:
        return [m for m in self.models.values() if m.tier == tier]

    def by_provider(self, provider: str) -> list[ModelMetadata]:
        return [m for m in self.models.values() if m.provider == provider]

    def with_capability(self, capability: str) -> list[ModelMetadata]:
        return [m for m in self.models.values() if capability in m.capabilities]

    def cheaper_with_equal_quality(
        self, target: ModelMetadata, quality_tolerance: float = 0.05
    ) -> list[ModelMetadata]:
        """Find models with quality within tolerance of target but cheaper.

        The empirical lookup table can use this to suggest downshifts:
        'you chose GPT-4o, but Sonnet costs less at the same quality'.
        """
        target_price = target.price_per_1m_input_usd
        out = []
        for m in self.models.values():
            if m.id == target.id:
                continue
            if abs(m.quality_score - target.quality_score) > quality_tolerance:
                continue
            if m.price_per_1m_input_usd < target_price:
                out.append(m)
        return sorted(out, key=lambda m: m.price_per_1m_input_usd)

    def pareto_frontier(self) -> list[ModelMetadata]:
        """Models on the cost/quality frontier — no other model weakly
        dominates (≤ cost AND ≥ quality, strict in at least one).

        A model is dominated when some other model is at-least-as-cheap
        AND at-least-as-high-quality AND strictly better in at least one
        of the two dimensions. This is the standard Pareto definition;
        equal-quality + strictly-cheaper drops the more expensive one.
        """
        front = []
        for cand in self.models.values():
            dominated = False
            for other in self.models.values():
                if other.id == cand.id:
                    continue
                cheaper = (
                    other.price_per_1m_input_usd < cand.price_per_1m_input_usd
                )
                better = other.quality_score > cand.quality_score
                cheaper_or_equal = (
                    other.price_per_1m_input_usd
                    <= cand.price_per_1m_input_usd
                )
                better_or_equal = other.quality_score >= cand.quality_score
                if cheaper_or_equal and better_or_equal and (cheaper or better):
                    dominated = True
                    break
            if not dominated:
                front.append(cand)
        return sorted(front, key=lambda m: m.price_per_1m_input_usd)


# ────────────────────────────────────────────────────────────────────────
# YAML parser
# ────────────────────────────────────────────────────────────────────────

def _parse(entry: dict) -> ModelMetadata:
    required = ("id", "provider", "tier", "quality_score",
                "price_per_1m_input_usd", "price_per_1m_output_usd")
    missing = [k for k in required if k not in entry]
    if missing:
        raise ValueError(f"model entry missing required keys: {missing}")

    tier_str = entry["tier"]
    try:
        tier = Tier(tier_str)
    except ValueError:
        raise ValueError(
            f"invalid tier {tier_str!r} for model {entry['id']!r}; "
            f"must be one of {[t.value for t in Tier]}"
        )

    return ModelMetadata(
        id=str(entry["id"]),
        provider=str(entry["provider"]),
        tier=tier,
        quality_score=float(entry["quality_score"]),
        price_per_1m_input_usd=float(entry["price_per_1m_input_usd"]),
        price_per_1m_output_usd=float(entry["price_per_1m_output_usd"]),
        latency_p50_ms=int(entry.get("latency_p50_ms", 0)),
        context_window=int(entry.get("context_window", 0)),
        capabilities=tuple(entry.get("capabilities", ())),
        source=str(entry.get("source", "artificialanalysis.ai")),
        notes=str(entry.get("notes", "")),
    )


# ────────────────────────────────────────────────────────────────────────
# Bundled defaults — used when config/models.yaml is absent
# Updated 2026-06; values approximate, refresh from artificialanalysis.ai
# ────────────────────────────────────────────────────────────────────────

_BUNDLED_DEFAULTS: tuple[ModelMetadata, ...] = (
    ModelMetadata(
        id="ollama/qwen3.5:latest", provider="ollama", tier=Tier.LOCAL,
        quality_score=0.68, price_per_1m_input_usd=0.0,
        price_per_1m_output_usd=0.0,
        latency_p50_ms=1800, context_window=32768,
        capabilities=("function-calling",),
        notes="Local Ollama; free at the API boundary",
    ),
    ModelMetadata(
        id="anthropic/claude-3.5-haiku", provider="anthropic", tier=Tier.CHEAP,
        quality_score=0.74, price_per_1m_input_usd=0.80,
        price_per_1m_output_usd=4.00,
        latency_p50_ms=900, context_window=200000,
        capabilities=("function-calling", "vision"),
    ),
    ModelMetadata(
        id="google/gemini-1.5-flash-8b", provider="google", tier=Tier.CHEAP,
        quality_score=0.65, price_per_1m_input_usd=0.0375,
        price_per_1m_output_usd=0.15,
        latency_p50_ms=600, context_window=1_000_000,
        capabilities=("function-calling", "vision", "json"),
    ),
    ModelMetadata(
        id="openai/gpt-4o-mini", provider="openai", tier=Tier.CHEAP,
        quality_score=0.72, price_per_1m_input_usd=0.15,
        price_per_1m_output_usd=0.60,
        latency_p50_ms=800, context_window=128000,
        capabilities=("function-calling", "vision", "json"),
    ),
    ModelMetadata(
        id="openai/gpt-4o", provider="openai", tier=Tier.MID,
        quality_score=0.85, price_per_1m_input_usd=2.50,
        price_per_1m_output_usd=10.00,
        latency_p50_ms=1500, context_window=128000,
        capabilities=("function-calling", "vision", "json"),
    ),
    ModelMetadata(
        id="anthropic/claude-3.5-sonnet", provider="anthropic", tier=Tier.MID,
        quality_score=0.88, price_per_1m_input_usd=3.00,
        price_per_1m_output_usd=15.00,
        latency_p50_ms=1700, context_window=200000,
        capabilities=("function-calling", "vision"),
    ),
    ModelMetadata(
        id="google/gemini-1.5-pro", provider="google", tier=Tier.MID,
        quality_score=0.82, price_per_1m_input_usd=1.25,
        price_per_1m_output_usd=5.00,
        latency_p50_ms=1800, context_window=2_000_000,
        capabilities=("function-calling", "vision", "json"),
    ),
    ModelMetadata(
        id="openai/o3", provider="openai", tier=Tier.PREMIUM,
        quality_score=0.94, price_per_1m_input_usd=60.0,
        price_per_1m_output_usd=240.0,
        latency_p50_ms=8000, context_window=200000,
        capabilities=("function-calling", "vision", "json", "reasoning"),
        notes="Reasoning-tier — cost reflects extended thinking tokens",
    ),
    ModelMetadata(
        id="anthropic/claude-3-opus", provider="anthropic", tier=Tier.PREMIUM,
        quality_score=0.90, price_per_1m_input_usd=15.0,
        price_per_1m_output_usd=75.0,
        latency_p50_ms=3000, context_window=200000,
        capabilities=("function-calling", "vision"),
    ),
    ModelMetadata(
        id="perplexity/sonar", provider="perplexity", tier=Tier.MID,
        quality_score=0.78, price_per_1m_input_usd=1.00,
        price_per_1m_output_usd=1.00,
        latency_p50_ms=3500, context_window=128000,
        capabilities=("web-grounded", "citations"),
        notes="Web-grounded; cost includes search backend",
    ),
)
