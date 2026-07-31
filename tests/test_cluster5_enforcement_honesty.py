"""Regression: CHZ-AUD-D-05 — enforcement messaging must not claim 'never blocks'
while the DEFAULT mode (smart) actually holds reasoning/Q&A tools until routed."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rules_file_does_not_claim_never_blocks():
    txt = (ROOT / "src" / "chuzom" / "rules" / "chuzom.md").read_text()
    low = txt.lower()
    # The flat false claim must be gone.
    assert "no tool is ever blocked" not in low
    # Header must not assert advise/never-block as the mode.
    assert "route everywhere, never block" not in low
    # Must acknowledge enforcement/holding exists.
    assert "hold" in low or "block" in low


def test_default_enforce_mode_is_an_enforcing_mode():
    from chuzom.enforce_config import DEFAULT_ENFORCE
    assert DEFAULT_ENFORCE == "smart"


def test_enforce_label_is_honest_for_enforcing_modes():
    spec = importlib.util.spec_from_file_location(
        "ss_d05", ROOT / "src" / "chuzom" / "hooks" / "session-start.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    # Enforcing modes must NOT claim they never block, and must say they hold.
    for mode in ("smart", "hard", "strict"):
        label = m._enforce_label.__wrapped__(mode) if hasattr(m._enforce_label, "__wrapped__") else None
    # _enforce_label() reads the resolved mode; test the description dict directly
    # via a monkeypatch of resolve_enforce_mode.
    import chuzom.enforce_config as ec
    orig = ec.resolve_enforce_mode
    try:
        for mode in ("smart", "hard", "strict"):
            ec.resolve_enforce_mode = lambda *a, **k: mode
            # session-start imports resolve at call time
            label = m._enforce_label()
            assert "never block" not in label.lower(), f"{mode} falsely claims never-block: {label}"
            assert "hold" in label.lower(), f"{mode} does not disclose holding: {label}"
    finally:
        ec.resolve_enforce_mode = orig
