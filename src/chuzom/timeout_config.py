"""Configurable timeout values for all external operations.

This module centralizes timeout management to prevent DoS via hardcoded
values. All timeouts are configurable via environment variables, with
sensible defaults.

Environment Variables:
- CHUZOM_REQUEST_TIMEOUT: HTTP request timeout in seconds (default: 120)
- CHUZOM_MEDIA_REQUEST_TIMEOUT: Media generation timeout (default: 600)
- CHUZOM_CODEX_TIMEOUT: Codex CLI execution timeout (default: 300)
- CHUZOM_SUBPROCESS_TIMEOUT: Hook/tool subprocess timeout (default: 15)
- CHUZOM_HTTP_TIMEOUT: Quick HTTP operations (default: 10)
- CHUZOM_BENCHMARK_TIMEOUT: Benchmark fetch timeout (default: 30)
"""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_timeout_config() -> dict[str, int]:
    """Get all configured timeout values from environment.

    Returns a dict with timeout values. All values are validated to be
    positive integers. Falls back to defaults if env vars are invalid.

    Returns:
        Dictionary with keys:
        - request_timeout: Standard HTTP requests (seconds)
        - media_request_timeout: Media generation (seconds)
        - codex_timeout: Codex CLI execution (seconds)
        - subprocess_timeout: Hook/tool subprocess calls (seconds)
        - http_timeout: Quick HTTP operations (seconds)
        - benchmark_timeout: Benchmark fetching (seconds)
    """
    defaults = {
        "request_timeout": 120,
        "media_request_timeout": 600,
        "codex_timeout": 300,
        "subprocess_timeout": 15,
        "http_timeout": 10,
        "benchmark_timeout": 30,
    }

    env_mapping = {
        "request_timeout": "CHUZOM_REQUEST_TIMEOUT",
        "media_request_timeout": "CHUZOM_MEDIA_REQUEST_TIMEOUT",
        "codex_timeout": "CHUZOM_CODEX_TIMEOUT",
        "subprocess_timeout": "CHUZOM_SUBPROCESS_TIMEOUT",
        "http_timeout": "CHUZOM_HTTP_TIMEOUT",
        "benchmark_timeout": "CHUZOM_BENCHMARK_TIMEOUT",
    }

    config = {}
    for key, env_var in env_mapping.items():
        try:
            value = int(os.environ.get(env_var, defaults[key]))
            if value <= 0:
                raise ValueError("Timeout must be positive")
            config[key] = value
        except (ValueError, TypeError):
            # Invalid env var — use default
            config[key] = defaults[key]

    return config


def request_timeout() -> int:
    """Standard HTTP request timeout (default: 120s).

    Set via CHUZOM_REQUEST_TIMEOUT environment variable.
    """
    return get_timeout_config()["request_timeout"]


def media_request_timeout() -> int:
    """Media generation request timeout (default: 600s).

    Video and image generation can take several minutes.
    Set via CHUZOM_MEDIA_REQUEST_TIMEOUT environment variable.
    """
    return get_timeout_config()["media_request_timeout"]


def codex_timeout() -> int:
    """Codex CLI execution timeout (default: 300s).

    Maximum time to wait for Codex agent to complete a task.
    Set via CHUZOM_CODEX_TIMEOUT environment variable.
    """
    return get_timeout_config()["codex_timeout"]


def subprocess_timeout() -> int:
    """Hook and tool subprocess call timeout (default: 15s).

    Used for quick subprocess operations like git, python, shell commands.
    Set via CHUZOM_SUBPROCESS_TIMEOUT environment variable.
    """
    return get_timeout_config()["subprocess_timeout"]


def http_timeout() -> int:
    """Quick HTTP operation timeout (default: 10s).

    Used for fast operations like status checks, metadata fetches.
    Set via CHUZOM_HTTP_TIMEOUT environment variable.
    """
    return get_timeout_config()["http_timeout"]


def benchmark_timeout() -> int:
    """Benchmark data fetch timeout (default: 30s).

    Used when fetching benchmark data and quality metrics.
    Set via CHUZOM_BENCHMARK_TIMEOUT environment variable.
    """
    return get_timeout_config()["benchmark_timeout"]


def reset_cache() -> None:
    """Reset the timeout config cache (for testing).

    After modifying environment variables in tests, call this to
    reload the configuration.
    """
    get_timeout_config.cache_clear()
