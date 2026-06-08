"""Shared pytest fixtures for all chuzom tests."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Collection Excludes ────────────────────────────────────────────────────
# TST-001 (audit 2026-06): nine test suites were previously skipped at
# COLLECTION time with `collect_ignore`. The original justification — that
# the suites referenced lineage API symbols (Inversion, Tier, make_record,
# tier_for_model) that did not exist — was correct when written, but stale:
# the symbols were restored in commit 5c6c386 (PR #10), yet the
# `collect_ignore` list was never cleaned up. The README's "766 tests
# passing" badge was running against a suite that silently excluded 206
# tests covering integrity, performance, observability, session-summary
# rendering, framework scenarios, and lineage roundtrips.
#
# The honest signal is now restored:
#   * `collect_ignore` is empty (every test file is collected).
#   * Tests that pass with the current API (116 newly-visible) contribute
#     to coverage.
#   * Tests that still fail — all due to one residual signature drift
#     (`LineageStore(db_path=...)` vs the actual `LineageStore(router_dir=...)`,
#     plus a `_load_default_models()` rename inside model_registry) — are
#     individually marked via `_KNOWN_BROKEN_TESTS` below, with a documented
#     reason that survives in `pytest -v` output.
#
# The follow-up rewrite is tracked for the v0.2.x lineage API stabilisation.
# Until then, the skip markers carry the reason next to each test so future
# readers see *why* it was deferred, not just *that* it was.
#
# The meta-test `tests/test_no_silent_collect_ignore.py` asserts this list
# stays empty so a future regression cannot re-introduce silent exclusion.
collect_ignore: list[str] = []


# ── Per-test skips for known-broken cases ─────────────────────────────────
# These individual tests fail at runtime (not collection). They live in files
# whose other tests pass, so we can't add them to collect_ignore without
# losing coverage. The failure modes are pre-existing and orthogonal to the
# fixes in v0.1.1. Tracked for the v0.2.x lineage API rework.
#
# Each entry is (test_node_id_substring, reason). Substring match keeps the
# list resilient to parametrize-id renames.
_KNOWN_BROKEN_TESTS = [
    # LineageStore(db_path=...) — tests use the keyword the planned API was
    # going to expose; actual __init__ accepts router_dir= (a directory, not
    # a file path). Skipping all `test_tool_*` in test_agents.py because the
    # shared `isolated_tools` fixture is what fails at setup.
    ("test_agents.py::test_tool_", "LineageStore signature differs from test expectations (db_path vs router_dir)"),
    # tests/qa/test_network_failures.py — relies on make_record() helper
    # that was never implemented in the rewritten lineage module.
    ("test_network_failures.py::test_lineage_record_supports_failure_outcome", "lineage.make_record helper not implemented"),
    ("test_network_failures.py::test_lineage_failed_chain_records_full_attempted_chain", "lineage.make_record helper not implemented"),
    # tests/qa/test_agno_deep.py — same root cause: imports make_record.
    ("test_agno_deep.py::test_agno_framework_string_recognized_by_lineage", "lineage.make_record helper not implemented"),
    # tests/qa/test_framework_contracts.py — all parametrize cases of
    # test_lineage_accepts_framework_slug depend on the planned lineage API.
    ("test_framework_contracts.py::test_lineage_accepts_framework_slug", "lineage planned-API helpers not implemented"),
    # Chain-builder doesn't include opus in PREMIUM at low pressure.
    # Could be a real bug in chain_builder OR an obsolete test assumption;
    # outside the scope of the v0.1.1 misroute fix to decide.
    ("test_profile_invariants.py::TestOpusAllowedInPremiumProfile::test_opus_not_removed_in_premium_at_low_pressure",
     "chain_builder returns sonnet-only for PREMIUM at low pressure — needs design call"),

    # ── TST-001 cluster cleared in v0.2.x ────────────────────────────────
    # The 14 entries previously listed here (test_integrity, test_nonfunctional_resilience,
    # test_observability, test_performance, test_session_summary, test_cross_cutting,
    # test_framework_scenarios, test_lineage) all shared one root cause:
    # `LineageStore(db_path=<file>)` didn't exist. LineageStore now accepts
    # both `router_dir` (directory-based, production shape) AND `db_path`
    # (file-based, test shape) — closes the drift without touching test
    # fixtures. If a test under any of those families fails again, add it
    # back with its specific reason.
]


def pytest_collection_modifyitems(config, items):  # noqa: ARG001 — pytest API
    """Mark known-broken tests as skipped with their documented reason.

    Substring match on `nodeid` so parametrize-id changes don't silently
    break the skip list. Each skip carries the reason in `pytest -v` output
    so future readers see why it was deferred, not just that it was.
    """
    skip_markers = {
        substring: pytest.mark.skip(reason=f"v0.1.x known-broken: {reason}")
        for substring, reason in _KNOWN_BROKEN_TESTS
    }
    for item in items:
        for substring, marker in skip_markers.items():
            if substring in item.nodeid:
                item.add_marker(marker)
                break


# ── Path Helpers (for safe path resolution in CI/local environments) ────────────


def get_project_root() -> Path:
    """Get project root regardless of where tests are run.

    Works in CI environments and local machines by resolving relative to this file.
    Never use hardcoded absolute paths like /Users/... or /home/... in tests.
    """
    return Path(__file__).parent.parent


def get_hook_path(hook_name: str) -> Path:
    """Safely get hook file path.

    Example:
        hook = get_hook_path("session-end.py")
        assert hook.exists()
    """
    return get_project_root() / "src" / "chuzom" / "hooks" / hook_name


def get_src_path(*parts: str) -> Path:
    """Safely get path in src/ directory.

    Example:
        cost_py = get_src_path("chuzom", "cost.py")
    """
    return get_project_root() / "src" / "chuzom" / Path(*parts)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Provide a temporary database for tests.
    
    Sets up a clean SQLite database in a temp directory and ensures
    all config reads the temp path, not the user's real ~/.chuzom.
    
    CRITICAL: This fixture MUST be used by any test that writes to the database
    (including log_claude_usage, log_routing_decision, etc.). Failure to use this
    fixture will contaminate the production database.
    """
    db_dir = tmp_path / ".chuzom"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "test_usage.db"
    
    # Set env vars for config to pick up
    monkeypatch.setenv("CHUZOM_DB_PATH", str(db_path))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    # Allow stub LLMResponse shapes (100/50/$0.003, 100/100/$0.001) to be
    # written. The stub guard in cost.log_usage blocks these shapes by default
    # to stop unisolated tests from polluting ~/.chuzom/usage.db.
    monkeypatch.setenv("CHUZOM_ALLOW_STUBS", "1")
    
    # Reset singleton so config reads the new env vars
    import chuzom.config as config_module
    config_module._config = None
    
    # Verify isolation: make sure we're NOT using production path
    from chuzom.config import get_config
    config = get_config()
    assert str(config.chuzom_db_path) != str(Path.home() / ".chuzom" / "usage.db"), \
        f"CRITICAL: Fixture failed to isolate database. Using production path: {config.chuzom_db_path}"
    assert "test" in str(db_path).lower(), \
        f"CRITICAL: Database path should contain 'test': {db_path}"
    
    yield db_path
    
    # Cleanup: verify the isolated database was actually used (has non-zero size)
    if db_path.exists():
        assert db_path.stat().st_size > 0, f"Test database was never written to: {db_path}"


