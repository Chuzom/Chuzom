from __future__ import annotations

import httpx


class CPClient:
    def __init__(
        self,
        cp_url: str,
        *,
        sidecar_token: str | None = None,
        timeout: float = 5.0,
        transport=None,
    ):
        cp_url = cp_url.rstrip("/")
        self._sidecar_token = sidecar_token
        self._client = httpx.Client(
            base_url=cp_url,
            timeout=timeout,
            transport=transport,
        )

    def get_current_policy(self, tenant_id: str) -> dict:
        headers = {}
        if self._sidecar_token is not None:
            headers["Authorization"] = f"Bearer {self._sidecar_token}"

        resp = self._client.get(
            f"/cp/v1/tenants/{tenant_id}/policy/current",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self._client.close()


__all__ = ["CPClient"]
