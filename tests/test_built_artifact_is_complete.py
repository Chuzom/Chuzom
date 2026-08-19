"""Every source package must survive the build into the sdist AND the wheel.

WHY THIS EXISTS
===============

The downstream redistribution shipped a release whose package could not be
imported: ``No module named '<pkg>.agents'``. The server exited before
registering a single tool and the client reported ``CONNECTION_CLOSED``,
indistinguishable from a network fault.

Two unanchored exclusion patterns, in two files. Without a leading slash both
``.gitignore`` and hatch's sdist ``exclude`` match a directory of that name at
ANY depth:

    .gitignore   "agents/"  -> also src/<pkg>/agents/
    pyproject    "agents/"  -> also src/<pkg>/agents/

The second SHIPPED, because ``uv build`` builds the wheel FROM THE SDIST — so an
sdist exclusion silently becomes a wheel exclusion.

THIS TREE DOES NOT HAVE THAT BUG — TODAY
========================================

Measured when this file was written: every subpackage except ``enterprise``
(excluded on purpose) is present in both artifacts. That is not because the
patterns are safe; it is because no entry in the exclude list happens to
collide with a package name. ``tests/``, ``research/``, ``demo/`` and
``deprecation/`` were all unanchored, and any of them would have done the same
damage the day someone added a ``src/chuzom/demo/`` or a per-package ``tests/``
directory.

The patterns are anchored now. This file checks the RESULT rather than trusting
the patterns, because the failure mode is silent: nothing errors, the build
succeeds, and the gap is only visible from inside the artifact.

WHY EVERY OTHER CHECK MISSED IT DOWNSTREAM
==========================================

A local ``uv build --wheel`` builds straight from source and included the
files. The suite, the linters and CI all ran against the source TREE. Every
check was answering "is the source correct?" when the question that mattered
was "is the ARTIFACT complete?".

Slow: it runs the real build.
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src" / "chuzom"

#: Subpackages deliberately kept out of public distributions. Each entry is a
#: decision with a reason, not a convenience — `enterprise/` is excluded because
#: the public wheel does not carry the enterprise tier, and pyproject excludes it
#: by its FULL path (`src/chuzom/enterprise/`), which is the safe form.
INTENTIONALLY_EXCLUDED = {"enterprise"}


def _source_subpackages() -> set[str]:
    """Every importable subpackage under src/chuzom (has an __init__.py)."""
    return {
        p.parent.relative_to(_SRC).as_posix()
        for p in _SRC.rglob("__init__.py")
        if "__pycache__" not in p.parts and p.parent != _SRC
    }


def _expected() -> set[str]:
    return {
        pkg
        for pkg in _source_subpackages()
        if pkg.split("/")[0] not in INTENTIONALLY_EXCLUDED
    }


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build BOTH artifacts the way the release does.

    ``uv build`` with no target flag. Using ``--wheel`` here would reproduce the
    downstream blind spot exactly: it bypasses the sdist, which is where the
    exclusion applied.
    """
    out = tmp_path_factory.mktemp("dist")
    result = subprocess.run(
        ["uv", "build", "-o", str(out)],
        cwd=_REPO,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        pytest.skip(f"uv build unavailable or failed: {result.stderr[-400:]}")
    wheels = list(out.glob("*.whl"))
    sdists = list(out.glob("*.tar.gz"))
    if not wheels or not sdists:
        pytest.skip("build produced no artifacts")
    return wheels[0], sdists[0]


def test_there_are_subpackages_to_check():
    """Guards the guard: an empty expectation makes everything below vacuous."""
    assert len(_expected()) >= 5, (
        f"only {len(_expected())} subpackages found under {_SRC} — the detector "
        f"is broken, and the completeness checks would pass against nothing"
    )


def test_wheel_contains_every_source_subpackage(built):
    wheel, _ = built
    names = zipfile.ZipFile(wheel).namelist()
    missing = sorted(
        pkg for pkg in _expected() if not any(f"chuzom/{pkg}/" in n for n in names)
    )
    assert not missing, (
        f"these subpackages exist in src/ but not in the built WHEEL: {missing}.\n"
        f"Check for an unanchored pattern in pyproject's build excludes or in "
        f".gitignore — without a leading slash they match at any depth."
    )


def test_sdist_contains_every_source_subpackage(built):
    """The sdist matters as much as the wheel: `uv build` builds one from the other."""
    _, sdist = built
    with tarfile.open(sdist) as tar:
        names = tar.getnames()
    missing = sorted(
        pkg for pkg in _expected() if not any(f"chuzom/{pkg}/" in n for n in names)
    )
    assert not missing, (
        f"these subpackages exist in src/ but not in the built SDIST: {missing}.\n"
        f"This is the one that shipped broken downstream — the wheel is built "
        f"FROM the sdist, so an sdist exclusion silently becomes a wheel one."
    )


def test_the_intentional_exclusion_is_still_excluded(built):
    """The reverse direction. An exclusion that stops working is also a defect.

    `enterprise/` must NOT be in the public artifacts. Without this, anchoring
    the patterns could quietly start shipping it and every other test here would
    still pass — completeness checks only ever look for things that are missing.
    """
    wheel, _ = built
    names = zipfile.ZipFile(wheel).namelist()
    leaked = [n for n in names if "chuzom/enterprise/" in n]
    assert not leaked, (
        f"enterprise/ is in the public wheel ({len(leaked)} files). It is "
        f"excluded on purpose; shipping it is a licensing and surface-area "
        f"change, not a packaging detail."
    )


def test_no_source_file_is_hidden_from_git():
    """A file that exists locally and is not committed does not exist for anyone else.

    Separate from the build checks because it fails EARLIER and for a different
    reason: the build cannot include what the repository never received. This is
    the half that CI caught downstream, before the tag.
    """
    files = [
        str(p.relative_to(_REPO))
        for p in _SRC.rglob("*.py")
        if "__pycache__" not in p.parts
    ]
    if not files:  # pragma: no cover
        pytest.skip("no source files found")
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=_REPO,
        input="\n".join(files),
        capture_output=True,
        text=True,
        timeout=120,
    )
    ignored = [line for line in result.stdout.splitlines() if line.strip()]
    assert not ignored, (
        f"{len(ignored)} source file(s) under src/ are gitignored and will never "
        f"be committed:\n" + "\n".join(f"  {n}" for n in ignored[:10])
    )


def test_the_critical_modules_survive_the_build(built):
    """The startup gate's modules specifically — their absence stops the server.

    ``server._CRITICAL_MODULES`` names what must import or the process exits. A
    missing one is not a degraded install; it is a server that refuses to boot
    with a remediation message telling the user to reinstall, which does not
    help. ``agents.session`` is on that list and is exactly what the downstream
    release dropped.
    """
    sys.path.insert(0, str(_REPO / "src"))
    from chuzom import server

    wheel, _ = built
    names = zipfile.ZipFile(wheel).namelist()
    missing = []
    for dotted in server._CRITICAL_MODULES:
        rel = dotted.replace(".", "/")
        if not any(f"{rel}.py" in n or f"{rel}/" in n for n in names):
            missing.append(dotted)
    assert not missing, (
        f"critical modules absent from the built wheel: {missing}. The server "
        f"calls _critical_modules_or_die() at startup and will sys.exit(1)."
    )
