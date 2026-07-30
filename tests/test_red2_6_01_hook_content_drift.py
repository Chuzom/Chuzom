"""Regression: RED2-6-01 / RED2-6-03 — hook & rules auto-update must be
CONTENT-aware, not purely version-stamp-gated.

`check_and_update_hooks()`/`check_and_update_rules()` re-copied only when the
bundled version stamp was strictly newer. A hook/rules file whose behaviour
changed without a stamp bump (a repeated real slip that stranded even security
fixes on installed machines) never propagated. They now also re-copy when the
stamps match but the installed bytes differ — while never downgrading.
"""
from __future__ import annotations

import chuzom.install_hooks as ih


def _setup(tmp_path, monkeypatch):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    monkeypatch.setattr(ih, "_HOOKS_SRC", src)
    monkeypatch.setattr(ih, "_HOOKS_DST", dst)
    monkeypatch.setattr(ih, "_SETTINGS_PATH", tmp_path / "settings.json")
    # Neutralize the legacy-alias sync (needs settings/other files we don't stub).
    monkeypatch.setattr(ih, "_sync_legacy_hook_alias", lambda *a, **k: None)
    # Single managed hook for the test.
    monkeypatch.setattr(ih, "_HOOK_DEFS", [("h.py", "chuzom-h.py", "SessionStart", "")])
    return src / "h.py", dst / "chuzom-h.py"


def test_content_drift_at_same_version_refreshes(tmp_path, monkeypatch):
    src, dst = _setup(tmp_path, monkeypatch)
    src.write_text("# chuzom-hook-version: 5\nNEW behaviour (fixed)\n")
    dst.write_text("# chuzom-hook-version: 5\nOLD behaviour (buggy)\n")

    msgs = ih.check_and_update_hooks()

    assert dst.read_text() == src.read_text(), "RED2-6-01: content drift not propagated"
    assert any("Refreshed" in m and "drift" in m for m in msgs), msgs


def test_identical_content_is_a_noop(tmp_path, monkeypatch):
    src, dst = _setup(tmp_path, monkeypatch)
    body = "# chuzom-hook-version: 5\nsame\n"
    src.write_text(body)
    dst.write_text(body)
    msgs = ih.check_and_update_hooks()
    assert msgs == [], "no update expected when content is identical"


def test_newer_version_still_updates(tmp_path, monkeypatch):
    src, dst = _setup(tmp_path, monkeypatch)
    src.write_text("# chuzom-hook-version: 6\nv6\n")
    dst.write_text("# chuzom-hook-version: 5\nv5\n")
    msgs = ih.check_and_update_hooks()
    assert dst.read_text() == src.read_text()
    assert any("→ v6" in m or "v5 → v6" in m for m in msgs), msgs


def test_never_downgrades_a_newer_installed_hook(tmp_path, monkeypatch):
    """src_v < dst_v (dev/newer installed) must be left untouched even if content differs."""
    src, dst = _setup(tmp_path, monkeypatch)
    src.write_text("# chuzom-hook-version: 5\nolder bundled\n")
    dst.write_text("# chuzom-hook-version: 9\nnewer installed\n")
    ih.check_and_update_hooks()
    assert dst.read_text() == "# chuzom-hook-version: 9\nnewer installed\n"


def test_rules_content_drift_refreshes(tmp_path, monkeypatch):
    rsrc = tmp_path / "rsrc"
    rdst = tmp_path / "rdst"
    rsrc.mkdir()
    rdst.mkdir()
    monkeypatch.setattr(ih, "_RULES_SRC", rsrc)
    monkeypatch.setattr(ih, "_RULES_DST", rdst)
    (rsrc / "chuzom.md").write_text("<!-- chuzom-rules-version: 7 -->\nNEW rules\n")
    (rdst / "chuzom.md").write_text("<!-- chuzom-rules-version: 7 -->\nOLD rules\n")

    msg = ih.check_and_update_rules()

    assert (rdst / "chuzom.md").read_text() == (rsrc / "chuzom.md").read_text()
    assert msg and "drift" in msg, msg


def test_rules_identical_is_noop(tmp_path, monkeypatch):
    rsrc = tmp_path / "rsrc"
    rdst = tmp_path / "rdst"
    rsrc.mkdir()
    rdst.mkdir()
    monkeypatch.setattr(ih, "_RULES_SRC", rsrc)
    monkeypatch.setattr(ih, "_RULES_DST", rdst)
    body = "<!-- chuzom-rules-version: 7 -->\nsame\n"
    (rsrc / "chuzom.md").write_text(body)
    (rdst / "chuzom.md").write_text(body)
    assert ih.check_and_update_rules() is None
