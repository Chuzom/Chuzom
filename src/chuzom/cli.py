"""CLI entry point for chuzom.

Usage:
    chuzom                  — start the MCP server (stdio transport)
    chuzom install              — install hooks, rules, and MCP server config globally
    chuzom install --check      — show what would be installed without doing it
    chuzom install --force      — reinstall even if already present
    chuzom install --claw-code  — also install into claw-code (auto-detects ~/.claw-code/)
    chuzom install --headless   — install for Docker/agent/CI environments (API-key mode, no OAuth)
    chuzom install --host codex       — write Codex CLI config files
    chuzom install --host opencode    — write OpenCode config files
    chuzom install --host gemini-cli  — write Gemini CLI config files
    chuzom install --host copilot-cli — write GitHub Copilot CLI config files
    chuzom install --host openclaw    — write OpenClaw config files
    chuzom install --host trae        — write Trae IDE config files
    chuzom install --host pi          — write Pi coding agent (pi.dev) config files
    chuzom install --host factory     — confirm Factory Droid plugin manifest
    chuzom install --host desktop     — print Claude Desktop config snippet
    chuzom install --host copilot     — print VS Code / Copilot config snippet
    chuzom install --host all         — install / print all host configs
    chuzom uninstall        — remove hooks and MCP registration
    chuzom uninstall --purge — also delete ~/.chuzom/ (usage DB, .env, logs)
    chuzom setup            — interactive wizard: configure providers and API keys
    chuzom init-policy      — interactive wizard: choose or create a routing policy (v7.5.0)
    chuzom status           — show routing status, today's savings, subscription pressure
    chuzom savings-report   — detailed token/cost breakdown (all-time, by model/provider)
    chuzom savings-report --period week  — weekly savings report
    chuzom doctor           — check that everything is wired up correctly
    chuzom demo             — show routing decisions for sample prompts
    chuzom dashboard        — start the web dashboard at localhost:7337
    chuzom dashboard --port 7338  — use a custom port
    chuzom set-enforce <mode>  — switch enforcement mode (smart|soft|hard|off)
    chuzom team report [period]  — show team savings report (default: week)
    chuzom team push [period]    — push report to Slack/Discord/Telegram/webhook
    chuzom team setup            — interactively configure team endpoint
    chuzom budget                — show all providers with spend, cap, pressure
    chuzom budget set <p> <amt>  — set monthly cap in USD for provider p
    chuzom budget remove <p>     — clear the cap for provider p
    chuzom last [--count N]      — show your last N routing decisions (default: 5)
    chuzom replay [--limit N]    — full transcript of routing decisions this session
    chuzom snapshot [--date DATE] — mid-session monitoring: accuracy trends and gap detection
    chuzom retrospect [--weekly] — IAF-style session debrief with routing directives
    chuzom stats [--period recent] — show combined download stats (llm-routing + claude-code-chuzom)
    chuzom verify                — end-to-end health check (30 seconds)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


# ── Helper functions: JSON MCP config management ────────────────────────────────


def _write_json_idempotent(file_path: Path | str, data: dict) -> str:
    """Write JSON file idempotently, returning action message."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if file exists with same content
    if file_path.exists():
        existing = json.loads(file_path.read_text())
        if existing == data:
            return f"skipped: {file_path.name} already has current content"

    file_path.write_text(json.dumps(data, indent=2))
    return f"Created: {file_path}"


