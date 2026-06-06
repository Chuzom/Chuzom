"""Health check — verify every component is wired up correctly.

Comprehensive diagnostic tool to check hooks, MCP registration, API keys,
Ollama availability, and host-specific configurations.
"""

import json
import os
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

from chuzom.terminal_style import Color


# ── Formatting utilities ────────────────────────────────────────────────────

def _bold(text: str) -> str:
    """Bold text."""
    return f"\033[1m{text}\033[0m"


def _green(text: str) -> str:
    """Green text."""
    return Color.CONFIDENCE_GREEN(text)


def _red(text: str) -> str:
    """Red text."""
    return Color.WARNING_RED(text)


def _yellow(text: str) -> str:
    """Yellow text."""
    return f"\033[33m{text}\033[0m"


def _dim(text: str) -> str:
    """Dim text."""
    return f"\033[2m{text}\033[0m"


def _ok(text: str) -> str:
    """Formatted success message."""
    return f"  {_green('✓')} {text}"


def _fail(text: str, fix: Optional[str] = None) -> str:
    """Formatted failure message."""
    msg = f"  {_red('✗')} {text}"
    if fix:
        msg += f" (fix: {_dim(fix)})"
    return msg


def _warn(text: str) -> str:
    """Formatted warning message."""
    return f"  {_yellow('⚠')} {text}"


# ── Hook utilities ──────────────────────────────────────────────────────────

def _hook_version_num(path: Path) -> int:
    """Read the version number embedded in a hook file header."""
    _re = re.compile(r"#\s*chuzom-hook-version:\s*(\d+)")
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[:5]:
            m = _re.search(line)
            if m:
                return int(m.group(1))
    except OSError:
        pass
    return 0


# ── Doctor implementation ───────────────────────────────────────────────────

def _run_doctor_host(host: str) -> None:
    """Run host-specific installation checks for vscode, cursor, or claude."""
    valid_hosts = {"claude", "vscode", "cursor", "all"}
    if host not in valid_hosts:
        print(f"  Unknown host: {host}. Valid options: {', '.join(sorted(valid_hosts))}")
        return

    hosts_to_check = list({"claude", "vscode", "cursor"}) if host == "all" else [host]

    for h in hosts_to_check:
        print(f"\n{_bold(f'  Host: {h}')}")
        issues: list[str] = []

        if h == "claude":
            # Check hooks
            from chuzom.install_hooks import _HOOKS_DST, _HOOK_DEFS

            for _, dst_name, event, _ in _HOOK_DEFS:
                dst = _HOOKS_DST / dst_name
                if dst.exists():
                    print(_ok(f"{dst_name}  ({event})"))
                else:
                    print(
                        _fail(
                            f"{dst_name}  — not installed",
                            fix="chuzom install",
                        )
                    )
                    issues.append(f"Hook {dst_name} missing")

            # Check uvx
            if shutil.which("uvx"):
                print(_ok("uvx found in PATH"))
            else:
                print(_warn("uvx not in PATH — install via: pip install uv"))

        elif h == "vscode":
            if sys.platform == "darwin":
                mcp_json = (
                    Path.home()
                    / "Library"
                    / "Application Support"
                    / "Code"
                    / "User"
                    / "mcp.json"
                )
            elif sys.platform == "win32":
                mcp_json = (
                    Path(os.getenv("APPDATA", "")) / "Code" / "User" / "mcp.json"
                )
            else:
                mcp_json = (
                    Path.home() / ".config" / "Code" / "User" / "mcp.json"
                )

            if mcp_json.exists():
                try:
                    data = json.loads(mcp_json.read_text())
                    if "chuzom" in data.get("servers", {}):
                        print(_ok(f"chuzom registered in {mcp_json}"))
                    else:
                        print(
                            _fail(
                                f"chuzom not in servers ({mcp_json})",
                                fix="chuzom install --host vscode",
                            )
                        )
                        issues.append("chuzom not registered in VS Code mcp.json")
                except Exception as e:
                    print(_fail(f"could not parse {mcp_json}: {e}"))
            else:
                print(
                    _fail(
                        f"mcp.json not found at {mcp_json}",
                        fix="chuzom install --host vscode",
                    )
                )
                issues.append("VS Code mcp.json missing")

            if shutil.which("uvx"):
                print(_ok("uvx found in PATH"))
            else:
                print(
                    _warn(
                        "uvx not in PATH — required for VS Code MCP server"
                    )
                )

        elif h == "cursor":
            mcp_json = Path.home() / ".cursor" / "mcp.json"
            cursor_rules = Path.home() / ".cursor" / "rules" / "chuzom.md"

            if mcp_json.exists():
                try:
                    data = json.loads(mcp_json.read_text())
                    if "chuzom" in data.get("mcpServers", {}):
                        print(_ok(f"chuzom registered in {mcp_json}"))
                    else:
                        print(
                            _fail(
                                f"chuzom not in mcpServers ({mcp_json})",
                                fix="chuzom install --host cursor",
                            )
                        )
                        issues.append("chuzom not registered in Cursor mcp.json")
                except Exception as e:
                    print(_fail(f"could not parse {mcp_json}: {e}"))
            else:
                print(
                    _fail(
                        f"mcp.json not found at {mcp_json}",
                        fix="chuzom install --host cursor",
                    )
                )
                issues.append("Cursor mcp.json missing")

            if cursor_rules.exists():
                print(_ok(f"routing rules installed ({cursor_rules})"))
            else:
                print(_warn(f"routing rules not found at {cursor_rules}"))

        if not issues:
            print(_green(f"  ✓ {h} is correctly configured"))
        else:
            print(_red(f"  {len(issues)} issue(s) found for {h}"))


