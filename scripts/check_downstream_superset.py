#!/usr/bin/env python3
"""Is upstream a superset of downstream? The precondition for the sync, measured.

WHY THIS EXISTS
===============

36_DOWNSTREAM_SYNC_PLAN.md Step 2 says: "Copy upstream ``src/`` minus the
exclusion set, into the downstream package layout." That instruction is safe
only if upstream contains everything downstream does. Nobody had checked.

It does not. Measured 2026-08-19, upstream ``Chuzom/src/chuzom`` against
downstream ``llm-router/src/llm_router``: **47 top-level symbols** are defined
downstream and nowhere upstream, across whole features:

    response_validation.py    ABSENT upstream — 9 symbols, an entire module
    audit_routing.py          PRESENT upstream, DIFFERENT FEATURE (see below)
    dashboard_data.py         query_realized_savings + 2 supporting symbols
    signals/__init__.py       detect_pii, force_local_for_pii
    cost.py                   get_savings_by_task_type + 2 baseline helpers
    commands/audit.py         the whole `audit` CLI command

The ``audit_routing.py`` case is the one that makes this a script rather than a
paragraph. Both repositories have a file at that path. They are unrelated:

    upstream    audit_routing_turn / _get_audit_log / reset_audit_log_for_tests
                -- an append-only log of routing turns
    downstream  run_audit / score_decision / sample_unaudited_decisions /
                _write_verdict -- a post-hoc misroute SCORER

A file-level copy overwrites one with the other. Same path, no merge conflict,
no import error, no failing test upstream -- the downstream feature simply
stops existing, and the only signal is that a test file somewhere downstream
now fails to import. That is a silent-deletion shape, and it is exactly what a
"copy src/ across" instruction produces when the two trees are not the
containment the instruction assumes.

WHAT THIS CHECKS
================

For every symbol defined in the downstream tree, is a symbol of that name
defined ANYWHERE in the upstream tree? Name-level, not signature-level,
deliberately:

  * a relocated symbol (``observability/summary.py`` upstream is ``summary.py``)
    is NOT a gap, and a path-sensitive check would report dozens of those as
    findings, which is how a check gets ignored;
  * a same-name-different-meaning symbol IS still reported by the file-level
    collision section below, which is the case that actually loses work.

Private helpers (``_fmt_usd_or_na``, ``_bold``) are reported separately from
public API, because a missing formatter is a cosmetic gap and a missing
``query_realized_savings`` is a missing feature, and lumping them together
makes the number meaningless.

EXIT CODES
==========

0  upstream is a superset -- Step 2's copy is safe to perform
1  gaps found -- port them upstream FIRST, then re-run

Usage:
    python scripts/check_downstream_superset.py [--downstream PATH] [--verbose]
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

UPSTREAM_DEFAULT = Path(__file__).resolve().parent.parent / "src" / "chuzom"
DOWNSTREAM_DEFAULT = Path.home() / "Projects" / "llm-router" / "src" / "llm_router"

#: Modules deliberately not synced (36_DOWNSTREAM_SYNC_PLAN.md §1). A symbol
#: only present downstream inside one of these is out of scope, not a gap.
EXCLUDED = {
    "tools/agoragentic.py",
    "tenant_policy_sidecar.py",
    "admin_api.py",
    "commands/admin_api.py",
}


def _defined_symbols(root: Path) -> dict[str, list[str]]:
    """Every top-level function/class name in the tree -> the files defining it."""
    found: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        if rel in EXCLUDED:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.setdefault(node.name, []).append(rel)
    return found


def _file_level_collisions(upstream: Path, downstream: Path) -> list[tuple[str, set[str], set[str]]]:
    """Same path, disjoint public API -- the silent-overwrite case.

    Reported only when the two files share NO public symbol at all. Partial
    overlap is ordinary drift; zero overlap means the path means two different
    things in the two trees, and copying one over the other deletes a feature
    without any signal.
    """
    out: list[tuple[str, set[str], set[str]]] = []
    for dpath in sorted(downstream.rglob("*.py")):
        if "__pycache__" in dpath.parts:
            continue
        rel = dpath.relative_to(downstream)
        if str(rel) in EXCLUDED:
            continue
        upath = upstream / rel
        if not upath.exists():
            continue

        def public(p: Path) -> set[str]:
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                return set()
            return {
                n.name
                for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and not n.name.startswith("_")
            }

        dsyms, usyms = public(dpath), public(upath)
        if dsyms and usyms and not (dsyms & usyms):
            out.append((str(rel), usyms, dsyms))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=UPSTREAM_DEFAULT)
    parser.add_argument("--downstream", type=Path, default=DOWNSTREAM_DEFAULT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.downstream.exists():
        print(
            f"SKIP: no downstream checkout at {args.downstream}. This check "
            f"compares two working trees and cannot run without both; it is a "
            f"local pre-sync gate, not a CI gate.",
            file=sys.stderr,
        )
        return 0

    upstream = _defined_symbols(args.upstream)
    downstream = _defined_symbols(args.downstream)

    if not upstream or not downstream:
        print(
            "FAIL: one of the trees yielded no symbols at all — the parser or a "
            "path is wrong, and a comparison against nothing would report a "
            "clean bill of health.",
            file=sys.stderr,
        )
        return 1

    missing = {name: files for name, files in downstream.items() if name not in upstream}
    public_missing = {n: f for n, f in missing.items() if not n.startswith("_")}
    private_missing = {n: f for n, f in missing.items() if n.startswith("_")}
    collisions = _file_level_collisions(args.upstream, args.downstream)

    print(f"upstream symbols:   {len(upstream)}")
    print(f"downstream symbols: {len(downstream)}")
    print(f"downstream-only:    {len(missing)}  ({len(public_missing)} public, "
          f"{len(private_missing)} private)")
    print(f"path collisions:    {len(collisions)}")
    print()

    if collisions:
        print("SAME PATH, DISJOINT API — a file copy here deletes a feature silently:")
        for rel, usyms, dsyms in collisions:
            print(f"  {rel}")
            print(f"      upstream:   {', '.join(sorted(usyms))}")
            print(f"      downstream: {', '.join(sorted(dsyms))}")
        print()

    if public_missing:
        by_file: dict[str, list[str]] = {}
        for name, files in public_missing.items():
            by_file.setdefault(files[0], []).append(name)
        print("PUBLIC API defined downstream and nowhere upstream:")
        for f in sorted(by_file):
            print(f"  {f}")
            print(f"      {', '.join(sorted(by_file[f]))}")
        print()

    if args.verbose and private_missing:
        print("private helpers, downstream-only (cosmetic unless they carry logic):")
        for name in sorted(private_missing):
            print(f"  {name:38} {private_missing[name][0]}")
        print()

    if collisions or public_missing:
        print(
            "NOT A SUPERSET. Copying upstream src/ over downstream would drop the\n"
            "above. Port these upstream first — that is what 'after Chuzom is\n"
            "completely ready' has to mean before a copy is safe — then re-run."
        )
        return 1

    print("SUPERSET OK: every downstream symbol has an upstream definition.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
