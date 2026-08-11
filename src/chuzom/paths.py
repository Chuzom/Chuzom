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
    """True when CHUZOM_HOME is redirecting state away from the real home.

    Exposed so a destructive test can *assert* its sandbox took effect instead
    of assuming it did — the assumption is what caused the incident.
    """
    return bool(os.environ.get(ENV_VAR, "").strip())