def _render_host_explainer() -> str:
    """Always-up-to-date explanation of why the host model (Claude Code,
    Cursor, Codex CLI, ...) runs on a frontier model like Opus 4.7 and
    not on a local one — and what that means for the savings Chuzom can
    deliver. Surfaced via ``chuzom doctor --explain-host`` so the
    answer lives next to the savings posture report.
    """
    return (
        f"\n{_bold('  Why is my host on Opus 4.7 / Sonnet 4.6 and not on a local model?')}\n\n"

        f"  {_bold('Short answer')}\n"
        "    The host (Claude Code, Cursor, Codex CLI) is the agent loop —\n"
        "    it reads tool results, decides the next action, generates code,\n"
        "    and drives the conversation. Chuzom routes the LLM *calls* the\n"
        "    host makes on your behalf (llm_query, llm_code, llm_research)\n"
        "    but it does not replace the host itself. The host model is\n"
        "    whatever Claude Code is configured to use; today that's Opus 4.7\n"
        "    (1M context) by default.\n\n"

        f"  {_bold('Why not just run the host on Ollama?')}\n"
        "    Three reasons in descending order of importance:\n\n"
        "      1. Agent-loop reasoning is the hardest LLM task. The host has\n"
        "         to hold the conversation, plan multi-step solutions, generate\n"
        "         working code, and recover from tool failures. Local models\n"
        "         (qwen3.5, llama-3) drop coherence after 2-3 turns of that\n"
        "         work — great at single-shot answers, not at multi-turn\n"
        "         orchestration.\n\n"
        "      2. Tool-call format conformance. The host must emit tool calls\n"
        "         in very specific JSON every time. Frontier models get this\n"
        "         right >99% of the time; mid-tier local models miss enough\n"
        "         that the agent stalls. Anthropic/OpenAI tune their models\n"
        "         specifically for this; local wrappers compound failure rate.\n\n"
        "      3. Claude Code's UX assumes Opus-class reasoning. Plan mode,\n"
        "         the 1M context window, the way it handles ambiguity — all\n"
        "         designed around Opus capabilities. Swapping the model would\n"
        "         degrade UX in subtle, hard-to-debug ways.\n\n"

        f"  {_bold('What Chuzom CAN save')}\n"
        "      * Cost of LLM calls the host makes (llm_query → Haiku/Flash\n"
        "        instead of Opus). Visible in routing_decisions.\n"
        "      * Tokens the host has to *process* (response_router compresses\n"
        "        explanations in MCP responses before Claude reads them).\n"
        "      * Wasted tool-call cycles (sidecar pre-executes deterministic\n"
        "        prompts like 'show me my routing today').\n"
        "      * Quota burned classifying conversational follow-ups\n"
        "        (continuation bypass + short-followup pattern).\n\n"

        f"  {_bold('What Chuzom CANT save')}\n"
        "      * The host model's own reasoning between tool calls. That's\n"
        "        Opus time, full price, no intercept point.\n"
        "      * Conversation history shipped through Opus on every turn.\n"
        "      * Tool-call decisions the host makes (Read file X, Run Bash Y) —\n"
        "        those decisions ARE the agent loop.\n\n"

        f"  {_bold('Workarounds if you need more headroom')}\n"
        "      1. /model claude-sonnet-4-6 — drops the host to Sonnet for the\n"
        "         rest of the conversation. Sonnet handles tool orchestration\n"
        "         at ~5x lower cost than Opus 4.7. Best for routine work.\n"
        "      2. /clear between unrelated tasks — drops the 1M context so\n"
        "         each new request starts cheap. Best for topic switches.\n"
        "      3. CHUZOM_SIDECAR_PREFETCH=1 — opt into the sidecar so\n"
        "         introspection prompts skip the host entirely.\n"
        "      4. Pair-mode subscriptions (Codex CLI / Gemini CLI) — Chuzom\n"
        "         injects these ahead of paid externals when available, so\n"
        "         routed work runs on your existing subscription quota\n"
        "         instead of API spend.\n"
    )


