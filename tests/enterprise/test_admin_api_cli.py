"""G-006-F1 — admin-api CLI command wiring.

We do not start a real uvicorn server in tests (that would bind a
port and block). These tests cover argument parsing and exit codes
for the public entry point. The uvicorn invocation itself is
exercised by manual smoke tests after install.
"""
from __future__ import annotations


from chuzom.commands.admin_api import cmd_admin_api


def test_help_flag_returns_zero_and_prints_usage(capsys) -> None:
    assert cmd_admin_api(["--help"]) == 0
    out = capsys.readouterr().out
    assert "admin api" in out.lower() or "admin-api" in out.lower()
    assert "--port" in out
    assert "--host" in out


def test_short_help_flag_also_works(capsys) -> None:
    assert cmd_admin_api(["-h"]) == 0
    assert "--port" in capsys.readouterr().out


def test_invalid_port_returns_one(capsys) -> None:
    assert cmd_admin_api(["--port", "not-a-number"]) == 1
    err = capsys.readouterr().err
    assert "invalid port" in err.lower()


def test_missing_port_value_returns_one(capsys) -> None:
    assert cmd_admin_api(["--port"]) == 1
    assert "--port requires a value" in capsys.readouterr().err.lower()


def test_missing_host_value_returns_one(capsys) -> None:
    assert cmd_admin_api(["--host"]) == 1
    assert "--host requires a value" in capsys.readouterr().err.lower()


def test_unknown_flag_returns_one(capsys) -> None:
    assert cmd_admin_api(["--bogus-flag"]) == 1
    err = capsys.readouterr().err
    assert "unknown flag" in err.lower()


def test_valid_flags_invoke_uvicorn(monkeypatch, capsys) -> None:
    """Patch uvicorn.run; confirm host/port flow through.

    We intercept ``uvicorn.run`` so the test doesn't actually bind
    a port; the assertion is that our flag parsing produced the
    expected kwargs.
    """
    captured: dict[str, object] = {}

    def fake_run(app, *, host: str, port: int, log_level: str = "info") -> None:
        captured["host"] = host
        captured["port"] = port
        captured["log_level"] = log_level

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)
    rc = cmd_admin_api(["--host", "0.0.0.0", "--port", "8080"])
    assert rc == 0
    assert captured == {"host": "0.0.0.0", "port": 8080, "log_level": "info"}


def test_default_host_and_port_when_no_flags(monkeypatch) -> None:
    """No flags → 127.0.0.1:7339 (distinct from dashboard's 7337)."""
    captured: dict[str, object] = {}

    def fake_run(app, *, host: str, port: int, log_level: str = "info") -> None:
        captured["host"] = host
        captured["port"] = port

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert cmd_admin_api([]) == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 7339
