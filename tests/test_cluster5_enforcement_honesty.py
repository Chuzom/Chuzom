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
    # _enforce_label() reads the resolved mode; drive it via resolve_enforce_mode.
    import re
    import chuzom.enforce_config as ec
    orig = ec.resolve_enforce_mode
    try:
        for mode in ("smart", "hard", "strict"):
            ec.resolve_enforce_mode = lambda *a, **k: mode
            label = m._enforce_label()
            low = label.lower()
            assert "never block" not in low, f"{mode} falsely claims never-block: {label}"
            assert "hold" in low, f"{mode} does not disclose holding: {label}"
    finally:
        ec.resolve_enforce_mode = orig


def test_hard_strict_labels_do_not_claim_edit_write_bash_proceed():
    """CHZ-AUD-D-05/A-06 sibling: HARD/STRICT hold Bash/Edit/Write/MultiEdit/
    NotebookEdit — their session-start labels must NOT claim those tools 'proceed'
    (only SMART, which holds just reasoning/Q&A tools on Q&A tasks, may say that).
    This asserts the SPECIFIC false claim is absent, not merely that 'never block'
    is absent — the gap the previous test could not catch."""
    import re
    import importlib.util as _u
    spec = _u.spec_from_file_location(
        "ss_d05b", ROOT / "src" / "chuzom" / "hooks" / "session-start.py")
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    import chuzom.enforce_config as ec
    orig = ec.resolve_enforce_mode
    try:
        for mode in ("hard", "strict"):
            ec.resolve_enforce_mode = lambda *a, **k: mode
            label = m._enforce_label()
            low = label.lower()
            assert not re.search(r"edit\s*/\s*write\s*/\s*bash\s+proceed", low), \
                f"{mode} falsely claims Edit/Write/Bash proceed: {label}"
            # Must name the implementation tools it actually holds.
            assert "bash/edit/write" in low or "bash/edit" in low, \
                f"{mode} does not disclose it holds the implementation tools: {label}"
        # SMART legitimately lets code tasks proceed — its label MAY mention proceed.
        ec.resolve_enforce_mode = lambda *a, **k: "smart"
        smart = m._enforce_label().lower()
        assert "proceed" in smart, f"smart should disclose code tasks proceed: {smart}"
    finally:
        ec.resolve_enforce_mode = orig


def test_hard_mode_banner_does_not_claim_edit_write_bash_allowed():
    """CHZ-AUD-A-06: the hard-enforcement directive banner must not claim
    'Edit/Write/Bash stay allowed' — hard mode blocks them."""
    src = (ROOT / "src" / "chuzom" / "hooks" / "auto-route.py").read_text()
    assert "(Edit/Write/Bash) stay allowed" not in src
    # It must acknowledge the blocked tools in hard mode.
    assert "Bash/Edit/Write/MultiEdit/NotebookEdit are" in src


def test_rules_document_guarantee_scope_honestly():
    """CHZ-AUD-A-03/A-05: rules must state that push execution is advisory
    unless zero-Claude, and that PreToolUse cannot intercept a prose-only answer."""
    rules = (ROOT / "src" / "chuzom" / "rules" / "chuzom.md").read_text()
    # A-03: external execution is advisory by default; only zero-Claude is authoritative.
    assert "CHUZOM_ZERO_CLAUDE=1" in rules
    assert "authoritative turn replacement" in rules
    # A-05: prose-only answers are not interceptable by PreToolUse.
    assert "cannot intercept a prose-only answer" in rules


def test_session_start_banner_not_absolute_never_block():
    """CHZ-AUD-D-05/A-06 sibling: the session-start banner must not assert
    routing 'never a block' — enforcement decides what is blocked."""
    src = (ROOT / "src" / "chuzom" / "hooks" / "session-start.py").read_text()
    assert "never a block" not in src