def _merge_json_mcp_block(
    config_path: Path | str,
    server_name: str,
    config_dict: dict,
    root_key: str = "mcpServers",
) -> list[str]:
    """Merge MCP server config into JSON file, idempotently.

    Args:
        config_path: Path to JSON config file
        server_name: Name of MCP server (e.g., "chuzom")
        config_dict: Server config dict (e.g., {"command": "chuzom"})
        root_key: Root key for servers (default "mcpServers", VS Code uses "servers")

    Returns:
        List of action strings describing what was done
    """
    config_path = Path(config_path)
    actions = []

    # Create parent directories if needed
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config or create new
    if config_path.exists():
        data = json.loads(config_path.read_text())
    else:
        data = {}

    # Ensure root_key exists
    if root_key not in data:
        data[root_key] = {}

    # Check if already present (idempotency)
    if server_name in data[root_key]:
        if data[root_key][server_name] == config_dict:
            actions.append(f"skipped: {server_name} already configured in {config_path.name}")
            config_path.write_text(json.dumps(data, indent=2))
            return actions

    # Add/update server config
    data[root_key][server_name] = config_dict
    config_path.write_text(json.dumps(data, indent=2))
    actions.append(f"Added: {server_name} to {config_path}")

    return actions


def _append_routing_rules(
    dest_path: Path | str,
    rules_filename: str,
) -> list[str]:
    """Append routing rules from template file, idempotently.

    Args:
        dest_path: Destination file path
        rules_filename: Name of rules file in src/chuzom/rules/ (e.g., "vscode-rules.md")

    Returns:
        List of action strings describing what was done
    """
    dest_path = Path(dest_path)
    actions = []

    # Load template rules
    rules_dir = Path(__file__).parent / "rules"
    rules_file = rules_dir / rules_filename

    if not rules_file.exists():
        actions.append(f"warning: {rules_filename} not found in {rules_dir}")
        return actions

    rules_content = rules_file.read_text()

    # Create parent directories if needed
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if already present (idempotency)
    if dest_path.exists():
        existing = dest_path.read_text()
        if "chuzom" in existing:
            actions.append(f"skipped: {dest_path.name} already contains chuzom rules")
            return actions
        # Append to existing file
        with open(dest_path, "a") as f:
            f.write("\n\n" + rules_content)
        actions.append(f"Appended: routing rules to {dest_path}")
    else:
        # Create new file
        dest_path.write_text(rules_content)
        actions.append(f"Created: {dest_path} with routing rules")

    return actions


# ── Platform-specific install functions ────────────────────────────────────────


def _install_vscode_files() -> list[str]:
    """Install chuzom MCP config for VS Code."""
    actions = []
    home = Path.home()

    # VS Code mcp.json location (platform-specific)
    if sys.platform == "darwin":
        mcp_json = home / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
    elif sys.platform == "win32":
        mcp_json = home / "AppData" / "Roaming" / "Code" / "User" / "mcp.json"
    else:
        mcp_json = home / ".config" / "Code" / "User" / "mcp.json"

    # VS Code uses "servers" key, not "mcpServers"
    actions.extend(
        _merge_json_mcp_block(
            mcp_json,
            "chuzom",
            {"command": "chuzom", "args": []},
            root_key="servers",
        )
    )

    # Add copilot-instructions.md if in current directory
    github_dir = Path.cwd() / ".github"
    if github_dir.exists():
        instructions = github_dir / "copilot-instructions.md"
        actions.extend(_append_routing_rules(instructions, "vscode-rules.md"))

    return actions


def _install_cursor_files() -> list[str]:
    """Install chuzom MCP config for Cursor IDE."""
    actions = []
    home = Path.home()

    # Cursor mcp.json location
    mcp_json = home / ".cursor" / "mcp.json"
    actions.extend(
        _merge_json_mcp_block(
            mcp_json,
            "chuzom",
            {"command": "chuzom", "args": []},
            root_key="mcpServers",
        )
    )

    # Add cursor rules
    cursor_rules = home / ".cursor" / "rules" / "chuzom.md"
    actions.extend(_append_routing_rules(cursor_rules, "cursor-rules.md"))

    return actions


def _install_opencode_files() -> list[str]:
    """Install chuzom MCP config for OpenCode."""
    actions = []
    home = Path.home()

    # OpenCode config
    config = home / ".config" / "opencode" / "config.json"
    actions.extend(
        _merge_json_mcp_block(
            config,
            "chuzom",
            {"command": "chuzom", "args": []},
        )
    )

    # OpenCode instructions
    instructions = home / ".config" / "opencode" / "instructions.md"
    actions.extend(_append_routing_rules(instructions, "opencode-rules.md"))

    return actions


