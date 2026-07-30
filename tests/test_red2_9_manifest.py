"""Regression: RED2-9-* — install manifest records artifacts and uninstall
replay reverses them (the structural fix for uninstall coverage drift)."""
import json
import pathlib
import pytest
from chuzom import install_manifest as im


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_json_mcp_record_and_remove(home):
    cfg = home / "cfg.json"
    cfg.write_text(json.dumps({"mcpServers": {"chuzom": {"x": 1}, "keep": {"y": 2}}}))
    im.record("json_mcp", cfg, root_key="mcpServers", server="chuzom")
    im.apply_uninstall()
    data = json.loads(cfg.read_text())
    assert "chuzom" not in data["mcpServers"] and "keep" in data["mcpServers"]
    assert not im._manifest_path().exists(), "manifest not cleared after apply"


def test_created_file_and_dir_and_text_block(home):
    f = home / "instructions.md"
    f.write_text("chuzom rules")
    d = home / "extensions" / "chuzom"
    d.mkdir(parents=True)
    other = home / "notes.md"
    other.write_text("user notes\n\nCHUZOM_BLOCK\n")
    im.record("created_file", f)
    im.record("dir", d)
    im.record("text_block", other, block="\n\nCHUZOM_BLOCK\n")
    im.apply_uninstall()
    assert not f.exists() and not d.exists()
    assert other.read_text() == "user notes", "appended block not cleanly stripped / user content lost"


def test_toml_table_record_backs_up(home):
    t = home / ".codex" / "config.toml"
    t.parent.mkdir(parents=True)
    t.write_text('[model_providers.chuzom]\nname="C"\n[other]\nk=1\n')
    im.record("toml_table", t, header="model_providers.chuzom")
    im.apply_uninstall()
    assert "[model_providers.chuzom]" not in t.read_text()
    assert "[other]" in t.read_text()
    assert t.with_suffix(".toml.chuzom-bak").exists(), "no backup before TOML mutation"
