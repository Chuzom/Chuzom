"""Regression: the public distribution must import without ``chuzom.enterprise``.

The wheel/sdist intentionally exclude ``src/chuzom/enterprise/`` (pyproject
``[tool.hatch.build.targets.sdist] exclude``). Public modules therefore MUST
guard their ``from chuzom.enterprise import ...`` statements with
``try/except ImportError`` — otherwise importing ``chuzom.server`` (the MCP
routing entrypoint) crashes for everyone who ``pip install``s the package.

This test runs in a subprocess with ``chuzom.enterprise`` forced absent to
simulate the public wheel, and asserts the core modules still import.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def test_public_modules_import_without_enterprise():
    code = textwrap.dedent(
        """
        import sys
        # Simulate the public distribution: enterprise/ is not shipped.
        sys.modules["chuzom.enterprise"] = None
        # These are the modules that import chuzom.enterprise at top level and
        # sit on the core routing / CLI / API import paths.
        import importlib

        # Modules that import chuzom.enterprise at top level and sit on the
        # core routing / CLI / API import paths.
        #
        # Imported by NAME rather than with `import x` statements so a module
        # that is absent for a DECLARED reason can be told apart from one that
        # fails on an unguarded enterprise import. This file is synced to a
        # downstream package that excludes admin_api and scim_api entirely;
        # there, a bare `import chuzom.admin_api` fails with
        # ModuleNotFoundError and reads as "an unguarded enterprise import
        # regressed", which is the opposite of what happened.
        #
        # The distinction is exact: ModuleNotFoundError naming the module
        # ITSELF means it was not shipped. Anything else — including a
        # ModuleNotFoundError naming chuzom.enterprise — is the regression
        # this test exists to catch, and still fails.
        for _name in (
            "chuzom.audit_routing",   # imported by chuzom.router
            "chuzom.router",
            "chuzom.server",          # MCP entrypoint
            "chuzom.rbac_routing",
            "chuzom.admin_api",
            "chuzom.scim_api",
            "chuzom.commands.audit",
        ):
            try:
                importlib.import_module(_name)
            except ModuleNotFoundError as exc:
                if exc.name == _name:
                    continue  # not shipped in this distribution — fine
                raise
        print("PUBLIC_IMPORT_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert "PUBLIC_IMPORT_OK" in result.stdout, (
        "Public import failed without chuzom.enterprise — an unguarded "
        f"enterprise import regressed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_critical_module_check_boots_without_enterprise():
    """The MCP server's _critical_modules_or_die() must not require chuzom.enterprise
    in the public (non-enterprise) profile — otherwise the published MCP server
    refuses to boot ('No module named chuzom.enterprise')."""
    code = textwrap.dedent(
        """
        import sys
        sys.modules["chuzom.enterprise"] = None  # simulate the public wheel
        from chuzom.server import _critical_modules_or_die
        _critical_modules_or_die()  # must NOT sys.exit / raise in non-enterprise profile
        print("CRITICAL_CHECK_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert "CRITICAL_CHECK_OK" in result.stdout, (
        "MCP critical-module check died without chuzom.enterprise — the public "
        f"MCP server would refuse to boot.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
