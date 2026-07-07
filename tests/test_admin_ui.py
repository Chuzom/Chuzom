"""#51 — minimal admin UI over the admin API.

The UI is a single self-contained, read-only HTML shell served without auth
(it holds no secrets; the operator's bearer token is entered client-side and
kept only in sessionStorage). These tests assert the shell is served correctly
and stays self-contained + read-only — the data-plane authorization is already
covered by the endpoint tests the page consumes.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_api import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_ui_served_without_auth(client: TestClient) -> None:
    r = client.get("/v1/admin/ui")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


def test_ui_shell_renders(client: TestClient) -> None:
    body = client.get("/v1/admin/ui").text
    assert "<!doctype html>" in body.lower()
    assert 'data-testid="app-root"' in body
    assert 'data-testid="health-strip"' in body
    assert "Chuzom — Admin" in body


def test_ui_is_self_contained(client: TestClient) -> None:
    body = client.get("/v1/admin/ui").text
    # CSP-safe: no external scripts, stylesheets, or webfont/CDN references.
    assert "src=\"http" not in body
    assert "href=\"http" not in body
    assert "cdn" not in body.lower()
    assert "@font-face" not in body.lower()


def test_ui_references_the_endpoints_it_reads(client: TestClient) -> None:
    body = client.get("/v1/admin/ui").text
    for path in (
        "/v1/admin/health",
        "/v1/admin/audit/verify",
        "/v1/admin/agents/status",
        "/v1/admin/policy/versions",
        "/v1/admin/providers/disabled",
        "/v1/admin/models/disabled",
        "/v1/admin/admin-actions",
    ):
        assert path in body, f"UI does not reference {path}"


def test_ui_reads_verified_flag_not_ok(client: TestClient) -> None:
    # Regression guard: the audit endpoint returns {verified: bool}, NOT {ok}.
    # The routed draft checked payload.ok — this asserts the corrected contract.
    body = client.get("/v1/admin/ui").text
    assert "payload.verified === true" in body
    assert "payload.ok === true" not in body


def test_ui_is_read_only(client: TestClient) -> None:
    # No mutating verbs are issued from the browser in v1.
    body = client.get("/v1/admin/ui").text
    assert 'method: "GET"' in body
    for verb in ('method: "POST"', 'method: "DELETE"', 'method: "PUT"'):
        assert verb not in body
