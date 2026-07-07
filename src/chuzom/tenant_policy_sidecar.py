from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from chuzom.control_plane.client import CPClient
from chuzom.control_plane.policy_bundle import (
    bundle_payload_bytes,
    make_payload,
    runtime_policy_from_payload,
)
from chuzom.control_plane.signing import SigningKeyError, verify_payload
from chuzom.policy import OrgPolicy as RuntimeOrgPolicy


class SignatureVerificationError(Exception):
    pass


class NoUsablePolicyError(Exception):
    pass


@dataclass(frozen=True)
class TenantPolicySidecarConfig:
    tenant_id: str
    cp_url: str
    trusted_public_key_b64: str
    cache_dir: Path
    instance_id: str = "sidecar"


class PolicyCache:
    def __init__(self, cache_dir: Path, tenant_id: str):
        self.path = cache_dir / tenant_id / "policy-lkg.json"

    def save(self, response: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f"{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(response, f)
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def load(self) -> dict | None:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        if not isinstance(loaded, dict):
            return None
        return loaded


class TenantPolicySidecar:
    def __init__(
        self,
        config: TenantPolicySidecarConfig,
        *,
        client: CPClient | None = None,
    ):
        self.config = config
        self._client = client or CPClient(config.cp_url)
        self._cache = PolicyCache(config.cache_dir, config.tenant_id)

    def _verify_and_extract(self, response: dict) -> RuntimeOrgPolicy:
        if response.get("public_key_b64") != self.config.trusted_public_key_b64:
            raise SignatureVerificationError(
                "served public key does not match pinned key"
            )

        payload = make_payload(
            tenant_id=response["tenant_id"],
            version=response["version"],
            issued_at=response["created_at"],
            yaml_text=response["yaml_text"],
        )
        try:
            ok = verify_payload(
                self.config.trusted_public_key_b64,
                bundle_payload_bytes(payload),
                response["signature_b64"],
            )
        except SigningKeyError as exc:
            raise SignatureVerificationError("bundle signature invalid") from exc
        if not ok:
            raise SignatureVerificationError("bundle signature invalid")
        return runtime_policy_from_payload(payload)

    def pull_once(self) -> RuntimeOrgPolicy:
        try:
            response = self._client.get_current_policy(self.config.tenant_id)
            policy = self._verify_and_extract(response)
            self._cache.save(response)
            return policy
        except SignatureVerificationError:
            raise
        except Exception as exc:
            cached = self._cache.load()
            if cached is None:
                raise NoUsablePolicyError("no usable policy available") from exc
            return self._verify_and_extract(cached)

    def heartbeat_payload(
        self, *, effective_version, effective_digest, source, last_apply_latency_ms=None
    ) -> dict:
        return {
            "instance_id": self.config.instance_id,
            "effective_version": effective_version,
            "effective_digest": effective_digest,
            "source": source,
            "sidecar_version": "0.1.0",
            "last_apply_latency_ms": last_apply_latency_ms,
        }

    def send_heartbeat(
        self, *, effective_version, effective_digest, source, last_apply_latency_ms=None
    ) -> dict:
        """Report this instance's effective policy version to the control plane."""
        payload = self.heartbeat_payload(
            effective_version=effective_version, effective_digest=effective_digest,
            source=source, last_apply_latency_ms=last_apply_latency_ms,
        )
        return self._client.post_heartbeat(self.config.tenant_id, payload)

    def close(self):
        self._client.close()


__all__ = [
    "TenantPolicySidecarConfig",
    "TenantPolicySidecar",
    "PolicyCache",
    "SignatureVerificationError",
    "NoUsablePolicyError",
]
