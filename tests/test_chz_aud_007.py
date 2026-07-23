"""CHZ-AUD-007 regression: README enforcement-mode default must match code default.

enforce_config.DEFAULT_ENFORCE is 'soft' (changed in v0.8.7).
The README config table and env-var reference still say 'smart' (default).
This test enforces that the README-documented default equals the code default.
"""
from __future__ import annotations

import re
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chuzom.enforce_config import DEFAULT_ENFORCE  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
README = REPO_ROOT / "README.md"


def _readme_enforce_table_default() -> str | None:
    """Extract the default value from the CHUZOM_ENFORCE row in the config table.

    Looks for patterns like:
      | `CHUZOM_ENFORCE` | `smart` | ...
    and returns the value cell content (e.g. 'smart' or 'soft').
    """
    text = README.read_text(encoding="utf-8")
    # Match the table row for CHUZOM_ENFORCE: | `CHUZOM_ENFORCE` | `<value>` | ...
    match = re.search(
        r"\|\s*`CHUZOM_ENFORCE`\s*\|\s*`([^`]+)`\s*\|",
        text,
    )
    if match:
        return match.group(1).strip()
    return None


def _readme_enforce_mode_section_default() -> str | None:
    """Check for '(default)' marker in the Enforcement Modes table.

    Returns the mode that has '(default)' next to it, if any.
    """
    text = README.read_text(encoding="utf-8")
    # Find rows like: | `smart` (default) | ...
    match = re.search(r"\|\s*`([^`]+)`\s*\(default\)", text)
    if match:
        return match.group(1).strip()
    return None


class TestEnforceDefaultConsistency:
    """The README must document the same default as enforce_config.DEFAULT_ENFORCE."""

    def test_enforce_config_default_is_soft(self) -> None:
        """Code default must be 'soft' (set in v0.8.7 for safety)."""
        assert DEFAULT_ENFORCE == "soft", (
            f"enforce_config.DEFAULT_ENFORCE is '{DEFAULT_ENFORCE}', expected 'soft'. "
            "If the default changed intentionally, update this test and README together."
        )

    def test_readme_config_table_matches_code_default(self) -> None:
        """The CHUZOM_ENFORCE row in README's config reference table matches code."""
        readme_default = _readme_enforce_table_default()
        assert readme_default is not None, (
            "Could not find CHUZOM_ENFORCE row in README config table. "
            "Expected a row like: | `CHUZOM_ENFORCE` | `soft` | ..."
        )
        assert readme_default == DEFAULT_ENFORCE, (
            f"README config table says CHUZOM_ENFORCE default is '{readme_default}' "
            f"but enforce_config.DEFAULT_ENFORCE is '{DEFAULT_ENFORCE}'. "
            "Update README.md so they agree."
        )

    def test_readme_enforcement_modes_section_default_marker(self) -> None:
        """The Enforcement Modes table '(default)' marker points to the code default."""
        mode_section_default = _readme_enforce_mode_section_default()
        if mode_section_default is None:
            # No '(default)' marker is acceptable — as long as the table row is right
            return
        assert mode_section_default == DEFAULT_ENFORCE, (
            f"Enforcement Modes table marks '{mode_section_default}' as (default), "
            f"but enforce_config.DEFAULT_ENFORCE is '{DEFAULT_ENFORCE}'. "
            "Move the '(default)' marker to the '{DEFAULT_ENFORCE}' row."
        )

    def test_readme_does_not_show_smart_as_enforce_default(self) -> None:
        """'smart (default)' must not appear in README — 'soft' is the real default."""
        text = README.read_text(encoding="utf-8")
        assert "`smart` (default)" not in text, (
            "README still contains '`smart` (default)' in the Enforcement Modes table. "
            "The code ships 'soft' as the default. Update the README."
        )