def _install_gemini_cli_files() -> list[str]:
    """Install chuzom MCP config for Gemini CLI."""
    actions = []
    home = Path.home()

    # Gemini settings.json
    settings = home / ".gemini" / "settings.json"
    actions.extend(
        _merge_json_mcp_block(
            settings,
            "chuzom",
            {"command": "chuzom", "args": []},
        )
    )

    # Gemini extension manifest
    ext_dir = home / ".gemini" / "extensions" / "chuzom"
    manifest = ext_dir / "gemini-extension.json"

    manifest_data = {
        "name": "chuzom",
        "version": "9.0.1",
        "description": "Multi-LLM routing MCP server",
    }
    actions.append(_write_json_idempotent(manifest, manifest_data))

    # Gemini hooks.json
    hooks_file = ext_dir / "hooks" / "hooks.json"

    hooks_data = {
        "hooks": {
            "PostToolUse": {
                "enabled": True,
            }
        }
    }
    actions.append(_write_json_idempotent(hooks_file, hooks_data))

    # Gemini instructions
    instructions = ext_dir / "INSTRUCTIONS.md"
    actions.extend(_append_routing_rules(instructions, "gemini-rules.md"))

    return actions


def _install_copilot_cli_files() -> list[str]:
    """Install chuzom MCP config for GitHub Copilot CLI."""
    actions = []
    home = Path.home()

    # Copilot mcp.json
    mcp_json = home / ".config" / "gh" / "copilot" / "mcp.json"
    actions.extend(
        _merge_json_mcp_block(
            mcp_json,
            "chuzom",
            {"command": "chuzom", "args": []},
        )
    )

    # Copilot instructions
    instructions = home / ".config" / "gh" / "copilot" / "instructions.md"
    actions.extend(_append_routing_rules(instructions, "copilot-rules.md"))

    return actions


def _install_openclaw_files() -> list[str]:
    """Install chuzom MCP config for OpenClaw."""
    actions = []
    home = Path.home()

    # OpenClaw mcp.json
    mcp_json = home / ".openclaw" / "mcp.json"
    actions.extend(
        _merge_json_mcp_block(
            mcp_json,
            "chuzom",
            {"command": "chuzom", "args": []},
        )
    )

    # OpenClaw instructions
    instructions = home / ".openclaw" / "instructions.md"
    actions.extend(_append_routing_rules(instructions, "openclaw-rules.md"))

    return actions


def _install_trae_files() -> list[str]:
    """Install chuzom MCP config for Trae IDE."""
    actions = []
    home = Path.home()

    # Trae mcp.json (location varies by Trae version, try common location)
    mcp_json = home / ".trae" / "mcp.json"
    actions.extend(
        _merge_json_mcp_block(
            mcp_json,
            "chuzom",
            {"command": "chuzom", "args": []},
        )
    )

    return actions


def _install_pi_files() -> list[str]:
    """Install chuzom MCP config for Pi coding agent (pi.dev)."""
    actions = []
    home = Path.home()

    # Pi agent MCP config: ~/.pi/agent/mcp.json
    mcp_json = home / ".pi" / "agent" / "mcp.json"
    actions.extend(
        _merge_json_mcp_block(
            mcp_json,
            "chuzom",
            {
                "command": "chuzom",
                "args": [],
                "lifecycle": "lazy",
            },
        )
    )

    # Pi agent instructions
    instructions = home / ".pi" / "agent" / "INSTRUCTIONS.md"
    actions.extend(_append_routing_rules(instructions, "pi-rules.md"))

    return actions


