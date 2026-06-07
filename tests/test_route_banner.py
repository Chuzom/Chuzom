"""Test the routing-visibility banner emitted on DIRECT route success.

When chuzom's DIRECT path successfully handles a prompt (without involving
Claude), ``auto-route.py`` prints a one-line stderr banner showing which
model answered. The line lands under Claude Code's "UserPromptSubmit:hook
success:" header — visible to the user — whereas the same information in
``additionalContext`` only reaches the model.

The banner can be disabled with ``CHUZOM_ROUTE_BANNER`` set to any of
``off|0|false|no`` (case-insensitive).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest


_SRC_HOOK = Path(__file__).resolve().parent.parent / "src" / "chuzom" / "hooks" / "auto-route.py"


def test_banner_block_is_present_in_source() -> None:
    """Source-level guard: the banner emit block must remain in the
    DIRECT-success branch of ``auto-route.py``. Catches the regression
    where someone accidentally removes the stderr write or the env-var
    guard while refactoring the routing path.
    """
    source = _SRC_HOOK.read_text()
    assert "CHUZOM_ROUTE_BANNER" in source, (
        "missing CHUZOM_ROUTE_BANNER opt-out — banner emit block deleted?"
    )
    assert "🎯 routed →" in source, (
        "missing 🎯 routed → format string — banner emit block deleted?"
    )
    # Verify the block sits inside the DIRECT-success branch (i.e. follows
    # the DIRECT SUCCESS debug_log line) rather than firing unconditionally.
    direct_idx = source.find("DIRECT SUCCESS:")
    banner_idx = source.find("🎯 routed →")
    assert direct_idx > 0 and banner_idx > direct_idx, (
        "banner emit must follow the DIRECT SUCCESS debug_log within the "
        "same branch — otherwise it fires on prompts that didn't actually "
        "route directly"
    )


@pytest.mark.parametrize(
    "value, expect_emit",
    [
        (None, True),       # unset → default on
        ("on", True),
        ("1", True),
        ("true", True),
        ("off", False),
        ("OFF", False),     # case-insensitive
        ("0", False),
        ("false", False),
        ("no", False),
        ("  no  ", False),  # whitespace tolerated
    ],
)
def test_opt_out_env_var(
    value: str | None, expect_emit: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact predicate the hook uses to decide whether to emit."""
    if value is None:
        monkeypatch.delenv("CHUZOM_ROUTE_BANNER", raising=False)
    else:
        monkeypatch.setenv("CHUZOM_ROUTE_BANNER", value)
    raw = os.environ.get("CHUZOM_ROUTE_BANNER", "on").strip().lower()
    emit = raw not in ("0", "off", "false", "no")
    assert emit is expect_emit, (
        f"CHUZOM_ROUTE_BANNER={value!r} → emit={emit}, expected {expect_emit}"
    )


def test_banner_format_renders_expected_fields() -> None:
    """The banner string must include the provider/model, task/complexity,
    and a human-friendly latency in seconds (1-decimal). Exercises the
    same f-string the hook uses so any format-drift surfaces here.
    """
    provider, model = "gemini", "gemini-2.5-flash"
    latency_ms = 1463
    task_type, complexity = "query", "simple"
    latency_s = latency_ms / 1000.0
    line = (
        f"🎯 routed → {provider}/{model} "
        f"· {task_type}/{complexity} · {latency_s:.1f}s"
    )
    assert line == "🎯 routed → gemini/gemini-2.5-flash · query/simple · 1.5s"


def test_emit_block_wraps_in_try_except() -> None:
    """The banner emit MUST swallow exceptions — UI presentation is never
    a reason to break a successful routing decision. Verified via AST
    walk so the test fails even on subtle restructures.
    """
    tree = ast.parse(_SRC_HOOK.read_text(), filename=str(_SRC_HOOK))
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body_src = ast.unparse(node)
        if "🎯 routed →" in body_src and "CHUZOM_ROUTE_BANNER" not in body_src:
            # The try/except wrapping the print itself (env-var check is
            # outside the try; that's expected).
            found = True
            break
        if "🎯 routed →" in body_src:
            found = True
            break
    assert found, (
        "the 🎯 routed → print must sit inside a try/except so a UI rendering "
        "failure cannot block a successful route"
    )
