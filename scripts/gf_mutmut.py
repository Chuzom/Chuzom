#!/usr/bin/env python3
"""Run mutmut over G-F's scope without disturbing Gate 13's config.

Protocol doc 20, Phase 0. Every result records the commit SHA, the exact command
line, the environment and the universe hash — reproducibility is the point, and a
mutation score whose provenance is unrecorded is not evidence.

WHY A SWAP
----------
mutmut 3.6 resolves config in `configuration.py::_config_reader`:

    1. pyproject.toml [tool.mutmut]   -- if present, setup.cfg is IGNORED ENTIRELY
    2. else setup.cfg [mutmut]

There is no `--config` flag and no support for a second named section. So the
obvious way to add a second configuration — `[tool.mutmut]` in pyproject.toml —
would have **silently disabled** the Gate-13 scope that lives in setup.cfg,
rather than sitting alongside it. mutmut would then have run cheerfully over the
wrong files and reported a score, which is the failure mode this whole audit
exists to remove.

So: swap `config/mutmut_gf.cfg` into `setup.cfg`, run, and restore the original
**byte-for-byte** in a `finally`. The restore is verified by hash, and
`tests/test_gate13_mutmut_config_intact.py` fails if a crashed run ever leaves
the wrong config in place.

This deliberately breaks the session rule "do not change a measuring instrument
mid-measurement" in a narrow, bounded way: the swap happens *before* the
measurement starts and is undone *after* it ends, never during. The hash check
is what makes that claim checkable rather than asserted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SETUP_CFG = REPO / "setup.cfg"
GF_CFG = REPO / "config" / "mutmut_gf.cfg"
PYPROJECT = REPO / "pyproject.toml"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()


def _assert_pyproject_would_not_hijack() -> None:
    """If pyproject gains [tool.mutmut], setup.cfg stops being read at all.

    Checked every run rather than assumed: a future contributor adding that
    section would silently redirect BOTH this run and Gate 13's, and nothing
    else in the repo would notice.
    """
    if "[tool.mutmut]" in PYPROJECT.read_text():
        sys.exit(
            "REFUSING TO RUN: pyproject.toml now has a [tool.mutmut] section.\n"
            "mutmut prefers it and IGNORES setup.cfg entirely, so this swap would\n"
            "have no effect and the scope would silently be someone else's.\n"
            "Remove it, or rework this script to write pyproject instead."
        )


def run(extra_args: list[str], out_dir: Path) -> int:
    _assert_pyproject_would_not_hijack()

    original = SETUP_CFG.read_text()
    original_hash = _sha256(original)
    gf_config = GF_CFG.read_text()

    started = time.time()
    cmd = [str(REPO / ".venv" / "bin" / "mutmut"), "run", *extra_args]

    try:
        SETUP_CFG.write_text(gf_config)
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        stdout = proc.stdout
        rc = proc.returncode
    finally:
        # Restore FIRST, then verify. If this raises, the guard test catches it
        # on the next suite run; leaving Gate 13's config swapped out silently
        # is the one outcome that must not happen.
        SETUP_CFG.write_text(original)
        restored = _sha256(SETUP_CFG.read_text())
        if restored != original_hash:
            sys.exit(
                f"CRITICAL: setup.cfg was not restored byte-for-byte "
                f"({original_hash[:12]} -> {restored[:12]}). Gate 13's config may "
                "be damaged; restore it from git before doing anything else."
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    # Strip the spinner glyphs mutmut writes; they make the log unreadable and
    # balloon it to ~100KB of animation frames.
    clean = "".join(c for c in stdout if c not in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
    (out_dir / "mutmut_stdout.txt").write_text(clean)

    meta = {
        "commit_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "command": " ".join(cmd),
        "config_source": str(GF_CFG.relative_to(REPO)),
        "config_sha256": _sha256(gf_config),
        "setup_cfg_restored_sha256": original_hash,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "mutmut_version": _git_pkg_version("mutmut"),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "elapsed_sec": round(time.time() - started, 1),
        "returncode": rc,
    }
    (out_dir / "run_metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    return rc


def _git_pkg_version(pkg: str) -> str:
    try:
        from importlib.metadata import version

        return version(pkg)
    except Exception as exc:  # noqa: BLE001 — provenance must not break the run
        return f"unknown ({exc})"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="mutmut over G-F scope (Gate 13 untouched)")
    ap.add_argument("--out", default=".chuzom/gf/latest", help="artefact directory")
    ap.add_argument("mutmut_args", nargs="*", help="passed through to `mutmut run`")
    ns = ap.parse_args()
    sys.exit(run(ns.mutmut_args, REPO / ns.out))
