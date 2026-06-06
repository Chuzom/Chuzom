"""Token budget calculator — allocates context window space for routed prompts.

When routing to an external model, the prompt must fit within that model's
context window. This module calculates how many tokens to allocate to each
component: system prompt, retrieved context, user prompt, and output reserve.

The budget ensures cheap models (gemma4/8K) aren't overwhelmed with context
they can't process, while large models (Gemini Flash/1M) don't waste money
on unnecessarily bloated prompts.
"""

from __future__ import annotations

from dataclasses import dataclass

from chuzom.types import Complexity, TaskType

# ── Model Context Windows ─────────────────────────────────────────────────────
# Maps model identifiers (or prefixes) to their total context window in tokens.
# When a model isn't found, we use a conservative default.

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # Ollama local models
    "ollama/gemma4:latest": 8_192,
    "ollama/gemma4": 8_192,
    "ollama/qwen3.5:latest": 32_768,
    "ollama/qwen3.5": 32_768,
    "ollama/llama3.2": 128_000,
    "ollama/deepseek-r1": 64_000,
    # OpenAI
    "openai/gpt-4o-mini": 128_000,
    "openai/gpt-4o": 128_000,
    "openai/o3": 200_000,
    "openai/gpt-5.4": 200_000,
    # Gemini
    "gemini/gemini-2.5-flash": 1_048_576,
    "gemini/gemini-2.5-pro": 1_048_576,
    # Anthropic
    "anthropic/claude-haiku-4-5-20251001": 200_000,
    "anthropic/claude-sonnet-4-6-20260320": 200_000,
    "anthropic/claude-opus-4-6-20260401": 200_000,
    # Groq
    "groq/llama-3.3-70b-versatile": 128_000,
    # DeepSeek
    "deepseek/deepseek-chat": 64_000,
    # Codex
    "codex/gpt-5.4": 200_000,
    "codex/o3": 200_000,
}

# Prefix-based fallbacks for models not in the exact dict
_PREFIX_LIMITS: dict[str, int] = {
    "ollama/": 8_192,       # Conservative default for unknown Ollama models
    "openai/": 128_000,
    "gemini/": 1_048_576,
    "anthropic/": 200_000,
    "groq/": 128_000,
    "deepseek/": 64_000,
    "codex/": 200_000,
    "gemini_cli/": 1_048_576,
    "perplexity/": 128_000,
}

_DEFAULT_LIMIT = 32_000  # Conservative fallback


def get_model_context_limit(model: str) -> int:
    """Get the total context window size for a model in tokens.

    Looks up exact model name first, then falls back to prefix matching.
    """
    if model in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model]

    for prefix, limit in _PREFIX_LIMITS.items():
        if model.startswith(prefix):
            return limit

    return _DEFAULT_LIMIT


# ── Usable Budget Caps ────────────────────────────────────────────────────────
# Even for large-context models, we cap the usable budget to avoid wasting money
# on bloated prompts that don't improve quality for simple/moderate tasks.

_USABLE_CAPS: dict[Complexity, int] = {
    Complexity.SIMPLE: 4_000,        # Simple tasks don't need much context
    Complexity.MODERATE: 12_000,     # Moderate: enough for code + prior Q&A
    Complexity.COMPLEX: 30_000,      # Complex: generous but bounded
    Complexity.DEEP_REASONING: 50_000,
}


@dataclass(frozen=True)
class TokenBudget:
    """Token allocation for a prepared prompt.

    Attributes:
        total: Total usable tokens (context window minus output reserve).
        system_tokens: Tokens allocated for system prompt.
        context_tokens: Tokens allocated for retrieved context (cache + code).
        user_tokens: Tokens reserved for the user's original prompt.
        output_reserve: Tokens reserved for model's response.
        model_limit: Raw model context window size.
    """

    total: int
    system_tokens: int
    context_tokens: int
    user_tokens: int
    output_reserve: int
    model_limit: int


def calculate_budget(
    model: str,
    task_type: TaskType,
    complexity: Complexity,
    user_prompt_tokens: int = 0,
) -> TokenBudget:
    """Calculate token budget allocation for a routed prompt.

    Strategy:
    - Start with model's context limit
    - Cap to usable maximum (don't waste money on bloated prompts)
    - Reserve 30% for output
    - Allocate remaining: 10% system, 60% context, 30% user prompt

    Args:
        model: Target model identifier (e.g. "ollama/gemma4:latest").
        task_type: Task being performed.
        complexity: Classified complexity level.
        user_prompt_tokens: Approximate token count of user's prompt (for budget calc).

    Returns:
        TokenBudget with allocation for each prompt component.
    """
    model_limit = get_model_context_limit(model)

    # Cap to usable maximum for this complexity
    usable_cap = _USABLE_CAPS.get(complexity, 12_000)
    usable = min(model_limit, usable_cap)

    # Reserve output space (30% of usable, minimum 1000 tokens)
    output_reserve = max(1_000, int(usable * 0.30))
    remaining = usable - output_reserve

    # If user prompt is known, reserve that exactly; otherwise estimate 15%
    if user_prompt_tokens > 0:
        user_tokens = min(user_prompt_tokens, remaining)
    else:
        user_tokens = min(int(remaining * 0.15), 2_000)

    remaining -= user_tokens

    # System prompt: 10% of remaining, capped at 300 tokens
    system_tokens = min(int(remaining * 0.10), 300)
    remaining -= system_tokens

    # Context gets everything else
    context_tokens = max(0, remaining)

    return TokenBudget(
        total=usable - output_reserve,
        system_tokens=system_tokens,
        context_tokens=context_tokens,
        user_tokens=user_tokens,
        output_reserve=output_reserve,
        model_limit=model_limit,
    )


