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
    # RED2-10-05: uninstall must NOT leave a persistent .chuzom-bak behind.
    assert not t.with_suffix(".toml.chuzom-bak").exists(), "leftover .chuzom-bak cruft"


def test_malformed_record_does_not_abort_replay(home):
    """RED1-10-01: a non-dict manifest record must be skipped, not crash the loop."""
    import json as _json
    good = home / "gone.md"
    good.write_text("chuzom")
    # Manually plant a manifest with a good record AND a malformed (string) one.
    mpath = home / ".chuzom" / "install-manifest.json"
    mpath.parent.mkdir(parents=True)
    mpath.write_text(_json.dumps([
        {"kind": "created_file", "path": str(good), "block": "chuzom"},
        "this-is-not-a-dict",  # malformed
    ]))
    actions = im.apply_uninstall()  # must not raise
    assert not good.exists(), "RED1-10-01: good record not replayed after malformed one"
    assert any("malformed" in a for a in actions)


def test_created_file_preserves_user_appended_content(home):
    """RED1-10-02: created_file removal must strip only chuzom's text, keeping
    anything the user appended after install."""
    f = home / "instructions.md"
    chuzom_text = "# chuzom routing rules\ncall llm_query\n"
    f.write_text(chuzom_text + "\n# MY OWN NOTES\nkeep me\n")
    im.record("created_file", f, block=chuzom_text)
    im.apply_uninstall()
    assert f.exists(), "RED1-10-02: file with user content was deleted"
    assert "MY OWN NOTES" in f.read_text() and "keep me" in f.read_text()
    assert "call llm_query" not in f.read_text(), "chuzom block not stripped"


def test_created_file_deleted_when_only_chuzom_content(home):
    f = home / "instructions.md"
    chuzom_text = "# chuzom rules\n"
    f.write_text(chuzom_text)
    im.record("created_file", f, block=chuzom_text)
    im.apply_uninstall()
    assert not f.exists(), "a chuzom-only created file should be removed entirely"
