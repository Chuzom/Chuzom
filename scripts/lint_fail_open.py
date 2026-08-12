#!/usr/bin/env python3
"""CHZ-FO-01 — no SILENT broad catch in the money/routing/verification paths.

RED8-09. ~810 broad `except Exception` handlers exist across the codebase and
most of them are correct: a UserPromptSubmit hook that raises kills the user's
turn, and a telemetry write that raises turns observability into an outage.
Removing them would trade a known degradation for a crash.

The defect is not the catch. It is the SILENCE. A handler ending in bare `pass`
is indistinguishable from the happy path in every surface we have — the same
shape as the ledger drop that looked like no traffic, the routing bypass that
looked like a clean run, and the savings query failure that rendered "$0.00
saved". A caught exception is information, and discarding it converts a known
failure into an unknown one.

So this lint does not ban broad catches. It bans catches that leave NO TRACE, and
only in the modules where a silent degradation costs money or corrupts a routing
decision. Elsewhere the pattern is deliberate and stays.

Zero tolerance, no baseline: WP-13's acceptance criterion names these five
modules explicitly, and a baseline here would be a list of exactly the places the
criterion says must be empty.

Exit 0 clean, 1 on any finding.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: WP-13's protected set. A silent failure in any of these either mis-reports
#: money or silently changes a routing decision.
PROTECTED = (
    "src/chuzom/cost.py",
    "src/chuzom/router.py",
    "src/chuzom/execution_ledger.py",
    "src/chuzom/dashboard_data.py",
    "src/chuzom/summary.py",
)

#: A handler is "traced" if its body does any of these. Deliberately broad --
#: the bar is "leaves evidence somewhere", not "uses our preferred helper", so a
#: pre-existing log call counts and nobody has to churn working code to satisfy
#: a lint.
#:
#: KNOWN LIMIT, stated rather than hidden: this matches on the CALLED NAME, so
#: `from chuzom.failopen import record as _fo; _fo(...)` reads as untraced, and
#: conversely a local helper called `log_nothing()` would read as traced. Found
#: the hard way -- the first fixes in this very work package aliased the import
#: and the lint did not count them.
#:
#: Not fixed by chasing aliases through the AST, because that trades a visible
#: limit for an invisible one: the check would then look complete while still
#: missing indirection through a wrapper, a dict dispatch, or a decorator. A
#: name-matching lint whose limit is documented is honest; one that appears
#: exhaustive is the shape this audit keeps finding. Call sites use the canonical
#: `failopen.record(...)`, which is also what makes an event code greppable.
_TRACE_CALLS = (
    "record",          # chuzom.failopen.record
    "log", "logger", "warning", "error", "info", "debug", "exception",
    "_debug_log", "print",
)


def _is_broad(handler: ast.ExceptHandler) -> bool:
    """True for `except:` / `except Exception:` / `except BaseException:`.

    Narrow handlers (OSError, ValueError, sqlite3.OperationalError, …) are out of
    scope: catching a SPECIFIC error you anticipated and choosing to continue is
    ordinary control flow, not a swallowed unknown.
    """
    t = handler.type
    if t is None:
        return True
    names: list[str] = []
    if isinstance(t, ast.Name):
        names = [t.id]
    elif isinstance(t, ast.Tuple):
        names = [e.id for e in t.elts if isinstance(e, ast.Name)]
    return any(n in ("Exception", "BaseException") for n in names)


def _leaves_a_trace(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name and any(t in str(name) for t in _TRACE_CALLS):
                return True
        # `raise` re-raises or replaces — the failure is not being hidden.
        if isinstance(node, ast.Raise):
            return True
    return False


def scan(paths: tuple[str, ...] = PROTECTED) -> list[str]:
    findings: list[str] = []
    for rel in paths:
        p = REPO / rel
        if not p.exists():
            findings.append(f"{rel}: MISSING (protected module cannot be checked)")
            continue
        src = p.read_text()
        lines = src.splitlines()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.ExceptHandler) or not _is_broad(node):
                continue
            if _leaves_a_trace(node):
                continue
            snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
            findings.append(f"{rel}:{node.lineno}: silent broad catch — {snippet}")
    return findings


def main() -> int:
    findings = scan()
    if not findings:
        print(f"CHZ-FO-01: clean ({len(PROTECTED)} protected modules checked)")
        return 0
    print(f"CHZ-FO-01: {len(findings)} silent broad catch(es) in protected modules\n")
    for f in findings:
        print(f"  {f}")
    print(
        "\nA broad catch here is fine; a SILENT one is not. Call "
        "chuzom.failopen.record('CHZ-FO-<AREA>-<SITE>', exc) so the degradation "
        "is counted instead of invisible."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
