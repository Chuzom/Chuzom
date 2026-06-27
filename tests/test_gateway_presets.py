"""Gateway multi-protocol surface + preset resolution.

Deterministic (no network): asserts all wire-format routes are mounted and that
preset resolution honors env overrides and ~/.chuzom/presets.yaml.
"""
import importlib

import pytest


def test_gateway_mounts_all_formats():
    from chuzom.gateway import app
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/v1/chat/completions" in paths     # OpenAI
    assert "/v1/messages" in paths             # Anthropic
    assert "/api/chat" in paths                # Ollama chat
    assert "/api/generate" in paths            # Ollama generate
    assert "/healthz" in paths


def test_classifier_tiers():
    from chuzom.gateway import _classify
    assert _classify("fix the bug in the parser")[0] == "code"
    assert _classify("what are economic moats")[0] == "analyze"
    assert _classify("x" * 50)[1] == "simple"
    assert _classify("x" * 600)[1] == "moderate"
    assert _classify("x" * 3000)[1] == "complex"


def test_preset_defaults(monkeypatch):
    monkeypatch.delenv("CHUZOM_PRESET", raising=False)
    monkeypatch.delenv("CHUZOM_GATEWAY_URL", raising=False)
    monkeypatch.delenv("CHUZOM_GATEWAY_HOST", raising=False)
    monkeypatch.delenv("CHUZOM_GATEWAY_PORT", raising=False)
    from chuzom import presets
    presets.reload()
    assert presets.active_name() == "local"
    assert presets.bind() == ("127.0.0.1", 17900)
    assert presets.gateway_url().endswith("/v1")


def test_preset_from_yaml_and_env_override(tmp_path, monkeypatch):
    (tmp_path / "presets.yaml").write_text(
        "team:\n  gateway: http://10.0.0.5:17900/v1\n  host: 0.0.0.0\n  port: 18000\n")
    from chuzom import presets
    monkeypatch.setattr(presets, "PRESETS_FILE", tmp_path / "presets.yaml")
    presets.reload()
    monkeypatch.setenv("CHUZOM_PRESET", "team")
    monkeypatch.delenv("CHUZOM_GATEWAY_HOST", raising=False)
    monkeypatch.delenv("CHUZOM_GATEWAY_PORT", raising=False)
    monkeypatch.delenv("CHUZOM_GATEWAY_URL", raising=False)
    assert presets.bind() == ("0.0.0.0", 18000)
    assert presets.gateway_url() == "http://10.0.0.5:17900/v1"
    # env var overrides the preset
    monkeypatch.setenv("CHUZOM_GATEWAY_URL", "http://override/v1")
    assert presets.gateway_url() == "http://override/v1"
    presets.reload()