# ── Model-aware token counting ───────────────────────────────────────────
# tiktoken ships with cl100k_base / o200k_base encodings which cover every
# OpenAI model and approximate non-OpenAI models well. We use it when
# available and fall back to the chars/4 heuristic when (a) tiktoken
# isn't installed, (b) the model name is unknown, or (c) the encoding
# load itself raises (offline, missing tiktoken data).
#
# Anthropic publishes its own count_tokens API but it requires a network
# round-trip — too expensive for hot-path budget checks. cl100k_base
# under-counts Anthropic by ~5–10% on English text, which is acceptable
# for budget sizing.

try:
    import tiktoken as _tiktoken  # type: ignore[import-not-found]
    _HAS_TIKTOKEN = True
except ImportError:  # pragma: no cover — defensive for stripped installs
    _tiktoken = None  # type: ignore[assignment]
    _HAS_TIKTOKEN = False

# Per-model encoding map. Models not listed fall back to cl100k_base,
# which is accurate enough for budget arithmetic.
_MODEL_ENCODING = {
    # OpenAI
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "o1": "o200k_base",
    "o3": "o200k_base",
    "o3-mini": "o200k_base",
    # Anthropic, Gemini, others — approximated via cl100k_base.
    # Acceptable: chars/4 is worse, tiktoken-cl100k is within ~10%.
}

_encoding_cache: dict[str, object] = {}


def _get_encoding(model: str | None):
    """Return a tiktoken encoding for ``model`` (cached) or None on failure.

    Caches by encoding name (not model name) since multiple models share
    the same encoder. Returns None if tiktoken is unavailable so callers
    can fall through to the chars/4 heuristic.
    """
    if not _HAS_TIKTOKEN:
        return None

    enc_name = _MODEL_ENCODING.get(model or "", "cl100k_base")
    cached = _encoding_cache.get(enc_name)
    if cached is not None:
        return cached
    try:
        enc = _tiktoken.get_encoding(enc_name)
    except Exception:  # tiktoken data not cached locally, offline, etc.
        return None
    _encoding_cache[enc_name] = enc
    return enc


def count_tokens(text: str, model: str | None = None) -> int:
    """Accurate token count for ``text`` against ``model``'s tokenizer.

    Uses tiktoken when available; falls back to chars/4 when tiktoken is
    absent, the model is unknown, or encoding load fails. Always returns
    at least 1 to keep budget math non-degenerate.

    Preferred over :func:`estimate_tokens` for cost-attribution paths
    (logging, dashboards, quota enforcement) where the ~10–20% error of
    chars/4 distorts user-facing numbers. Hot-path budget checks can
    keep using ``estimate_tokens`` for speed.
    """
    enc = _get_encoding(model)
    if enc is None:
        return max(1, len(text) // 4)
    try:
        return max(1, len(enc.encode(text)))
    except Exception:
        return max(1, len(text) // 4)


def estimate_tokens(text: str) -> int:
    """Fast token count approximation (chars/4 heuristic).

    Retained for hot-path budget checks where allocation-free speed
    matters more than per-model accuracy. For cost-attribution paths
    (dashboards, quota enforcement, audit), prefer :func:`count_tokens`
    which uses tiktoken when available.
    """
    return max(1, len(text) // 4)


def fits_budget(text: str, budget_tokens: int) -> bool:
    """Check if text fits within a token budget."""
    return estimate_tokens(text) <= budget_tokens


def truncate_to_budget(text: str, budget_tokens: int) -> str:
    """Truncate text to fit within token budget, preserving whole lines.

    Cuts from the end, preserving complete lines where possible.
    Adds a "[truncated]" marker when truncation occurs.
    """
    if fits_budget(text, budget_tokens):
        return text

    # Approximate character limit
    char_limit = budget_tokens * 4 - 20  # Reserve space for marker
    if char_limit <= 0:
        return "[truncated]"

    truncated = text[:char_limit]

    # Try to cut at a line boundary
    last_newline = truncated.rfind("\n")
    if last_newline > char_limit * 0.7:  # Only if we keep >70% of content
        truncated = truncated[:last_newline]

    return truncated + "\n[truncated]"