def _install_codex_cli_files() -> list[str]:
    """Install chuzom MCP config for Codex CLI."""
    actions = []
    home = Path.home()

    # Codex CLI config location
    config_json = home / ".codex" / "config.json"
    actions.extend(
        _merge_json_mcp_block(
            config_json,
            "chuzom",
            {"command": "chuzom", "args": []},
        )
    )

    # Add Codex rules
    rules_file = home / ".codex" / "rules" / "chuzom.md"
    actions.extend(_append_routing_rules(rules_file, "codex-rules.md"))

    return actions


def _print_claude_desktop_config() -> list[str]:
    """Print Claude Desktop config snippet."""
    config = {
        "mcpServers": {
            "chuzom": {
                "command": "chuzom",
                "args": []
            }
        }
    }
    print("Add this to your claude_desktop_config.json:")
    print(json.dumps(config, indent=2))
    return ["Config snippet for claude_desktop_config.json"]


def _print_vs_code_copilot_config() -> list[str]:
    """Print VS Code / Copilot config snippet."""
    config = {
        "servers": {
            "chuzom": {
                "command": "chuzom",
                "args": []
            }
        }
    }
    print("Add this to your VS Code mcp.json:")
    print(json.dumps(config, indent=2))
    return ["Config snippet for mcp.json"]


def _install_host(host: str) -> None:
    """Dispatch to appropriate install function based on host."""
    host = host.lower()

    if host in ("vscode", "vs-code"):
        actions = _install_vscode_files()
        print("VS Code configuration:")
        for action in actions:
            print(f"  {action}")
    elif host == "cursor":
        actions = _install_cursor_files()
        print("Cursor IDE configuration:")
        for action in actions:
            print(f"  {action}")
    elif host == "opencode":
        actions = _install_opencode_files()
        print("OpenCode configuration:")
        for action in actions:
            print(f"  {action}")
    elif host == "gemini-cli":
        actions = _install_gemini_cli_files()
        print("Gemini CLI configuration:")
        for action in actions:
            print(f"  {action}")
    elif host == "copilot-cli":
        actions = _install_copilot_cli_files()
        print("GitHub Copilot CLI configuration:")
        for action in actions:
            print(f"  {action}")
    elif host == "openclaw":
        actions = _install_openclaw_files()
        print("OpenClaw configuration:")
        for action in actions:
            print(f"  {action}")
    elif host == "trae":
        actions = _install_trae_files()
        print("Trae IDE configuration:")
        for action in actions:
            print(f"  {action}")
    elif host == "pi":
        actions = _install_pi_files()
        print("Pi coding agent (pi.dev) configuration:")
        for action in actions:
            print(f"  {action}")
    elif host == "codex":
        actions = _install_codex_cli_files()
        print("Codex CLI configuration:")
        for action in actions:
            print(f"  {action}")
    elif host == "desktop":
        print("Claude Desktop configuration:")
        actions = _print_claude_desktop_config()
        for action in actions:
            print(f"  {action}")
    elif host == "copilot":
        print("VS Code / Copilot configuration:")
        actions = _print_vs_code_copilot_config()
        for action in actions:
            print(f"  {action}")
    elif host == "all":
        for h in ["vscode", "cursor", "opencode", "gemini-cli", "copilot-cli", "openclaw", "trae", "pi", "codex", "desktop", "copilot"]:
            _install_host(h)
            print()
    else:
        print(f"Unknown host: {host}")


# ── Main dispatcher ────────────────────────────────────────────────────────────

def isolation_test_command() -> None:
    """Run the isolation test suite for router health verification.

    Validates: cache isolation, routing logic, dashboard accuracy, database persistence.
    """
    import subprocess
    from pathlib import Path

    # Try to find the bash script first (for repo installations)
    package_dir = Path(__file__).parent.parent.parent
    script_path = package_dir / "scripts" / "router_isolation_test.sh"

    if script_path.exists():
        # Run via bash script if available
        result = subprocess.run(
            ["bash", str(script_path)] + sys.argv[1:],
            cwd=Path.home() / ".chuzom"
        )
        sys.exit(result.returncode)

    # For tool installations, pytest may not have access to tests directory
    # Run a simple health check instead
    print("Running chuzom health check...")
    print()

    # Quick health checks without pytest
    try:
        from chuzom.commands.status import cmd_status
        print("✓ Status check:")
        cmd_status([])
        print()
        print("✅ Router health check passed!")
        print()
        print("For comprehensive isolation tests, run from the repository:")
        print("  cd /Users/yali.pollak/Projects/chuzom")
        print("  pytest tests/test_isolation_routing.py -v")
        sys.exit(0)
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        sys.exit(1)


