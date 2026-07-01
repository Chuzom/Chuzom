# SPDX-License-Identifier: MIT
"""Per-user install of the Chuzom OpenAI-compatible gateway as a background service.

The gateway (``python -m chuzom.gateway``) lets any OPENAI_BASE_URL client route
through Chuzom. Keeping it always-on needs a service definition — but that
definition must point at *this* machine's interpreter and home, not a checked-in
absolute path. This module renders the launchd plist (macOS) or systemd user unit
(Linux) from ``sys.executable`` + ``Path.home()`` so it works on any clone.

    python -m chuzom.gateway_service      # write the service file for this user
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

LABEL = "com.chuzom.gateway"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17900


def render_launchd_plist(
    python: str, home: Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> str:
    """macOS launchd agent, paths resolved for the given interpreter/home."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>chuzom.gateway</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>CHUZOM_GATEWAY_HOST</key><string>{host}</string>
        <key>CHUZOM_GATEWAY_PORT</key><string>{port}</string>
    </dict>
    <key>KeepAlive</key><true/>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>{home}/.chuzom/gateway.out.log</string>
    <key>StandardErrorPath</key><string>{home}/.chuzom/gateway.err.log</string>
</dict>
</plist>
"""


def render_systemd_user_unit(
    python: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> str:
    """Linux systemd *user* unit (runs as the invoking user, no root needed)."""
    return f"""[Unit]
Description=Chuzom OpenAI-compatible gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python} -m chuzom.gateway
Environment=CHUZOM_GATEWAY_HOST={host}
Environment=CHUZOM_GATEWAY_PORT={port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def gateway_service_target(system: str | None = None) -> tuple[Path, str]:
    """Return (destination path, activation command) for the current platform."""
    system = system or platform.system()
    if system == "Darwin":
        dest = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        return dest, f"launchctl load {dest}"
    if system == "Linux":
        dest = Path.home() / ".config" / "systemd" / "user" / "chuzom-gateway.service"
        return dest, "systemctl --user daemon-reload && systemctl --user enable --now chuzom-gateway"
    raise RuntimeError(
        f"Automatic gateway-service install is not supported on {system!r}; "
        "run `python -m chuzom.gateway` under your own supervisor."
    )


def install_gateway_service(
    python: str | None = None, *, system: str | None = None, write: bool = True
) -> tuple[Path, str]:
    """Render and (by default) write the per-user gateway service file.

    Returns (path, activation_command). Does NOT auto-load the service — writing
    the file is reversible; loading it starts a daemon, so that stays an explicit
    step the caller runs.
    """
    python = python or sys.executable
    system = system or platform.system()
    dest, activate = gateway_service_target(system)
    content = (
        render_launchd_plist(python, Path.home())
        if system == "Darwin"
        else render_systemd_user_unit(python)
    )
    if write:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
    return dest, activate


def main() -> None:
    dest, activate = install_gateway_service()
    print(f"Wrote Chuzom gateway service for this user:\n  {dest}\n")
    print(f"Activate it with:\n  {activate}")


if __name__ == "__main__":
    main()
