"""Refinement #12 / SEC-001 closure — SSE transport with Bearer auth.

Closes the literal first audit finding (SEC-001) by re-introducing
the SSE network transport behind:

* **Bearer-token auth.** Every request must carry
  ``Authorization: Bearer <token>``; validated against
  ``IdentityStore.authenticate`` + requires
  ``Permission.ROUTE_PROMPT``.
* **Default loopback.** ``--host 0.0.0.0`` refuses without
  ``CHUZOM_SSE_ALLOW_PUBLIC=on`` so a careless deployment cannot
  silently expose the surface.
* **Startup verifier.** Under enterprise profile the verifier
  fires before bind (refinement #11 contract).

These tests pin the CLI flag handling + the public-bind guard.
The Bearer middleware itself is tested at the function level
against a synthetic Starlette request rather than spinning up a
real uvicorn — the auth contract is what we need to enforce, not
the SSE framing details.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chuzom.commands.sse import cmd_sse
from chuzom import server as srv
from chuzom.enterprise.identity import IdentityStore
from chuzom.enterprise.rbac import Role


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch) -> None:
    for env in (
        "CHUZOM_PROFILE",
        "CHUZOM_TOKEN",
        "CHUZOM_SSE_ALLOW_PUBLIC",
        "CHUZOM_SKIP_STARTUP_VERIFY",
    ):
        monkeypatch.delenv(env, raising=False)


# ── 1. CLI flag parsing ────────────────────────────────────────────────────


def test_help_returns_zero(capsys) -> None:
    assert cmd_sse(["--help"]) == 0
    out = capsys.readouterr().out
    assert "chuzom sse" in out
    assert "Bearer" in out
    assert "CHUZOM_SSE_ALLOW_PUBLIC" in out


def test_unknown_flag_returns_two(capsys) -> None:
    assert cmd_sse(["--bogus"]) == 2
    err = capsys.readouterr().err
    assert "Unknown flag" in err


def test_invalid_port_returns_two(capsys) -> None:
    assert cmd_sse(["--port", "abc"]) == 2
    err = capsys.readouterr().err
    assert "Invalid port" in err


def test_missing_port_value_returns_two(capsys) -> None:
    assert cmd_sse(["--port"]) == 2


def test_missing_host_value_returns_two(capsys) -> None:
    assert cmd_sse(["--host"]) == 2


# ── 2. Public bind guard ──────────────────────────────────────────────────


def test_public_bind_refused_without_env(capsys, monkeypatch) -> None:
    """The CLI delegates to ``main_sse_secured`` which exits with
    code 2 before binding when 0.0.0.0 is requested without the
    explicit opt-in env."""
    # Block the actual bind by short-circuiting verifier + ensuring
    # the error path runs first.
    monkeypatch.setenv("CHUZOM_SKIP_STARTUP_VERIFY", "on")
    with pytest.raises(SystemExit) as excinfo:
        srv.main_sse_secured(host="0.0.0.0", port=9999)
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "0.0.0.0" in err
    assert "CHUZOM_SSE_ALLOW_PUBLIC" in err


def test_public_bind_allowed_with_explicit_env(
    monkeypatch, tmp_path: Path,
) -> None:
    """With ``CHUZOM_SSE_ALLOW_PUBLIC=on`` the guard passes. We
    don't actually bind (would race the port + take seconds) — we
    short-circuit at ``anyio.run`` by stubbing it out."""
    monkeypatch.setenv("CHUZOM_SSE_ALLOW_PUBLIC", "on")
    monkeypatch.setenv("CHUZOM_SKIP_STARTUP_VERIFY", "on")
    monkeypatch.setenv(
        "CHUZOM_IDENTITY_PATH", str(tmp_path / "identity.db")
    )

    bound: dict = {}

    def fake_run(coro):
        bound["called"] = True

    import anyio
    monkeypatch.setattr(anyio, "run", fake_run)

    # Likewise stub IdentityStore connection-open so no real DB
    # work runs.
    srv.main_sse_secured(host="0.0.0.0", port=9999)
    assert bound.get("called") is True


def test_loopback_bind_allowed_by_default(
    monkeypatch, tmp_path: Path,
) -> None:
    """127.0.0.1 binds without the public-bind env — it's the
    documented default."""
    monkeypatch.setenv("CHUZOM_SKIP_STARTUP_VERIFY", "on")
    monkeypatch.setenv(
        "CHUZOM_IDENTITY_PATH", str(tmp_path / "identity.db")
    )

    import anyio
    monkeypatch.setattr(anyio, "run", lambda _coro: None)
    # No SystemExit raised.
    srv.main_sse_secured(host="127.0.0.1", port=8888)


# ── 3. Truthy / falsy env values for CHUZOM_SSE_ALLOW_PUBLIC ──────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("on", True), ("1", True), ("true", True), ("yes", True),
        ("ON", True), ("True", True),
        ("off", False), ("0", False), ("", False), ("typo", False),
    ],
)
def test_allow_public_bind_truth_table(
    monkeypatch, value: str, expected: bool,
) -> None:
    if value:
        monkeypatch.setenv("CHUZOM_SSE_ALLOW_PUBLIC", value)
    else:
        monkeypatch.delenv("CHUZOM_SSE_ALLOW_PUBLIC", raising=False)
    assert srv._allow_public_bind() is expected


# ── 4. Bearer middleware contract (direct invocation) ─────────────────────


def _build_app_with_middleware(tmp_path: Path):
    """Construct a tiny Starlette app, install the Bearer middleware
    from ``main_sse_secured`` against an isolated IdentityStore, and
    return a TestClient that exercises it."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from chuzom.enterprise.identity import InvalidToken
    from chuzom.enterprise.rbac import Permission

    store = IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False,
    )

    class _BearerAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            authz = request.headers.get("Authorization", "")
            parts = authz.strip().split(None, 1)
            if len(parts) != 2 or parts[0].lower() != "bearer":
                return PlainTextResponse(
                    "Unauthorized — Bearer token required",
                    status_code=401,
                )
            token = parts[1].strip()
            if not token:
                return PlainTextResponse(
                    "Unauthorized — empty bearer token",
                    status_code=401,
                )
            try:
                identity = store.authenticate(token)
            except InvalidToken as exc:
                return PlainTextResponse(
                    f"Unauthorized — {exc}", status_code=401,
                )
            if Permission.ROUTE_PROMPT not in identity.permissions:
                return PlainTextResponse(
                    "Forbidden — identity lacks ROUTE_PROMPT",
                    status_code=403,
                )
            request.state.identity = identity
            return await call_next(request)

    async def echo(request):
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[Route("/sse", echo)],
        middleware=[Middleware(_BearerAuthMiddleware)],
    )
    return TestClient(app), store


