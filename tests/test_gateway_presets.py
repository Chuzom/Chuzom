"""Gateway multi-protocol surface + preset resolution.

Deterministic (no network): asserts all wire-format routes are mounted and that
preset resolution honors env overrides and ~/.chuzom/presets.yaml.
"""



def test_gateway_mounts_all_formats():
    from chuzom.gateway import app
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/v1/chat/completions" in paths     # OpenAI
    assert "/v1/messages" in paths             # Anthropic
    assert "/api/chat" in paths                # Ollama chat
    assert "/api/generate" in paths            # Ollama generate
    assert "/healthz" in paths
    assert "/route" in paths                   # native (folded in from route_server)


# ── Consolidation: every endpoint goes through route_payload → route_and_call ──
def test_routed_result_adapter_normalizes_model():
    from chuzom.gateway import _RoutedResult
    # provider-prefixed model → bare model behind .model.model (no double prefix)
    r = _RoutedResult({"text": "hi", "provider": "ollama", "model": "ollama/hermes3:8b",
                       "input_tokens": 5, "output_tokens": 2})
    assert r.model.provider == "ollama"
    assert r.model.model == "hermes3:8b"
    assert f"{r.model.provider}/{r.model.model}" == "ollama/hermes3:8b"
    assert (r.text, r.input_tokens, r.output_tokens) == ("hi", 5, 2)
    # already-bare model is left as-is
    r2 = _RoutedResult({"provider": "openai", "model": "gpt-4o"})
    assert r2.model.model == "gpt-4o"


def test_all_endpoints_route_through_route_payload(monkeypatch):
    """OpenAI / Anthropic / Ollama / native /route must all funnel through the one
    route_payload core — so external callers uniformly get budget caps + the cap."""
    import chuzom.route_server as rs
    from chuzom.gateway import app

    calls = []

    def _fake_payload(payload):
        calls.append(payload)
        return {"text": "ok", "provider": "ollama", "model": "ollama/hermes3:8b",
                "cost_usd": 0.0, "input_tokens": 3, "output_tokens": 1, "complexity": "simple"}

    monkeypatch.setattr(rs, "route_payload", _fake_payload)

    from fastapi.testclient import TestClient
    client = TestClient(app)

    # native /route
    r = client.post("/route", json={"prompt": "hi"})
    assert r.status_code == 200 and r.json()["model"] == "ollama/hermes3:8b"

    # OpenAI
    r = client.post("/v1/chat/completions",
                    json={"model": "chuzom-auto", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "ok"
    assert r.json()["model"] == "ollama/hermes3:8b"

    # Anthropic
    r = client.post("/v1/messages",
                    json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200 and r.json()["content"][0]["text"] == "ok"

    # Ollama
    r = client.post("/api/generate", json={"prompt": "hi"})
    assert r.status_code == 200 and r.json()["response"] == "ok"

    # All four endpoints went through the single core.
    assert len(calls) == 4


def test_route_endpoint_missing_prompt_is_400(monkeypatch):
    from chuzom.gateway import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.post("/route", json={"prompt": "   "})
    assert r.status_code == 400


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
