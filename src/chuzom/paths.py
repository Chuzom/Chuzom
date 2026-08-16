"""RED2-07 — one resolver for the chuzom state directory, honouring CHUZOM_HOME.

`CHUZOM_HOME` looked like the way to point chuzom at a scratch directory. It was
not: nothing read it. ~149 call sites compute ``Path.home() / ".chuzom"``
directly, and ``config.chuzom_db_path`` was worse than that — a field default
evaluated at *class definition* time, so it froze the real home directory at
import and could not be redirected afterwards even by monkeypatching
``Path.home()``.

This is not a tidiness complaint. During the audit a test that believed it was
sandboxed by `CHUZOM_HOME` wrote to the operator's real `~/.chuzom/usage.db` and
destroyed live data (`evidence/AUDITOR_INCIDENT.md`). A safety mechanism that
silently does nothing is more dangerous than no mechanism, because people rely
on it.

Resolution order:

1. ``CHUZOM_HOME`` if set — read at CALL time, never cached, so a test that sets
   it after import still gets isolation. Caching here would reintroduce exactly
   the freeze that caused the incident.
2. ``~/.chuzom`` otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "CHUZOM_HOME"


def chuzom_home() -> Path:
    """The chuzom state directory. Resolved on every call, deliberately."""
    override = os.environ.get(ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".chuzom"


def state_path(*parts: str) -> Path:
    """A path inside the chuzom state directory, e.g. ``state_path("usage.db")``."""
    return chuzom_home().joinpath(*parts)


def is_isolated() -> bool:
    """True when ``CHUZOM_HOME`` is set and this module will honour it.

    SCOPE — READ THIS BEFORE TRUSTING IT (audit #37).

    This asserts one thing only: that ``chuzom_home()`` and ``state_path()`` will
    resolve under ``CHUZOM_HOME``. It does **not** certify that the process as a
    whole is sandboxed, because most of the codebase does not ask this module
    where state lives.

    Surveyed 2026-08-15: **120 sites in ``src/chuzom/`` compose ``~/.chuzom``
    directly**, plus 55 more in ``src/chuzom/hooks/`` which run as separate
    processes. ``usage.db`` alone is resolved ~23 different ways. Four modules
    honour an override, and each honours a *different* variable
    (``CHUZOM_STATE_DIR``, ``CHUZOM_EXECUTION_LEDGER_DB``, ``CHUZOM_CP_AUDIT_PATH``,
    ``CHUZOM_DB_PATH``); none honours ``CHUZOM_HOME``.

    So a test that asserts ``is_isolated()`` and then exercises a module which
    resolves its own path is **not** protected. That is not hypothetical: it is
    exactly how ``session_store.py`` read the operator's real session content while
    a test believed it was sandboxed, and how the incident in
    ``evidence/AUDITOR_INCIDENT.md`` destroyed live data.

    Assert it to check YOUR OWN writes go through ``state_path()``. Do not read it
    as "nothing can escape". The honest name for what this returns is "the
    canonical resolver is redirected", and narrowing the claim is the point of this
    docstring — a guard that over-claims is how a local bug becomes a silent one.
    """
    return bool(os.environ.get(ENV_VAR, "").strip())
