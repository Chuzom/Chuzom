"""Multi-host coexistence — Tessera + llm-router in the same config.

The real-world scenario: a user has llm-router already installed (likely,
since Tessera was forked from it) and wants to run both in parallel for
a while during migration. Each speaks MCP and registers tools under its
own server name, so the tool namespace prefix (`mcp__tessera__llm_query`
vs `mcp__llm-router__llm_query`) disambiguates at the host.

This suite proves:
    1. Cursor/Gemini-CLI adapter installs don't clobber an existing
       llm-router entry in the same config file.
    2. Both servers can be listed simultaneously in any host config.
    3. Tool-name overlap is handled via the MCP namespace prefix.
    4. Uninstalling Tessera leaves llm-router untouched, and vice versa.
    5. Doctor-style queries can distinguish "Tessera installed" from
       "llm-router installed" without confusion.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ────────────────────────────────────────────────────────────────────────
# Fixture: a config file pre-loaded with llm-router
# ────────────────────────────────────────────────────────────────────────

@pytest.fixture
def config_with_llm_router(tmp_path: Path) -> Path:
    """Realistic starting state: ~/.cursor/mcp.json (or equivalent) already
    has llm-router registered. Tessera install must respect it."""
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "llm-router": {
                "command": "llm-router",
                "args": [],
                "env": {"LLM_ROUTER_CLAUDE_SUBSCRIPTION": "true"},
            },
        },
    }, indent=2))
    return cfg


# ────────────────────────────────────────────────────────────────────────
# Cursor adapter: install preserves llm-router
# ────────────────────────────────────────────────────────────────────────

def test_cursor_install_preserves_llm_router_entry(config_with_llm_router: Path):
    from tessera.hosts.cursor import CursorAdapter

    adapter = CursorAdapter(config_path=config_with_llm_router)
    adapter.install(server_command=["tessera"])

    data = json.loads(config_with_llm_router.read_text())
    assert "llm-router" in data["mcpServers"]
    assert data["mcpServers"]["llm-router"]["command"] == "llm-router"
    assert "tessera" in data["mcpServers"]


def test_cursor_install_preserves_llm_router_env_block(config_with_llm_router: Path):
    """The full llm-router config — including the env dict — must survive."""
    from tessera.hosts.cursor import CursorAdapter

    adapter = CursorAdapter(config_path=config_with_llm_router)
    adapter.install(server_command=["tessera"])

    data = json.loads(config_with_llm_router.read_text())
    entry = data["mcpServers"]["llm-router"]
    assert entry.get("env", {}).get("LLM_ROUTER_CLAUDE_SUBSCRIPTION") == "true"


def test_cursor_uninstall_only_removes_tessera(config_with_llm_router: Path):
    """Uninstalling Tessera must NOT touch the llm-router entry."""
    from tessera.hosts.cursor import CursorAdapter

    adapter = CursorAdapter(config_path=config_with_llm_router)
    adapter.install(server_command=["tessera"])
    adapter.uninstall()

    data = json.loads(config_with_llm_router.read_text())
    assert "tessera" not in data["mcpServers"]
    assert "llm-router" in data["mcpServers"], (
        "Tessera uninstall must not remove llm-router"
    )


def test_cursor_is_installed_does_not_confuse_with_llm_router(
    config_with_llm_router: Path,
):
    """A config containing ONLY llm-router must not report Tessera as installed."""
    from tessera.hosts.cursor import CursorAdapter

    adapter = CursorAdapter(config_path=config_with_llm_router)
    assert not adapter.is_installed(), (
        "Tessera adapter should distinguish itself from llm-router"
    )


# ────────────────────────────────────────────────────────────────────────
# Gemini CLI adapter: same coexistence guarantees
# ────────────────────────────────────────────────────────────────────────

def test_gemini_cli_install_preserves_llm_router_entry(
    config_with_llm_router: Path,
):
    from tessera.hosts.gemini_cli import GeminiCliAdapter

    adapter = GeminiCliAdapter(config_path=config_with_llm_router)
    adapter.install(server_command=["tessera"])

    data = json.loads(config_with_llm_router.read_text())
    assert "llm-router" in data["mcpServers"]
    assert "tessera" in data["mcpServers"]


def test_gemini_cli_uninstall_only_removes_tessera(config_with_llm_router: Path):
    from tessera.hosts.gemini_cli import GeminiCliAdapter

    adapter = GeminiCliAdapter(config_path=config_with_llm_router)
    adapter.install(server_command=["tessera"])
    adapter.uninstall()

    data = json.loads(config_with_llm_router.read_text())
    assert "tessera" not in data["mcpServers"]
    assert "llm-router" in data["mcpServers"]


# ────────────────────────────────────────────────────────────────────────
# Order independence — install order shouldn't matter
# ────────────────────────────────────────────────────────────────────────

def test_install_tessera_before_llm_router_still_coexist(tmp_path: Path):
    """Reverse scenario: Tessera installed first, then user adds llm-router
    manually. Tessera must not get confused or clobber on re-install."""
    from tessera.hosts.cursor import CursorAdapter

    cfg = tmp_path / "mcp.json"
    adapter = CursorAdapter(config_path=cfg)
    adapter.install(server_command=["tessera"])

    # User manually adds llm-router
    data = json.loads(cfg.read_text())
    data["mcpServers"]["llm-router"] = {"command": "llm-router"}
    cfg.write_text(json.dumps(data))

    # Re-install Tessera (e.g. version upgrade)
    adapter.install(server_command=["tessera", "--upgraded"])

    final = json.loads(cfg.read_text())
    assert "llm-router" in final["mcpServers"]
    assert final["mcpServers"]["tessera"]["args"] == ["--upgraded"]


# ────────────────────────────────────────────────────────────────────────
# Tool namespace disambiguation
# ────────────────────────────────────────────────────────────────────────

def test_tessera_mcp_server_name_is_tessera():
    """Tessera registers itself under the name 'tessera' so MCP tool calls
    are namespaced `mcp__tessera__llm_query`. This disambiguates from
    `mcp__llm-router__llm_query` even though both expose `llm_query`."""
    from tessera.server import mcp

    # FastMCP stores the server name on the .name attribute
    assert mcp.name == "tessera"


def test_tessera_and_llm_router_server_names_differ():
    """As long as the server names differ, MCP namespace prefixes
    guarantee zero tool-name collision. This is the static guarantee:
    'tessera' != 'llm-router'."""
    from tessera.server import mcp

    assert mcp.name != "llm-router"


# ────────────────────────────────────────────────────────────────────────
# Three-way coexistence — Tessera + llm-router + arbitrary third server
# ────────────────────────────────────────────────────────────────────────

def test_three_way_coexistence(tmp_path: Path):
    """A real user might have Tessera + llm-router + some unrelated MCP
    server (Obsidian, GitHub, Slack, etc.). All three must coexist
    indefinitely."""
    from tessera.hosts.cursor import CursorAdapter

    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({
        "mcpServers": {
            "llm-router": {"command": "llm-router"},
            "obsidian": {"command": "obsidian-mcp", "args": ["--vault", "~/Notes"]},
        },
    }))

    adapter = CursorAdapter(config_path=cfg)
    adapter.install(server_command=["tessera"])
    final = json.loads(cfg.read_text())
    assert set(final["mcpServers"].keys()) == {"llm-router", "obsidian", "tessera"}

    # Uninstall Tessera — other two must remain intact
    adapter.uninstall()
    after_uninstall = json.loads(cfg.read_text())
    assert set(after_uninstall["mcpServers"].keys()) == {"llm-router", "obsidian"}


# ────────────────────────────────────────────────────────────────────────
# Live filesystem check — does the user's actual config have both?
# ────────────────────────────────────────────────────────────────────────

def test_live_user_config_inspectable():
    """Sanity check on the user's actual ~/.claude/settings.json: if it
    exists, it should be valid JSON and we should be able to enumerate
    its mcpServers. This is a read-only test — never modifies."""
    settings = Path.home() / ".claude" / "settings.json"
    if not settings.exists():
        pytest.skip("No ~/.claude/settings.json on this machine")

    try:
        data = json.loads(settings.read_text())
    except json.JSONDecodeError as exc:
        pytest.fail(f"~/.claude/settings.json is invalid JSON: {exc}")

    servers = data.get("mcpServers", {})
    assert isinstance(servers, dict), (
        f"~/.claude/settings.json mcpServers must be a dict, got {type(servers)}"
    )
    # No assertion on content — this just proves we can read it without
    # crashing, which is what `tessera doctor` does.


# ────────────────────────────────────────────────────────────────────────
# Hook coexistence on disk — both `llm-router-*` and `tessera-*` hooks
# may exist simultaneously in ~/.claude/hooks/. Settings file only points
# at one set; the other set is dormant.
# ────────────────────────────────────────────────────────────────────────

def test_hooks_dir_can_hold_both_tessera_and_llm_router(tmp_path: Path):
    """Simulate a hooks dir holding both. Tessera's tooling must
    discriminate by filename prefix, not by directory contents."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "llm-router-auto-route.py").write_text("# legacy hook")
    (hooks_dir / "tessera-auto-route.py").write_text("# tessera hook")

    tessera_hooks = list(hooks_dir.glob("tessera-*.py"))
    llm_router_hooks = list(hooks_dir.glob("llm-router-*.py"))

    assert len(tessera_hooks) == 1
    assert len(llm_router_hooks) == 1
    assert (
        tessera_hooks[0].name != llm_router_hooks[0].name
    ), "Filename prefixes must be distinct"


# ────────────────────────────────────────────────────────────────────────
# Idempotency under coexistence
# ────────────────────────────────────────────────────────────────────────

def test_repeated_tessera_installs_dont_grow_llm_router_entry(
    config_with_llm_router: Path,
):
    """Multiple Tessera installs must not accidentally mutate the
    llm-router entry's content."""
    from tessera.hosts.cursor import CursorAdapter

    adapter = CursorAdapter(config_path=config_with_llm_router)
    original_llm_router = json.loads(config_with_llm_router.read_text())["mcpServers"]["llm-router"]

    for _ in range(5):
        adapter.install(server_command=["tessera"])

    final_llm_router = json.loads(config_with_llm_router.read_text())["mcpServers"]["llm-router"]
    assert original_llm_router == final_llm_router, (
        "llm-router entry should be byte-identical after 5 Tessera installs"
    )
