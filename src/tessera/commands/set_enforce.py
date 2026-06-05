"""Set-enforce command — manage routing enforcement mode."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


# ── Constants ────────────────────────────────────────────────────────────────

_ENFORCE_MODES = ("smart", "soft", "hard", "off")

_ENFORCE_DESCRIPTIONS = {
    "smart": "Hard block for Q&A tasks (query/research/generate/analyze), soft for code. >80% routing compliance without blocking file editing.",
    "soft": "Route hints in context, never blocks. Lowest friction — routing is suggested but not enforced.",
    "hard": "All Bash/Edit/Write blocked until an llm_* tool is called. Maximum cost savings, highest friction.",
    "off": "Enforcement disabled. Routing hints appear but nothing is enforced.",
}


# ── Formatting utilities ────────────────────────────────────────────────────

def _color_enabled() -> bool:
    """Check if color output is enabled."""
    return sys.stdout.isatty() and not os.getenv("NO_COLOR")


def _bold(s: str) -> str:
    """Bold text."""
    return f"\033[1m{s}\033[0m" if _color_enabled() else s


def _green(s: str) -> str:
    """Green text."""
    return f"\033[32m{s}\033[0m" if _color_enabled() else s


def _yellow(s: str) -> str:
    """Yellow text."""
    return f"\033[33m{s}\033[0m" if _color_enabled() else s


def _dim(s: str) -> str:
    """Dim text."""
    return f"\033[2m{s}\033[0m" if _color_enabled() else s


# ── Set-enforce command ─────────────────────────────────────────────────────

def _run_set_enforce(mode: str) -> None:
    """Switch the enforcement mode and persist to ~/.tessera/routing.yaml."""
    if not mode or mode not in _ENFORCE_MODES:
        print(f"\n{_bold('Usage:')} tessera set-enforce <mode>\n")
        print("Available modes:\n")
        for m in _ENFORCE_MODES:
            marker = " (default)" if m == "smart" else ""
            print(f"  {_bold(m):<12}{marker}")
            print(f"  {_dim(_ENFORCE_DESCRIPTIONS[m])}")
            print()
        return

    routing_yaml = Path.home() / ".tessera" / "routing.yaml"
    routing_yaml.parent.mkdir(parents=True, exist_ok=True)

    if routing_yaml.exists():
        content = routing_yaml.read_text()
        # Update existing enforce line or add it
        if re.search(r"^enforce:", content, re.MULTILINE):
            content = re.sub(r"^enforce:.*$", f"enforce: {mode}", content, flags=re.MULTILINE)
        else:
            content = f"enforce: {mode}\n" + content
    else:
        content = f"enforce: {mode}\n"

    routing_yaml.write_text(content)

    # Also write to .env for hooks that read it
    env_path = Path.home() / ".tessera" / ".env"
    if env_path.exists():
        env_content = env_path.read_text()
        if "TESSERA_ENFORCE=" in env_content:
            env_content = re.sub(
                r"TESSERA_ENFORCE=\S*", f"TESSERA_ENFORCE={mode}", env_content
            )
        else:
            env_content += f"\nTESSERA_ENFORCE={mode}\n"
        env_path.write_text(env_content)
    else:
        env_path.write_text(f"TESSERA_ENFORCE={mode}\n")

    print(f"\n{_green('✓')} Enforcement mode set to {_bold(mode)}")
    print(f"  {_dim(_ENFORCE_DESCRIPTIONS[mode])}")
    print(f"\n  Written to: {routing_yaml}")
    print(f"  Written to: {env_path}")

    # Warn if shell env var will override the files we just wrote
    current_env = os.environ.get("TESSERA_ENFORCE", "")
    if current_env and current_env.lower() != mode:
        print(f"\n  {_bold('⚠ WARNING')}: TESSERA_ENFORCE={current_env} is set in your shell.")
        print(f"  This overrides routing.yaml. Run: {_bold('unset TESSERA_ENFORCE')}")
        print("  Or remove it from ~/.zshrc / ~/.bashrc")

    print(f"\n  {_dim('Restart Claude Code for the change to take effect.')}\n")


# ── Entry point ─────────────────────────────────────────────────────────────

def cmd_set_enforce(args: list[str]) -> int:
    """Execute: tessera set-enforce <mode>

    Switch the routing enforcement mode.
    """
    mode = args[0] if args else ""
    _run_set_enforce(mode)
    return 0