def _check_savings_posture() -> list[str]:
    """Return rendered status lines for each quota-savings configuration check.

    Each line is one of ``_ok`` / ``_warn`` / ``_fail`` with a short
    actionable suggestion so the user knows exactly what env var or
    setting to flip. We check seven things in order of leverage:

    1. **OpenRouter key** — biggest unlock. Single key gives access to
       deepseek-v4-flash, qwen3-235b, claude-sonnet-4 via OpenRouter,
       which the ``cost_aggressive`` policy is wired for.
    2. **DeepSeek key** — direct access to deepseek-chat /
       deepseek-reasoner. Optional but unlocks the cheapest non-local
       reasoning tier when OpenRouter isn't set.
    3. **Sidecar pre-execution** — ``CHUZOM_SIDECAR_PREFETCH=1`` lets
       the hook answer introspection prompts without any tool calls.
    4. **Response router** — ``CHUZOM_RESPONSE_ROUTER=on`` (default on)
       compresses explanations in MCP tool responses before Claude reads
       them. Warn if explicitly disabled.
    5. **Enforcement mode** — strict / hard mode actually blocks
       bypasses; smart is the safe default. Off / shadow is a foot-gun.
    6. **Hook hint freshness** — the auto-route hook should be writing
       ``~/.chuzom/last_classification.json`` on every prompt. A stale
       file (> 1h) means the hook isn't firing.
    7. **Today's simple-share** — if any routing happened today, what
       fraction was classified ``simple``? Pre-fix this was 0%; healthy
       posture is > 30% on a chat-heavy session, > 50% on info-gathering.

    Failures here are advisory — they're rendered but don't append to
    the doctor's ``issues`` list, since "Chuzom works" and "Chuzom is
    optimally configured" are different bars.
    """
    import sqlite3
    import time
    from pathlib import Path

    lines: list[str] = []

    # 1. OpenRouter key — single biggest unlock.
    if os.environ.get("OPENROUTER_API_KEY"):
        lines.append(_ok("OPENROUTER_API_KEY set — full leaderboard pool reachable"))
    elif (Path.home() / ".chuzom" / "openrouter-routerarena.env").exists():
        lines.append(_warn(
            "OPENROUTER_API_KEY stored at ~/.chuzom/openrouter-routerarena.env "
            "but NOT loaded into env. Source the file before benchmark runs."
        ))
    else:
        lines.append(_warn(
            "OPENROUTER_API_KEY not set — deepseek-v4-flash / qwen3-235b / "
            "qwen3-coder-next unreachable. One key unlocks the leaderboard pool."
        ))

    # 2. DeepSeek key (direct).
    if os.environ.get("DEEPSEEK_API_KEY"):
        lines.append(_ok("DEEPSEEK_API_KEY set — direct deepseek-chat reachable"))
    else:
        lines.append(_warn(
            "DEEPSEEK_API_KEY not set — direct deepseek-chat unreachable "
            "(OpenRouter can still route there if its key is set)."
        ))

    # 3. Sidecar pre-execution.
    sidecar_value = os.environ.get("CHUZOM_SIDECAR_PREFETCH", "").strip().lower()
    if sidecar_value in {"1", "true", "yes", "on"}:
        lines.append(_ok("CHUZOM_SIDECAR_PREFETCH=on — introspection prompts pre-executed"))
    else:
        lines.append(_warn(
            "CHUZOM_SIDECAR_PREFETCH not set — introspection prompts ('show me "
            "my routing today', 'git status') still go through llm_query + tool "
            "calls. Set =1 to let the hook pre-execute and inject the result."
        ))

    # 4. Response router.
    rr_value = os.environ.get("CHUZOM_RESPONSE_ROUTER", "on").strip().lower()
    if rr_value == "off":
        lines.append(_warn(
            "CHUZOM_RESPONSE_ROUTER=off — MCP responses go to Claude unchanged. "
            "Default is on; you've explicitly disabled it."
        ))
    else:
        lines.append(_ok(
            f"CHUZOM_RESPONSE_ROUTER={rr_value or 'on'} — explanations compressed "
            "before they hit Claude's context"
        ))

    # 5. Enforcement mode.
    enforce = os.environ.get("CHUZOM_ENFORCE", "").strip().lower()
    if enforce in {"off", "shadow"}:
        lines.append(_warn(
            f"CHUZOM_ENFORCE={enforce} — route directives are advisory only. "
            "Claude can bypass without consequence; quota savings are best-effort."
        ))
    elif enforce in {"hard", "strict"}:
        lines.append(_ok(
            f"CHUZOM_ENFORCE={enforce} — bypasses are blocked"
        ))
    else:
        # Default / smart.
        lines.append(_ok("CHUZOM_ENFORCE=smart (default) — write tools blocked until route honored"))

    # 6. Hook hint freshness.
    hint_path = Path.home() / ".chuzom" / "last_classification.json"
    if hint_path.exists():
        try:
            age = time.time() - hint_path.stat().st_mtime
        except OSError:
            age = None
        if age is None:
            lines.append(_warn("last_classification.json unreadable"))
        elif age < 3600:
            lines.append(_ok(
                f"last_classification.json fresh ({int(age)}s) — hook hint bridge active"
            ))
        else:
            mins = int(age // 60)
            lines.append(_warn(
                f"last_classification.json is {mins}m old — auto-route hook may "
                "not be firing. Check ~/.chuzom/auto-route-debug.log for INVOCATION lines."
            ))
    else:
        lines.append(_warn(
            "~/.chuzom/last_classification.json missing — hook hint bridge "
            "has not run yet. Send any prompt to create it."
        ))

    # 7. Today's simple-share — the smoking-gun metric from the
    # earlier diagnostic. Pre-fix: 0/31 simple today. Healthy: > 30%.
    db = Path.home() / ".chuzom" / "usage.db"
    if db.is_file():
        try:
            conn = sqlite3.connect(str(db))
            row = conn.execute(
                "SELECT "
                "  SUM(CASE WHEN complexity='simple' THEN 1 ELSE 0 END), "
                "  COUNT(*) "
                "FROM routing_decisions "
                "WHERE date(timestamp,'localtime')=date('now','localtime') "
                "  AND COALESCE(reason_code,'') != 'sidecar_backfill'"
            ).fetchone()
            conn.close()
            simple_n, total_n = (row[0] or 0), (row[1] or 0)
        except sqlite3.Error:
            simple_n, total_n = 0, 0
        if total_n == 0:
            lines.append(_warn(
                "No routing decisions today yet — nothing to measure. "
                "Trigger a few llm_* tool calls and re-run."
            ))
        else:
            share = 100.0 * simple_n / total_n
            if share >= 30.0:
                lines.append(_ok(
                    f"Today's simple-share: {simple_n}/{total_n} ({share:.1f}%) — "
                    "boundary fix is firing"
                ))
            elif share > 0.0:
                lines.append(_warn(
                    f"Today's simple-share: {simple_n}/{total_n} ({share:.1f}%) — "
                    "below 30% target. Most prompts still classifying as moderate; "
                    "check classifier."
                ))
            else:
                lines.append(_warn(
                    f"Today's simple-share: 0/{total_n} — boundary fix isn't reaching "
                    "the router. Verify auto-route hook is installed with today's source."
                ))
    else:
        lines.append(_warn("~/.chuzom/usage.db missing — no telemetry to score"))

    return lines


def _run_doctor(host: Optional[str] = None) -> tuple[int, list[str]]:
    """Comprehensive health check — verify every component is wired up.

    Returns:
        (exit_code, issues) where exit_code is 0 for success, 1 for failure
    """
    if host:
        _run_doctor_host(host)
        # Fall through to also run the full general checks
        print()

    """Comprehensive general health check — verify every component is wired up."""
    from chuzom.install_hooks import (
        _HOOKS_DST,
        _HOOK_DEFS,
        _RULES_DST,
        _SETTINGS_PATH,
        check_api_keys,
        claude_desktop_config_path,
    )

    issues: list[str] = []

    print(f"\n{_bold('chuzom doctor')}\n")

    # ── 1. Hooks ───────────────────────────────────────────────────────────
    print(_bold("  Hooks"))
    for src_name, dst_name, event, _ in _HOOK_DEFS:
        dst = _HOOKS_DST / dst_name
        if dst.exists():
            # Check version freshness (assume src_name is in same directory)
            from chuzom.install_hooks import _HOOKS_SRC
            src = _HOOKS_SRC / src_name
            if src.exists():
                src_v = _hook_version_num(src)
                dst_v = _hook_version_num(dst)
                if src_v > dst_v:
                    print(
                        _warn(
                            f"{dst_name}  v{dst_v} installed, v{src_v} available"
                        )
                    )
                    issues.append(
                        f"Hook {dst_name} is outdated — run `chuzom install --force`"
                    )
                else:
                    print(_ok(f"{dst_name}  ({event})"))
            else:
                print(_ok(f"{dst_name}  ({event})"))
        else:
            print(
                _fail(
                    f"{dst_name}  ({event})  — not installed",
                    fix="chuzom install",
                )
            )
            issues.append(f"Hook {dst_name} not installed")

    # ── 1b. Hook Python path validation (B1 from audit) ─────────────────
    print(f"\n{_bold('  Hook interpreter paths')}")
    if _SETTINGS_PATH.exists():
        try:
            _settings_data = json.loads(_SETTINGS_PATH.read_text())
            _all_hooks = _settings_data.get("hooks", {})
            for _event, _entries in _all_hooks.items():
                if not isinstance(_entries, list):
                    continue
                for _entry in _entries:
                    for _hook in _entry.get("hooks", []):
                        _cmd = _hook.get("command", "")
                        if "chuzom" not in _cmd:
                            continue
                        # Extract Python interpreter path (first token)
                        _parts = _cmd.split()
                        if _parts:
                            _interp = _parts[0]
                            if os.path.exists(_interp):
                                print(_ok(f"{os.path.basename(_parts[-1])} → {_interp}"))
                            else:
                                print(
                                    _fail(
                                        f"{os.path.basename(_parts[-1])} → {_interp} NOT FOUND",
                                        fix="chuzom install --force",
                                    )
                                )
                                issues.append(
                                    f"Hook interpreter missing: {_interp} — "
                                    f"run `chuzom install --force` to fix"
                                )
        except Exception as _e:
            print(_warn(f"Could not parse settings.json: {_e}"))

    # ── 1c. Duplicate hook detection ──────────────────────────────────────
    if _SETTINGS_PATH.exists():
        try:
            _settings_data = json.loads(_SETTINGS_PATH.read_text())
            _all_hooks = _settings_data.get("hooks", {})
            for _event, _entries in _all_hooks.items():
                if not isinstance(_entries, list):
                    continue
                _seen_scripts: dict[str, int] = {}
                for _entry in _entries:
                    for _hook in _entry.get("hooks", []):
                        _cmd = _hook.get("command", "")
                        if "chuzom" not in _cmd:
                            continue
                        _script = _cmd.split()[-1] if _cmd.split() else _cmd
                        _seen_scripts[_script] = _seen_scripts.get(_script, 0) + 1
                for _script, _count in _seen_scripts.items():
                    if _count > 1:
                        print(
                            _warn(
                                f"Duplicate: {os.path.basename(_script)} registered "
                                f"{_count}x in {_event} — manual cleanup needed in settings.json"
                            )
                        )
                        issues.append(f"Duplicate hook: {os.path.basename(_script)} ({_count}x in {_event})")
        except Exception:
            pass

    # ── 2. Routing rules ───────────────────────────────────────────────────
    print(f"\n{_bold('  Routing rules')}")
    rules_dst = _RULES_DST / "chuzom.md"
    if rules_dst.exists():
        print(_ok("chuzom.md"))
    else:
        print(_fail("chuzom.md — not installed", fix="chuzom install"))
        issues.append("Routing rules not installed")

    # ── 3. Claude Code MCP registration ────────────────────────────────────
    print(f"\n{_bold('  Claude Code MCP')}")
    settings: dict = {}
    if _SETTINGS_PATH.exists():
        try:
            settings = json.loads(_SETTINGS_PATH.read_text())
        except Exception:
            pass
    registered_cc = "chuzom" in settings.get("mcpServers", {})
    if registered_cc:
        print(_ok("MCP server registered in ~/.claude/settings.json"))
    else:
        print(
            _fail(
                "MCP server not registered",
                fix="chuzom install",
            )
        )
        issues.append("MCP server not registered in Claude Code")

    # ── 4. Claude Desktop ──────────────────────────────────────────────────
    print(f"\n{_bold('  Claude Desktop')}")
    desktop_path = claude_desktop_config_path()
    if desktop_path is None:
        print(_warn("not supported on this platform"))
    elif not desktop_path.exists():
        print(
            _warn(
                f"config not found ({desktop_path}) — Claude Desktop may not be installed"
            )
        )
    else:
        try:
            cfg = json.loads(desktop_path.read_text())
            if "chuzom" in cfg.get("mcpServers", {}):
                print(_ok(f"registered ({desktop_path})"))
            else:
                print(
                    _fail(
                        "not registered in Claude Desktop",
                        fix="chuzom install",
                    )
                )
                issues.append("MCP server not registered in Claude Desktop")
        except Exception as e:
            print(_fail(f"could not read config: {e}"))

    # ── 5. Ollama ──────────────────────────────────────────────────────────
    print(f"\n{_bold('  Ollama (optional — free local classifier)')}")
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        req = urllib.request.Request(f"{ollama_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            model_names = [m.get("name", "") for m in data.get("models", [])]
            if model_names:
                preview = ", ".join(model_names[:3])
                if len(model_names) > 3:
                    preview += f" +{len(model_names) - 3} more"
                print(_ok(f"running — {len(model_names)} model(s): {preview}"))
            else:
                print(
                    _warn(
                        "running but no models pulled — run `ollama pull qwen2.5:0.5b`"
                    )
                )
    except Exception:
        print(
            _warn(
                f"not reachable at {ollama_url} — optional, but saves API cost"
            )
        )

    # ── 6. Usage data freshness ────────────────────────────────────────────
    print(f"\n{_bold('  Usage data (Claude subscription pressure)')}")
    usage_path = Path.home() / ".chuzom" / "usage.json"
    if not usage_path.exists():
        print(
            _warn(
                "usage.json not found — run `llm_check_usage` in Claude Code to populate"
            )
        )
    else:
        try:
            data = json.loads(usage_path.read_text())
            age_s = time.time() - data.get("updated_at", 0)
            if age_s < 1800:
                print(_ok(f"fresh ({int(age_s / 60)}m old)"))
            elif age_s < 3600:
                print(
                    _warn(
                        f"getting stale ({int(age_s / 60)}m old) — run `llm_check_usage`"
                    )
                )
            else:
                print(
                    _fail(
                        f"stale ({int(age_s / 3600)}h old) — routing may use wrong pressure",
                        fix="Run llm_check_usage in Claude Code",
                    )
                )
                issues.append("Usage data is stale")
        except Exception as e:
            print(_fail(f"could not read usage.json: {e}"))

    # ── 7. Provider keys ───────────────────────────────────────────────────
    print(f"\n{_bold('  Provider API keys')}")
    for line in check_api_keys():
        print(f"  {line}")

    # ── 8. claw-code ───────────────────────────────────────────────────────
    print(
        f"\n{_bold('  claw-code (optional — open-source Claude Code alternative)')}"
    )
    try:
        from chuzom.install_hooks import (
            _CLAW_CODE_HOOK_DEFS,
            _claw_code_dir,
        )

        cc_dir = _claw_code_dir()
        if cc_dir is None:
            print(
                _dim(
                    "  not detected (install at github.com/claw-code/claw-code)"
                )
            )
        else:
            cc_hooks_dst = cc_dir / "hooks"
            cc_settings = {}
            cc_settings_path = cc_dir / "settings.json"
            if cc_settings_path.exists():
                try:
                    cc_settings = json.loads(cc_settings_path.read_text())
                except Exception:
                    pass
            for _, dst_name, event, _ in _CLAW_CODE_HOOK_DEFS:
                dst = cc_hooks_dst / dst_name
                if dst.exists():
                    print(_ok(f"{dst_name}  ({event})"))
                else:
                    print(
                        _fail(
                            f"{dst_name}  — not installed",
                            fix="chuzom install --claw-code",
                        )
                    )
                    issues.append(f"claw-code hook {dst_name} not installed")
            if "chuzom" in cc_settings.get("mcpServers", {}):
                print(
                    _ok("MCP server registered in claw-code settings.json")
                )
            else:
                print(
                    _fail(
                        "MCP server not registered in claw-code",
                        fix="chuzom install --claw-code",
                    )
                )
                issues.append("MCP server not registered in claw-code")
    except Exception:
        # claw-code not installed or issue importing
        pass

    # ── 9. Version ────────────────────────────────────────────────────────
    print(f"\n{_bold('  Version')}")
    try:
        from chuzom import __version__ as project_version
        print(_ok(f"chuzom {project_version}"))
    except Exception:
        try:
            from importlib.metadata import version
            v = version("chuzom")
            print(_ok(f"chuzom {v}"))
        except Exception:
            print(_warn("could not determine installed version"))

    # ── 10. Quota savings posture ─────────────────────────────────────────
    # Verifies the features that drive cost-savings in a live session are
    # actually wired up. Each finding suggests a concrete env var or
    # config change so the operator can close the gap.
    print(f"\n{_bold('  Quota savings posture')}")
    _savings_warnings = _check_savings_posture()
    for line in _savings_warnings:
        print(line)
    # Posture warnings are advisory — surface them in the summary but
    # don't fail the doctor. The user wanted to *see* whether config is
    # optimal, not be blocked by it.

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    if not issues:
        print(_green(_bold("  ✓ All checks passed. Chuzom is healthy.")))
        exit_code = 0
    else:
        print(_red(_bold(f"  ✗ {len(issues)} issue(s) found:")))
        for issue in issues:
            print(f"    {_red('•')} {issue}")
        exit_code = 1
    print()

    return exit_code, issues


def cmd_doctor(args: list[str]) -> int:
    """Execute: chuzom doctor [--host H] [--posture] [--explain-host]

    Flags:
        --host H        Run host-specific checks (claude|vscode|cursor|all)
                        IN ADDITION to the general health checks.
        --posture       Print ONLY the quota-savings posture section.
                        Skips the long general health scan; ideal for
                        a fast in-session "am I configured for max
                        savings?" check.
        --explain-host  Print the always-up-to-date explainer for why
                        the host runs on Opus and what routing can vs
                        can't save. Skips everything else.

    Returns:
        0 if all checks passed, 1 if issues found.
    """
    if "--explain-host" in args:
        print(_render_host_explainer())
        return 0

    if "--posture" in args:
        print(f"\n{_bold('  Quota savings posture')}")
        for line in _check_savings_posture():
            print(line)
        print()
        return 0

    host_flag = None
    if "--host" in args:
        idx = args.index("--host")
        host_flag = args[idx + 1] if idx + 1 < len(args) else None

    exit_code, _ = _run_doctor(host=host_flag)
    return exit_code
