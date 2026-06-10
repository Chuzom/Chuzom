"""G-006-F1 admin-api command — start the enterprise admin API.

Default endpoint: ``http://127.0.0.1:7339`` — deliberately distinct
from the developer-facing dashboard (7337) because the audiences,
auth models, and risk profiles differ. The dashboard is read-only
stats for individual developers; the admin API is RBAC-gated
mutation for platform operators.

Usage::

    chuzom admin-api                        — bind 127.0.0.1:7339
    chuzom admin-api --port 7340            — custom port
    chuzom admin-api --host 0.0.0.0         — bind all interfaces
    chuzom admin-api --help                 — print this help

Security note: ``--host 0.0.0.0`` exposes the API on every reachable
interface. The API is RBAC-gated (every mutating endpoint requires
a valid bearer token + ``MANAGE_*`` permission), but a careless
deployment can still leak the OpenAPI surface. Pair with a reverse
proxy that enforces transport security, IP allow-list, and additional
authentication if you bind to a public interface.

See: ``src/chuzom/admin_api.py`` for the surface and
``docs/audit/post-remediation/GAP_ANALYSIS.md`` G-006.
"""
from __future__ import annotations

import sys


_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7339


def _print_help() -> None:
    """Print usage. Kept as a function so tests can capture stdout."""
    print(
        "chuzom admin-api — start the enterprise admin API\n"
        "\n"
        "Options:\n"
        "  --host HOST   bind interface (default: 127.0.0.1)\n"
        "  --port PORT   bind port (default: 7339)\n"
        "  --help, -h    show this message and exit\n"
        "\n"
        "Default endpoint: http://127.0.0.1:7339\n"
        "OpenAPI docs:     /docs (Swagger UI) and /redoc\n"
        "\n"
        "See docs/audit/post-remediation/GAP_ANALYSIS.md G-006."
    )


def cmd_admin_api(args: list[str]) -> int:
    """Execute: ``chuzom admin-api [--host HOST] [--port PORT]``.

    Parses flags, then starts uvicorn against ``admin_api:create_app()``.
    Returns ``1`` for invalid input or missing uvicorn dependency,
    ``0`` for ``--help`` / clean shutdown (uvicorn blocks until killed).
    """
    host = _DEFAULT_HOST
    port = _DEFAULT_PORT

    i = 0
    while i < len(args):
        flag = args[i]
        if flag in ("--help", "-h"):
            _print_help()
            return 0
        if flag == "--host":
            if i + 1 >= len(args):
                print("--host requires a value", file=sys.stderr)
                return 1
            host = args[i + 1]
            i += 2
            continue
        if flag == "--port":
            if i + 1 >= len(args):
                print("--port requires a value", file=sys.stderr)
                return 1
            try:
                port = int(args[i + 1])
            except ValueError:
                print(
                    f"Invalid port: {args[i + 1]!r}", file=sys.stderr
                )
                return 1
            i += 2
            continue
        print(f"Unknown flag: {flag!r}", file=sys.stderr)
        return 1

    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is required to run the admin API. "
            "It is listed in chuzom-router's dependencies; "
            "ensure your installation is current.",
            file=sys.stderr,
        )
        return 1

    from chuzom.admin_api import create_app

    app = create_app()
    print(
        f"Chuzom admin API starting on http://{host}:{port} "
        f"— OpenAPI at /docs (G-006 skeleton)"
    )
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0
