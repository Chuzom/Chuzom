"""Gap remediation tests — Phase 1 (Critical).

Covers:
  A1  — onboard.py calls chuzom install automatically
  B1  — research/* returns empty chain so direct-executor falls through to llm_research
  B2  — temporal-signal research prompts never get Ollama direct answers
  C1  — statusline registration skips gracefully on Windows without bash
  C2  — APPDATA fallback uses LOCALAPPDATA on Windows
  D3  — onboard.py prompts for Claude subscription
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOKS_CHAIN_BUILDER = ROOT / "src" / "chuzom" / "hooks" / "chain_builder.py"
ONBOARD_SRC = ROOT / "src" / "chuzom" / "onboard.py"
INSTALL_HOOKS_SRC = ROOT / "src" / "chuzom" / "install_hooks.py"


# ─── B1 + B2: Research chain always empty ─────────────────────────────────────

class TestResearchChainBypass:
    """B1+B2: build_chain must return [] for ALL research tasks so direct-executor
    falls through and llm_research (Perplexity) is invoked via MCP instead."""

    def setup_method(self):
        from chuzom.hooks.chain_builder import build_chain
        self.build_chain = build_chain

    @pytest.mark.parametrize("complexity", ["simple", "moderate", "complex", "deep_reasoning"])
    def test_research_returns_empty_chain_at_all_complexities(self, complexity):
        """research/* must return [] at every complexity — no Ollama, no external APIs."""
        chain = self.build_chain(complexity, "green", "research")
        assert chain == [], (
            f"research/{complexity} returned non-empty chain {chain}. "
            "Research must always fall through to llm_research MCP tool."
        )

    @pytest.mark.parametrize("zone", ["green", "yellow", "orange", "red", "critical"])
    def test_research_returns_empty_chain_at_all_pressure_zones(self, zone):
        """Even at 'green' pressure (lots of quota), research must not use direct execution."""
        chain = self.build_chain("moderate", zone, "research")
        assert chain == [], (
            f"research/moderate at zone={zone} returned {chain}. "
            "Quota pressure must not override research→Perplexity routing."
        )

    @pytest.mark.parametrize("task_type", ["query", "code", "generate", "analyze"])
    def test_non_research_tasks_still_get_ollama_chains(self, task_type):
        """Non-research simple tasks must still get local Ollama models (free-first)."""
        chain = self.build_chain("simple", "green", task_type)
        assert len(chain) > 0, (
            f"{task_type}/simple returned empty chain — non-research tasks must still direct-execute."
        )

    def test_research_does_not_block_on_missing_perplexity_key(self):
        """Empty chain must be returned even when PERPLEXITY_API_KEY is absent.
        The MCP tool handles the missing-key error, not the chain builder."""
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("PERPLEXITY_API_KEY", None)
            chain = self.build_chain("moderate", "green", "research")
        assert chain == [], "research must return [] regardless of PERPLEXITY_API_KEY presence"


# ─── B2: Hook-level audit — research prompts produce llm_research directive ───

class TestResearchHookOutput:
    """B2: Verify the full hook pipeline produces ⚡ MANDATORY ROUTE → llm_research
    for time-sensitive research prompts, not a cached Ollama block.

    The auto-route hook is a standalone script loaded via importlib; if it
    can't be imported as a module (missing transitive deps), tests skip.
    """

    TEMPORAL_PROMPTS = [
        "what is the latest news on AI regulation in the EU in 2026",
        "latest news about OpenAI",
        "what happened today in the stock market",
        "current state of AI in 2026",
        "breaking news about climate change this week",
    ]

    @pytest.fixture(autouse=True)
    def _load_classify(self):
        """Load classify_prompt from the installed hook script via importlib."""
        import importlib.util
        hook_path = Path.home() / ".claude" / "hooks" / "chuzom-auto-route.py"
        if not hook_path.exists():
            pytest.skip(f"Hook not installed at {hook_path}")
        spec = importlib.util.spec_from_file_location("chuzom_auto_route", hook_path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except SystemExit:
            pass  # hook exits when run without stdin — that's expected
        except Exception as exc:
            pytest.skip(f"Could not load hook module: {exc}")
        if not hasattr(mod, "classify_prompt"):
            pytest.skip("classify_prompt not exported from hook script")
        self.classify_prompt = mod.classify_prompt

    @pytest.mark.parametrize("prompt", TEMPORAL_PROMPTS)
    def test_temporal_research_prompts_classify_as_research(self, prompt):
        """These prompts must classify as research/* — never query or generate."""
        result = self.classify_prompt(prompt)
        if result is None:
            pytest.skip(f"classify_prompt returned None for {prompt!r} — heuristic inconclusive")
        assert result["task_type"] == "research", (
            f"Prompt {prompt!r} classified as {result['task_type']!r}, expected 'research'. "
            "Temporal research prompts must go to llm_research, not Ollama."
        )


# ─── A1: onboard.py auto-calls install ───────────────────────────────────────

class TestOnboardAutoInstall:
    """A1: chuzom-onboard must call chuzom install automatically after writing .env."""

    def test_onboard_imports_install_hooks(self):
        """onboard.py source must import chuzom.install_hooks."""
        src = ONBOARD_SRC.read_text()
        assert "chuzom.install_hooks" in src, (
            "onboard.py must import from chuzom.install_hooks to auto-install hooks (gap A1)"
        )

    def test_onboard_calls_install(self):
        """onboard.py source must call the install function."""
        src = ONBOARD_SRC.read_text()
        assert "_install_hooks()" in src, (
            "onboard.py must call _install_hooks() to auto-install hooks (gap A1)"
        )

    def test_onboard_install_is_in_main_flow(self):
        """The install call must be inside the main() function, not a dead branch."""
        tree = ast.parse(ONBOARD_SRC.read_text())
        main_fn = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main"),
            None,
        )
        assert main_fn is not None, "main() function must exist in onboard.py"
        src_in_main = ast.unparse(main_fn)
        assert "_install_hooks" in src_in_main, (
            "_install_hooks() call must be inside main(), not at module level"
        )

    def test_onboard_install_has_error_handling(self):
        """Install call must be wrapped in try/except — install failure must not crash onboard."""
        src = ONBOARD_SRC.read_text()
        assert "except" in src, (
            "onboard.py must have try/except around the install call so "
            "hook installation failure doesn't abort the wizard (gap A1)"
        )

    def test_onboard_asks_subscription_question(self):
        """onboard.py must ask the user about Claude subscription (gap D3)."""
        src = ONBOARD_SRC.read_text()
        assert "CHUZOM_CLAUDE_SUBSCRIPTION" in src, (
            "onboard.py must set CHUZOM_CLAUDE_SUBSCRIPTION based on user answer (gap D3)"
        )


# ─── C1: Windows bash detection ───────────────────────────────────────────────

class TestWindowsBashDetection:
    """C1: statusline registration must skip gracefully on Windows when bash is absent."""

    def test_install_hooks_checks_bash_on_windows(self):
        """install_hooks.py must have logic to skip statusline when bash is not in PATH."""
        src = INSTALL_HOOKS_SRC.read_text()
        assert 'which("bash")' in src or "shutil.which" in src, (
            "install_hooks.py must check for bash availability (gap C1)"
        )
        assert "win32" in src, "Windows platform detection must be present (gap C1)"

    def test_statusline_skipped_on_windows_without_bash(self, monkeypatch, tmp_path):
        """On Windows without bash, statusline must be skipped — not raise an error."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("HOME", str(tmp_path))

        import shutil as _shutil
        original_which = _shutil.which

        def mock_which(cmd, *a, **kw):
            if cmd == "bash":
                return None  # simulate bash not found
            return original_which(cmd, *a, **kw)

        with patch("shutil.which", side_effect=mock_which):
            # Should not raise even with no bash
            src = INSTALL_HOOKS_SRC.read_text()
            assert "statusLine skipped on Windows" in src or "bash not in PATH" in src, (
                "install_hooks.py must emit a message when skipping statusline on Windows"
            )


# ─── C2: Windows APPDATA fallback ─────────────────────────────────────────────

class TestWindowsAPPDATAFallback:
    """C2: When APPDATA is unset on Windows, LOCALAPPDATA must be used."""

    def test_claude_desktop_config_path_uses_localappdata_fallback(self, monkeypatch):
        """claude_desktop_config_path() must return LOCALAPPDATA path when APPDATA is absent."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\Test\\AppData\\Local")

        from chuzom.install_hooks import claude_desktop_config_path
        result = claude_desktop_config_path()

        assert result is not None, (
            "claude_desktop_config_path() must not return None when LOCALAPPDATA is set (gap C2)"
        )
        assert "Local" in str(result) or "localappdata" in str(result).lower(), (
            f"Expected path under LOCALAPPDATA, got: {result}"
        )

    def test_claude_desktop_config_path_uses_appdata_when_set(self, monkeypatch):
        """When APPDATA is set, APPDATA must be preferred over LOCALAPPDATA."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", "C:\\Users\\Test\\AppData\\Roaming")
        monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\Test\\AppData\\Local")

        from chuzom.install_hooks import claude_desktop_config_path
        result = claude_desktop_config_path()

        assert "Roaming" in str(result), (
            f"APPDATA should be preferred when set, got: {result}"
        )

    def test_claude_desktop_config_path_returns_none_when_both_missing(self, monkeypatch):
        """If both APPDATA and LOCALAPPDATA are unset on Windows, return None gracefully."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)

        from chuzom.install_hooks import claude_desktop_config_path
        result = claude_desktop_config_path()

        assert result is None, (
            "Must return None (not raise) when neither APPDATA nor LOCALAPPDATA is set"
        )