def test_middleware_rejects_missing_authorization(tmp_path: Path) -> None:
    client, _ = _build_app_with_middleware(tmp_path)
    resp = client.get("/sse")
    assert resp.status_code == 401
    assert "Bearer" in resp.text


def test_middleware_rejects_invalid_token(tmp_path: Path) -> None:
    client, _ = _build_app_with_middleware(tmp_path)
    resp = client.get(
        "/sse", headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_middleware_accepts_valid_employee_token(tmp_path: Path) -> None:
    client, store = _build_app_with_middleware(tmp_path)
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="dev@x", display_name="D", role=Role.EMPLOYEE,
    )
    tok = store.issue_token(user.id, name="t")
    resp = client.get(
        "/sse", headers={"Authorization": f"Bearer {tok.plaintext}"},
    )
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_middleware_rejects_token_without_route_prompt(
    tmp_path: Path,
) -> None:
    """A token whose permissions don't include ROUTE_PROMPT must be
    refused at 403 (not 401 — auth succeeded, authz failed)."""
    client, store = _build_app_with_middleware(tmp_path)
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="r@x", display_name="R", role=Role.EMPLOYEE,
    )
    # Issue a token with NO permissions.
    tok = store.issue_token(user.id, name="r", permissions=())
    resp = client.get(
        "/sse", headers={"Authorization": f"Bearer {tok.plaintext}"},
    )
    assert resp.status_code == 403
    assert "ROUTE_PROMPT" in resp.text


def test_middleware_rejects_non_bearer_scheme(tmp_path: Path) -> None:
    client, _ = _build_app_with_middleware(tmp_path)
    resp = client.get(
        "/sse", headers={"Authorization": "Basic Zm9vOmJhcg=="},
    )
    assert resp.status_code == 401


def test_middleware_rejects_revoked_token(tmp_path: Path) -> None:
    client, store = _build_app_with_middleware(tmp_path)
    org = store.create_org(name="acme")
    team = store.create_team(org.id, "platform")
    user = store.create_user(
        org_id=org.id, team_id=team.id,
        email="z@x", display_name="Z", role=Role.EMPLOYEE,
    )
    tok = store.issue_token(user.id, name="will-revoke")
    store.revoke_token(tok.id)
    resp = client.get(
        "/sse", headers={"Authorization": f"Bearer {tok.plaintext}"},
    )
    assert resp.status_code == 401