def main() -> None:
    """Unified CLI: dispatches to MCP server or subcommands."""
    args = sys.argv[1:]

    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return

    if args and args[0] in ("-v", "--version"):
        from chuzom import __version__
        print(f"chuzom v{__version__}")
        return

    if args and args[0] == "install":
        from chuzom.commands.install import cmd_install
        cmd_install(args[1:])
    elif args and args[0] == "uninstall":
        from chuzom.commands.uninstall import cmd_uninstall
        cmd_uninstall(args[1:])
    elif args and args[0] == "update":
        from chuzom.commands.update import cmd_update
        cmd_update(args[1:])
    elif args and args[0] == "setup":
        from chuzom.commands.setup import cmd_setup
        cmd_setup(args[1:])
    elif args and args[0] == "status":
        from chuzom.commands.status import cmd_status
        cmd_status(args[1:])
    elif args and args[0] == "welcome":
        # Print the painterly Chuzom banner on demand. Use this from your
        # shell rc (e.g., `claude` wrapper function in ~/.zshrc) to put the
        # welcome in your terminal scrollback before Claude Code's TUI takes
        # over — Claude Code's SessionStart hooks cannot surface output to
        # the user's terminal directly.
        from chuzom.commands.welcome import cmd_welcome
        sys.exit(cmd_welcome(args[1:]))
    elif args and args[0] == "dev-refresh":
        # Full dev refresh: reinstall package, sync hooks, restart MCP
        # servers — all three layers that need updating after a source
        # edit. Wraps the three-step pipeline that historically caused
        # "I reinstalled but my change isn't live" confusion when any
        # one layer was skipped.
        from chuzom.commands.dev_refresh import cmd_dev_refresh
        sys.exit(cmd_dev_refresh(args[1:]))
    elif args and args[0] == "serve":
        # E3: run chuzom as a long-lived HTTP service (container / systemd
        # entrypoint). Default = secured SSE MCP server; --admin = admin API.
        from chuzom.commands.serve import cmd_serve
        sys.exit(cmd_serve(args[1:]))
    elif args and args[0] == "routing":
        from chuzom.commands.routing import cmd_routing
        cmd_routing(args[1:])
    elif args and args[0] == "profile":
        from chuzom.commands.profile import cmd_profile
        cmd_profile(args[1:])
    elif args and args[0] == "init-claude-memory":
        from chuzom.cli_init_memory import run_init_claude_memory
        run_init_claude_memory()
    elif args and args[0] == "doctor":
        from chuzom.commands.doctor import cmd_doctor
        cmd_doctor(args[1:])
    elif args and args[0] == "quickstart":
        from chuzom.quickstart import main as _qs_main
        _qs_main()
    elif args and args[0] == "demo":
        from chuzom.commands.demo import cmd_demo
        cmd_demo(args[1:])
    elif args and args[0] == "dashboard":
        from chuzom.commands.dashboard import cmd_dashboard
        cmd_dashboard(args[1:])
    elif args and args[0] == "summary":
        # Session Summary Dashboard — rich terminal overview.
        # Flags: --since-hours N, --limit N, --markdown, --watch,
        #        --watch-interval N (seconds, default 5)
        from chuzom.summary import cli_summary
        rest = args[1:]
        since = 24.0
        limit = 5000
        markdown = False
        watch = False
        watch_interval = 5.0
        i = 0
        while i < len(rest):
            tok = rest[i]
            if tok == "--since-hours" and i + 1 < len(rest):
                since = float(rest[i + 1])
                i += 2
                continue
            if tok == "--limit" and i + 1 < len(rest):
                limit = int(rest[i + 1])
                i += 2
                continue
            if tok == "--markdown":
                markdown = True
                i += 1
                continue
            if tok == "--watch":
                watch = True
                i += 1
                continue
            if tok == "--watch-interval" and i + 1 < len(rest):
                watch_interval = float(rest[i + 1])
                i += 2
                continue
            i += 1
        raise SystemExit(cli_summary(
            since_hours=since, limit=limit, markdown=markdown,
            watch=watch, watch_interval=watch_interval,
        ))
    elif args and args[0] == "tui":
        from chuzom.dashboard.tui import run as _tui_run
        _tui_run()
    elif args and args[0] == "share":
        from chuzom.commands.share import cmd_share
        cmd_share(args[1:])
    elif args and args[0] == "test":
        from chuzom.commands.test import cmd_test
        cmd_test(args[1:])
    elif args and args[0] == "onboard":
        from chuzom.commands.onboard import cmd_onboard
        cmd_onboard(args[1:])
    elif args and args[0] == "config":
        from chuzom.commands.config import cmd_config
        cmd_config(args[1:])
    elif args and args[0] == "init-policy":
        from chuzom.cli_init_policy import run_init_policy_wizard
        run_init_policy_wizard()
    elif args and args[0] == "set-enforce":
        from chuzom.commands.set_enforce import cmd_set_enforce
        cmd_set_enforce(args[1:])
    elif args and args[0] == "team":
        from chuzom.commands.team import cmd_team
        cmd_team(args[1:])
    elif args and args[0] == "budget":
        from chuzom.commands.budget import cmd_budget
        cmd_budget(args[1:])
    elif args and args[0] == "replay":
        from chuzom.commands.replay import main as _replay_main
        _replay_main(args[1:])
    elif args and args[0] == "verify":
        from chuzom.commands.verify import main as _verify_main
        _verify_main(args[1:])
    elif args and args[0] == "last":
        from chuzom.commands.last import main as _last_main
        _last_main(args[1:])
    elif args and args[0] == "retrospect":
        from chuzom.commands.retrospect import main as _retrospect_main
        _retrospect_main(args[1:])
    elif args and args[0] == "snapshot":
        from chuzom.commands.snapshot import main as _snapshot_main
        _snapshot_main(args[1:])
    elif args and args[0] == "stats":
        from chuzom.commands.stats import cmd_stats
        sys.exit(cmd_stats(args[1:]))
    elif args and args[0] == "savings-report":
        from chuzom.commands.savings_report import main as _savings_report_main
        sys.exit(_savings_report_main(args[1:]))
    elif args and args[0] == "benchmark":
        from chuzom.commands.benchmark import cmd_benchmark
        sys.exit(cmd_benchmark(args[1:]))
    elif args and args[0] == "test-delta":
        from chuzom.test_delta import main as _td_main
        sys.exit(_td_main(args[1:]))
    elif args and args[0] == "migrate":
        from chuzom.commands.migrate import main as _migrate_main
        sys.exit(_migrate_main(args[1:]))
    elif args and args[0] == "team-sync":
        from chuzom.commands.team_sync import main as _team_sync_main
        sys.exit(_team_sync_main(args[1:]))
    elif args and args[0] == "policy":
        from chuzom.commands.policy import cmd_policy
        sys.exit(cmd_policy(args[1:]))
    elif args and args[0] == "explain-dashboard":
        from chuzom.commands.explain_dashboard import cmd_explain_dashboard
        sys.exit(cmd_explain_dashboard(args[1:]))
    else:
        # Default: start the MCP server (original behavior)
        from chuzom.server import main as _mcp_main
        _mcp_main()


if __name__ == "__main__":
    main()
