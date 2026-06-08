"""Tests for MCP server tool registration and basic functionality."""


import pytest

from chuzom.server import mcp


def test_all_tools_registered():
    """Verify all tools are registered dynamically from modules.
    
    This test prevents tool registration drift by dynamically discovering
    all @mcp.tool() decorated functions rather than hardcoding names.
    """
    from chuzom.tools import routing, text, media, pipeline, admin, subscription, codex, gemini_cli, setup, agoragentic

    # Get all tools from the MCP server
    registered_tools = mcp._tool_manager.list_tools()
    registered_names = {t.name for t in registered_tools}

    # Dynamically collect expected tools from all modules
    tool_modules = [routing, text, media, pipeline, admin, subscription, codex, gemini_cli, setup, agoragentic]
    expected_names = set()
    
    for module in tool_modules:
        # Scan module for functions with __wrapped__ (indicates @mcp.tool decorator)
        for name in dir(module):
            obj = getattr(module, name)
            if callable(obj) and hasattr(obj, '__wrapped__'):
                # This is likely an MCP tool
                expected_names.add(name)
    
    # Also add known tools that might not be easily discoverable
    known_tools = {
        "llm_classify", "llm_track_usage", "llm_route", "llm_auto", "llm_stream", "llm_select_agent",
        "llm_query", "llm_research", "llm_generate", "llm_analyze", "llm_code",
        "llm_image", "llm_video", "llm_audio",
        "llm_orchestrate", "llm_pipeline_templates",
        "llm_save_session", "llm_gain",
        "llm_set_profile", "llm_usage", "llm_savings", "llm_health", "llm_hook_health", "llm_providers",
        "llm_check_usage", "llm_update_usage", "llm_refresh_claude_usage",
        "llm_codex", "llm_gemini", "llm_setup", "llm_cache_stats", "llm_cache_clear",
        "llm_quality_report", "llm_quality_guard",
        "llm_edit", "llm_rate", "llm_dashboard",
        "llm_fs_find", "llm_fs_rename", "llm_fs_edit_many", "llm_fs_analyze_context",
        "llm_team_report", "llm_team_push",
        "llm_policy", "llm_digest", "llm_benchmark",
        "llm_reroute", "llm_session_spend", "llm_session_savings", "llm_approve_route",
        "llm_budget", "llm_quota_status", "llm_share_profile", "llm_import_profile",
        "llm_model_eval", "llm_model_usage", "llm_model_export", "llm_savings_dashboard",
        "agoragentic_task", "agoragentic_browse", "agoragentic_wallet", "agoragentic_status",
        # v0.0.2 agent-session MCP tools — registered by tools/agents.py
        "chuzom_agent_list", "chuzom_agent_start_session",
        "chuzom_agent_check_budget", "chuzom_agent_route",
        "chuzom_agent_complete_session", "chuzom_agent_lineage",
    }
    
    # SEC-002: llm_fs_* tools are opt-in via CHUZOM_FS_TOOLS=on and won't be
    # registered without it; exclude them from the must-be-present set when the
    # opt-in is absent.
    import os as _os
    fs_opt_in = _os.environ.get("CHUZOM_FS_TOOLS", "").strip().lower() in {"1", "on", "true", "yes"}
    if not fs_opt_in:
        known_tools = known_tools - {
            "llm_fs_find", "llm_fs_rename", "llm_fs_edit_many", "llm_fs_analyze_context",
        }

    # With slim=routing (default), only routing-tier tools are registered.
    # Check that registered tools are a known subset, not that ALL tools are present.
    from chuzom.config import get_config
    slim = get_config().chuzom_slim
    if slim == "off":
        assert known_tools.issubset(registered_names), f"Missing tools: {known_tools - registered_names}"
    else:
        # In slim mode, registered tools should be a subset of known tools
        assert registered_names.issubset(known_tools | expected_names), \
            f"Unexpected tools: {registered_names - (known_tools | expected_names)}"
        # At minimum, core routing tools must be present
        core_tools = {"llm_query", "llm_code", "llm_research", "llm_usage"}
        assert core_tools.issubset(registered_names), f"Missing core tools: {core_tools - registered_names}"


def test_resource_registered():
    # FastMCP should have our status resource
    resources = mcp._resource_manager.list_resources()
    uris = [str(r.uri) for r in resources]
    assert any("status" in u for u in uris)


class TestSetProfile:
    @pytest.mark.asyncio
    async def test_valid_profile(self, mock_env):
        from chuzom.server import llm_set_profile
        result = await llm_set_profile("budget")
        assert "budget" in result

    @pytest.mark.asyncio
    async def test_invalid_profile(self, mock_env):
        from chuzom.server import llm_set_profile
        result = await llm_set_profile("invalid")
        assert "Invalid" in result


class TestUsage:
    @pytest.mark.asyncio
    async def test_usage_no_data(self, mock_env, tmp_path, monkeypatch):
        monkeypatch.setenv("CHUZOM_DB_PATH", str(tmp_path / "test.db"))
        from chuzom.server import llm_usage
        result = await llm_usage("all")
        assert "Usage Dashboard" in result


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_shows_providers(self, mock_env):
        from chuzom.server import llm_health
        result = await llm_health()
        assert "Provider Health" in result
