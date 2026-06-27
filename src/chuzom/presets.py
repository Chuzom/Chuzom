"""Named infra presets — endpoint / providers / profile per environment.

Resolved from ``~/.chuzom/presets.yaml`` and selected by ``CHUZOM_PRESET``
(default ``local``). Both the gateway and any client read their endpoint from
here, so no URL is hardcoded and a user can swap infra (laptop / team server /
cloud) by flipping one env var. Individual env vars still override the preset.

Example ~/.chuzom/presets.yaml:

    local:       {gateway: "http://127.0.0.1:17900/v1", host: 127.0.0.1, port: 17900, profile: budget}
    team-server: {gateway: "http://10.0.0.5:17900/v1",  host: 0.0.0.0,   port: 17900, profile: balanced}
    cloud:       {gateway: "https://chuzom.internal/v1", profile: premium}
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

PRESETS_FILE = Path.home() / ".chuzom" / "presets.yaml"

# Built-in fallback so things work with no presets.yaml present.
_DEFAULTS: dict[str, dict] = {
    "local": {
        "gateway": "http://127.0.0.1:17900/v1",
        "host": "127.0.0.1",
        "port": 17900,
        "providers": ["ollama", "gemini"],
        "profile": "budget",
    },
}


@functools.lru_cache(maxsize=1)
def _load() -> dict[str, dict]:
    presets = {k: dict(v) for k, v in _DEFAULTS.items()}
    if PRESETS_FILE.exists():
        try:
            import yaml
            loaded = yaml.safe_load(PRESETS_FILE.read_text()) or {}
            if isinstance(loaded, dict):
                for name, cfg in loaded.items():
                    if isinstance(cfg, dict):
                        presets[name] = {**presets.get(name, {}), **cfg}
        except Exception:
            pass  # malformed presets.yaml → fall back to defaults
    return presets


def reload() -> None:
    """Drop the cache (after editing presets.yaml)."""
    _load.cache_clear()


def active_name() -> str:
    return os.environ.get("CHUZOM_PRESET", "local")


def active() -> dict:
    presets = _load()
    return presets.get(active_name(), presets["local"])


def gateway_url() -> str:
    """Endpoint clients should POST to. Env override wins over the preset."""
    return os.environ.get("CHUZOM_GATEWAY_URL") or active().get(
        "gateway", "http://127.0.0.1:17900/v1")


def bind() -> tuple[str, int]:
    """(host, port) the gateway server should bind. Env overrides win."""
    p = active()
    host = os.environ.get("CHUZOM_GATEWAY_HOST") or p.get("host", "127.0.0.1")
    port = int(os.environ.get("CHUZOM_GATEWAY_PORT") or p.get("port", 17900))
    return host, port
