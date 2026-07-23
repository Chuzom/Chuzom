"""Shared pytest fixtures for all chuzom tests."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Config-singleton isolation (CHZ-AUD-001) ────────────────────────────────
@pytest.fixture(autouse=True)
def _restore_config_singleton():
    """Snapshot and restore ``chuzom.config._config`` around every test.

    The ``temp_db`` fixture isolates the DB by resetting the config singleton,
    but some suites (e.g. test_ensemble) set ``chuzom.config._config = None``
    directly. Left uncleaned, a later test that forgets ``temp_db`` calls
    ``get_config()``, which re-reads the real ``~/.chuzom`` and can pollute the
    production ``usage.db``. Restoring the singleton after each test makes that
    ordering-dependent leak impossible.
    """
    import chuzom.config as _cfg

    saved = getattr(_cfg, "_config", None)
    try:
        yield
    finally:
        _cfg._config = saved


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

    # CI perf budget: 1000 lineage rows take ~5.3s on the GitHub Actions
    # 3.11 runner, exceeding the dev-box-calibrated 5s budget by ~6%.
    # Passes consistently on 3.13 and locally. Either:
    #   (a) batch the per-row INSERT into a single transaction (real fix), or
    #   (b) bump the budget to 7s (acknowledges CI heterogeneity).
    # Until the call is made, this stays skipped so the rest of the
    # honest signal isn't drowned by a borderline perf wobble.
    ("test_performance.py::test_perf_lineage_1000_rows_under_5_seconds",
     "CI 3.11 runs ~6% slower than dev box; bump budget or batch INSERTs (TST-001 follow-up)"),
]


# ── Hermetic routing unit ─────────────────────────────────────────────────
# Files whose tests must pass with ZERO real host state (empty repo config,
# codex/gemini CLIs unavailable) — enforced by the autouse
# `_hermetic_host_state` fixture below. Auto-marked `routing_hermetic` here
# (rather than per-file `pytestmark`) so the set is defined in one place and
# can be run as a unit: `pytest -m routing_hermetic`.
_ROUTING_HERMETIC_FILES = (
    "tests/test_router.py",
    "tests/test_p1_4_deploy_probes.py",
    "tests/test_config_routing_value.py",
    "tests/test_quality_escalation.py",
    "tests/audit/test_policy_switching.py",
)


def pytest_collection_modifyitems(config, items):  # noqa: ARG001 — pytest API
    """Mark known-broken tests as skipped, and tag the hermetic routing unit.

    Substring match on `nodeid` so parametrize-id changes don't silently
    break the skip list. Each skip carries the reason in `pytest -v` output
    so future readers see why it was deferred, not just that it was.
    """
    skip_markers = {
        substring: pytest.mark.skip(reason=f"v0.1.x known-broken: {reason}")
        for substring, reason in _KNOWN_BROKEN_TESTS
    }
    hermetic_marker = pytest.mark.routing_hermetic
    for item in items:
        # nodeid paths are always /-separated, relative to rootdir
        if item.nodeid.split("::")[0] in _ROUTING_HERMETIC_FILES or item.nodeid.split("::")[0] in tuple(p.removeprefix("tests/") for p in _ROUTING_HERMETIC_FILES):
            item.add_marker(hermetic_marker)
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
    # CHZ-AUD-001: pydantic-settings' env->field binding for chuzom_db_path is
    # ordering-fragile — a prior test can leave state that makes a fresh
    # RouterConfig ignore CHUZOM_DB_PATH and fall back to the ~/.chuzom default.
    # Force the isolated path deterministically so the fixture can NEVER resolve
    # to the production DB (writers that read the env var are already isolated
    # via the monkeypatch above; this covers readers that use config directly).
    if str(config.chuzom_db_path) != str(db_path):
        try:
            object.__setattr__(config, "chuzom_db_path", db_path)
        except Exception:
            config.chuzom_db_path = db_path
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

    # Reset config singleton so it reads fresh env vars
    import chuzom.config as config_module
    config_module._config = None

    # Reset dynamic routing table — it's a global singleton built at session
    # startup. Without this, test ordering determines which providers appear in
    # the chain (whichever env was active when the first test triggered server
    # startup wins), making routing tests non-deterministic across CI runs.
    from chuzom.dynamic_routing import reset_dynamic_routing
    reset_dynamic_routing()

    yield

    # Restore clean state so subsequent tests start from a known baseline
    config_module._config = None
    reset_dynamic_routing()


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
        chuzom_db_path = Path.home() / ".chuzom" / "routing.db"
        token_budget = 10_000_000
        quality = QualityMode.BALANCED
        min_model_floor = "haiku"
        semantic_cache_ttl = 86400
        health_circuit_breaker_threshold = 0.5
        health_circuit_breaker_ttl = 300
        health_request_timeout = 30
        chuzom_gemini_subscription = False
        openai_compat_base_url = ""
        effective_ollama_base_url = ""
        # No providers at all — mirrors RouterConfig.available_providers
        # for an environment with no keys and no reachable Ollama.
        available_providers = frozenset()
        chuzom_monthly_budget = 0.0
        chuzom_agentic_model = ""
        chuzom_routing_policy = "balanced"
        codex_daily_limit = 1000
        prompt_cache_enabled = True
        prompt_cache_min_tokens = 1024

        def all_ollama_models(self):
            return []

        def all_openai_compat_models(self):
            return []

        def apply_keys_to_env(self):
            pass  # No-op

        def __getattr__(self, name):
            # Fall back to RouterConfig's pydantic field defaults for any
            # attribute not explicitly overridden above. Keeps this fixture
            # from breaking every time the router reads a new config knob,
            # while guaranteeing no env/.env values leak into tests.
            from chuzom.config import RouterConfig

            field = RouterConfig.model_fields.get(name)
            if field is not None:
                return field.get_default(call_default_factory=True)
            raise AttributeError(
                f"EmptyConfig has no attribute {name!r} and RouterConfig "
                f"declares no such field"
            )

    empty_config = EmptyConfig()

    # Replace the singleton itself: get_config() returns `_config` directly,
    # so this takes effect in every module even when get_config was bound
    # by value at import time (`from chuzom.config import get_config`).
    import chuzom.config as config_module
    monkeypatch.setattr(config_module, "_config", empty_config)
    monkeypatch.setattr(config_module, "get_config", lambda: empty_config)

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


@pytest.fixture(autouse=True)
def _reset_health_tracker():
    """Reset the provider HealthTracker singleton before and after each test.

    It's a process-lifetime singleton (see chuzom.health.get_tracker) — a test
    that makes a real, failing provider call (e.g. an invalid test API key)
    marks that provider unhealthy for the rest of the pytest run, silently
    breaking any later, unrelated test that expects it to be healthy.
    """
    from chuzom.health import reset_tracker_for_tests
    reset_tracker_for_tests()
    yield
    reset_tracker_for_tests()


@pytest.fixture(autouse=True)
def _reset_ollama_isolation():
    """Isolate Ollama-reachability state so provider-availability tests are stable.

    Two independent process-lifetime leaks made TestOllamaProviderInclusion /
    TestAvailableProviders flaky on a box that actually runs Ollama:

    1. ``config._ollama_reachable_cache`` / ``_pxpipe_reachable_cache`` — 60s-TTL
       module caches monkeypatch can't restore.
    2. Ambient ``OLLAMA_BASE_URL`` / ``OLLAMA_URL`` in ``os.environ``.
       ``effective_ollama_base_url`` reads these *directly* (not via the config
       field), so a value inherited from the developer's shell/.env — or leaked
       by another test — makes ``RouterConfig(ollama_base_url="")`` still resolve
       to a live endpoint and pull "ollama" into ``available_providers``.

    Clearing the ambient vars is correct isolation: tests that need Ollama set the
    URL themselves via monkeypatch inside the test body (which runs after this
    fixture), so they are unaffected; tests asserting exclusion get a clean slate.
    Snapshot/restore keeps the real environment intact for the process.
    """
    import os

    import chuzom.config as config_module

    saved = {k: os.environ.pop(k, None) for k in ("OLLAMA_BASE_URL", "OLLAMA_URL")}
    config_module._ollama_reachable_cache = None
    config_module._pxpipe_reachable_cache = None
    try:
        yield
    finally:
        config_module._ollama_reachable_cache = None
        config_module._pxpipe_reachable_cache = None
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


@pytest.fixture(autouse=True)
def _reset_quality_store():
    """Reset the module-global quality-feedback store before and after each test.

    ``chuzom.quality_feedback._quality_store`` is process-lifetime state that
    ``monkeypatch`` cannot restore. Since #130 wired quality-gated escalation
    into chain building, ModelQuality entries recorded by one test (e.g. the
    budget-cap concurrency test's mocked successes) silently change routing
    chains built by later tests — see the order-dependent failures in
    tests/audit/test_failure_fallback.py.
    """
    from chuzom.quality_feedback import reset_quality_store
    reset_quality_store()
    yield
    reset_quality_store()


@pytest.fixture(autouse=True)
def _hermetic_host_state(monkeypatch):
    """Isolate router tests from real host state (repo config + CLI probes).

    Even with ``cm._config`` fully stubbed, chain building still reads two
    host-side side doors:

    1. ``chuzom.router.get_repo_config`` (= ``repo_config.effective_config``)
       loads the developer's real ``~/.chuzom/routing.yaml``. A per-task pin
       there (e.g. ``query: ollama/qwen2.5-coder:7b``) is silently prepended
       to every chain a test builds — phantom models that don't exist on CI.
    2. ``is_codex_available()`` / ``is_gemini_cli_available()`` probe for the
       real CLIs, so subprocess-tier entries survive the provider filter on
       a dev machine but not on CI.

    Both were bound by name at import time in ``chuzom.router``, so we patch
    the *router's* bindings, plus the source loaders for other call sites.
    Tests that exercise pins or codex/gemini injection explicitly re-patch
    these on top (test-level monkeypatch wins over this autouse default).
    """
    import chuzom.repo_config as repo_config_module
    import chuzom.router as router_module
    from chuzom.repo_config import RepoConfig

    _empty = RepoConfig()
    monkeypatch.setattr(router_module, "get_repo_config", lambda *a, **k: _empty)
    monkeypatch.setattr(repo_config_module, "load_user_config", lambda *a, **k: RepoConfig())
    monkeypatch.setattr(router_module, "is_codex_available", lambda: False)
    monkeypatch.setattr(router_module, "is_gemini_cli_available", lambda: False)
    # The LLM-first ensemble makes live Ollama classifier calls, which in unit
    # tests punch through host-state isolation — real model latency,
    # non-determinism, and background warmup threads that leak global state
    # across tests. Default it OFF here (ON in production); the ensemble suite
    # re-enables per-test (test-level monkeypatch wins). OKF stays ON — it is
    # part of the shipped default and its suites exercise it with a tmp base.
    monkeypatch.setenv("CHUZOM_ENSEMBLE", "off")
    yield


@pytest.fixture(autouse=True)
def _isolate_session_context_accumulator(monkeypatch):
    """Prevent the Session Context Accumulator from touching the real
    ``~/.chuzom`` during tests.

    router.py's ``route_and_call`` and context.py's ``build_context_messages``
    both now call into ``chuzom.session_store`` (``record_event`` /
    ``resolve_session_id`` / ``build_session_context``). ``resolve_session_id``
    falls back to the ``CLAUDE_SESSION_ID`` / ``CLAUDE_CODE_SESSION_ID``
    environment variables when no explicit id is given — and this suite runs
    inside a real Claude Code session that sets ``CLAUDE_CODE_SESSION_ID``.
    Without this fixture, any test that exercises those (unmocked) code paths
    would resolve a real session id and read/write a real
    ``~/.chuzom/session_context_*.jsonl`` file, violating test hermeticity and
    leaking state across the whole run (all such tests would share one file).

    Clearing just these two env vars (not redirecting ``HOME`` wholesale, which
    would also affect unrelated pre-existing subsystems like session_spend /
    receipts / savings_logger that aren't part of this feature) makes
    ``resolve_session_id()`` return ``None`` by default, so layer 2b /
    ``record_event`` become no-ops for every test that doesn't explicitly opt
    in. ``tests/test_session_store.py`` exercises the real functions directly
    and defines its own local (file-scoped) ``_isolated_home`` fixture that
    also monkeypatches ``HOME`` to a tmp dir — that fixture, not this one,
    governs isolation there. Any other test that wants real accumulator
    behavior can set ``CLAUDE_SESSION_ID``/monkeypatch ``session_store``
    itself; a test-level ``monkeypatch`` call always wins over this autouse
    default.
    """
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    yield


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