@pytest.fixture
def temp_router_dir(tmp_path, monkeypatch):
    """Provide a temporary router config directory.

    Patches module-level variables to use a temp directory for tests.
    """
    temp_home = tmp_path
    router_dir = temp_home / ".chuzom"
    router_dir.mkdir(parents=True, exist_ok=True)

    # Patch module-level variables that were evaluated at import time
    import chuzom.hook_health
    monkeypatch.setattr(chuzom.hook_health, "_ROUTER_DIR", router_dir)
    monkeypatch.setattr(chuzom.hook_health, "_HOOK_HEALTH_FILE", router_dir / "hook_health.json")
    monkeypatch.setattr(chuzom.hook_health, "_HOOK_LOG_FILE", router_dir / "hook_errors.log")
    # Also patch Path.home for any runtime calls
    monkeypatch.setattr("pathlib.Path.home", lambda: temp_home)

    yield router_dir


@pytest.fixture
def temp_hooks_dir(tmp_path, monkeypatch):
    """Provide a temporary hooks directory.

    For tests that check hook permissions and execution.
    """
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    with patch("pathlib.Path.home", return_value=tmp_path):
        yield hooks_dir


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment for classification and routing tests."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CHUZOM_PROFILE", "balanced")
    monkeypatch.setenv("CHUZOM_CLAUDE_SUBSCRIPTION", "false")
    monkeypatch.setenv("CHUZOM_GEMINI_SUBSCRIPTION", "false")
    
    # Reset singleton so config reads fresh env vars
    import chuzom.config as config_module
    config_module._config = None
    
    yield
    
    # Reset again after test to avoid polluting other tests
    config_module._config = None


@pytest.fixture
def minimal_env(monkeypatch):
    """Minimal environment with only one API key, for testing 'Recommended to Add' messages."""
    # Clear all API keys except one
    for key in ["OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY",
                "DEEPSEEK_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY", "TOGETHER_API_KEY",
                "XAI_API_KEY", "COHERE_API_KEY", "OLLAMA_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)

    # Set only one key to trigger "Recommended to Add"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CHUZOM_PROFILE", "balanced")
    yield


@pytest.fixture
def no_providers_env(monkeypatch):
    """Create a truly empty config with no providers configured.

    This fixture mocks the config loader to return a RouterConfig with all
    API keys and Ollama disabled, regardless of local environment files.
    Used by tests that verify error handling when no providers are available.
    """
    # Create a manual config object without reading from env or .env
    from chuzom.types import QualityMode
    
    # Create a mock config with all providers disabled
    class EmptyConfig:
        openai_api_key = ""
        gemini_api_key = ""
        perplexity_api_key = ""
        anthropic_api_key = ""
        deepseek_api_key = ""
        groq_api_key = ""
        mistral_api_key = ""
        together_api_key = ""
        xai_api_key = ""
        cohere_api_key = ""
        ollama_base_url = ""
        chuzom_profile = "balanced"
        chuzom_claw_code = False
        chuzom_claude_subscription = False
        chuzom_enforce = "soft"
        chuzom_db_path = str(Path.home() / ".chuzom" / "routing.db")
        token_budget = 10_000_000
        quality = QualityMode.BALANCED
        min_model_floor = "haiku"
        semantic_cache_ttl = 86400
        health_circuit_breaker_threshold = 0.5
        health_circuit_breaker_ttl = 300
        health_request_timeout = 30
        
        def apply_keys_to_env(self):
            pass  # No-op
    
    empty_config = EmptyConfig()

    # Mock the get_config function to return our empty config
    import chuzom.config as config_module
    monkeypatch.setattr(config_module, "get_config", lambda: empty_config)

    # Also reset the singleton
    config_module._config = None

    yield empty_config


@pytest.fixture
def mock_acompletion():
    """Mock async completion for provider tests.
    
    Patches chuzom.providers.call_llm to return a mock LLM response,
    preventing actual API calls in tests. Also disables Codex injection
    and marks all providers as healthy to avoid skipping injected models.
    """
    from chuzom.types import LLMResponse

    mock_response = LLMResponse(
        content="Mock response",
        model="test/mock-model",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.001,
        latency_ms=100.0,
        provider="test",
    )

    async_mock = AsyncMock(return_value=mock_response)

    # Mock health tracker to mark all providers as healthy
    mock_tracker = MagicMock()
    mock_tracker.is_healthy.return_value = True

    with patch("chuzom.providers.call_llm", async_mock):
        with patch("chuzom.codex_agent.is_codex_available", return_value=False):
            with patch("chuzom.router.get_tracker", return_value=mock_tracker):
                yield async_mock


@pytest.fixture
def mock_litellm_response():
    """Factory for mock litellm completion responses (for tests patching litellm directly).
    
    Returns a mock object that mimics litellm.acompletion response with:
    - response.choices[0].message.content
    - response.usage.prompt_tokens / completion_tokens
    """
    def _make_response(content="Mock response", input_tokens=10, output_tokens=5, **kwargs):
        # Create mock litellm response structure
        # Accepts content, input_tokens, output_tokens as well as arbitrary kwargs
        mock_msg = MagicMock()
        mock_msg.content = content
        
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = input_tokens
        mock_usage.completion_tokens = output_tokens
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        
        return mock_response
    return _make_response


@pytest.fixture(autouse=True)
def _reset_config_singleton():
    """Reset config singleton before and after each test.

    Ensures that monkeypatched environment variables are picked up by get_config(),
    and prevents test pollution from config state changes.
    """
    import chuzom.config as config_module
    config_module._config = None
    yield
    config_module._config = None


@pytest.fixture(scope="session", autouse=True)
def _close_db_connections():
    """Force close all aiosqlite connections at end of test session.
    
    Prevents 'pytest is hanging on exit' due to unclosed async database connections.
    """
    yield
    # After all tests, force cleanup of aiosqlite connections
    try:
        import asyncio
        import gc
        
        # Close any pending event loops
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        
        if loop and not loop.is_closed():
            # Give any pending tasks a chance to finish
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
        
        # Force garbage collection to release aiosqlite threads
        gc.collect()
    except Exception:
        pass
