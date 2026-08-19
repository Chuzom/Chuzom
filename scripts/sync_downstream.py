#!/usr/bin/env python3
"""Rebrand upstream into the downstream package. Deterministic and re-runnable.

WHY A SCRIPT AND NOT A COPY
===========================

The sync rewrites ~4,956 ``chuzom`` occurrences across 363 files. Done by hand
it is unreviewable, unrepeatable, and impossible to redo when upstream moves on
next month. Done as a script the diff is the script, the mapping is written
down, and the next sync is one command.

More importantly, a copy cannot express the two rules that matter, both
discovered by ``check_downstream_superset.py``:

  * ``audit_routing.py`` means DIFFERENT FEATURES in the two trees. Copying it
    across deletes one of them, silently — same path, no merge conflict, no
    import error, no failing test.
  * seven downstream-only public symbols are dead code downstream, and several
    downstream-only MODULES are alive. A wholesale replace deletes both
    indiscriminately.

SAFETY MODEL
============

Default is ``--dry-run``: prints what would change and writes nothing.
``--apply`` writes. Nothing is deleted, ever — files that exist downstream and
not upstream are LEFT ALONE and reported, because deciding a downstream module
is obsolete is a human call and this script cannot make it.

REWRITES
========

Order matters — the longest and most specific patterns first, or a shorter one
eats the prefix of a longer one and the result is subtly wrong in a way tests
do not always catch (``chuzom-router`` becoming ``llm_router-router``).
``_check_rewrite_order`` asserts the ordering property directly rather than
trusting the list to stay sorted.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

UPSTREAM_ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_SRC = UPSTREAM_ROOT / "src" / "chuzom"
DOWNSTREAM_ROOT_DEFAULT = Path.home() / "Projects" / "llm-router"

#: Ordered longest-first. See _check_rewrite_order.
REWRITES: list[tuple[str, str]] = [
    ("chuzom-router", "llm-routing"),      # distribution name
    ("CHUZOM_", "LLM_ROUTER_"),            # env var prefix
    (".chuzom", ".llm-router"),            # home directory
    ("chuzom", "llm_router"),              # python package / module paths
    ("Chuzom", "LLM Router"),              # prose brand
    ("CHUZOM", "LLM_ROUTER"),              # any remaining shout-case
]

#: Not synced. From 36_DOWNSTREAM_SYNC_PLAN.md §1 (maintainer decision) plus the
#: enterprise tree, which the downstream README sells separately rather than
#: ships.
EXCLUDED_PATHS = {
    "tools/agoragentic.py",
    "tenant_policy_sidecar.py",
    "admin_api.py",
    "commands/admin_api.py",
}
EXCLUDED_DIRS = {"enterprise", "invoice_reconciliation", "__pycache__"}

#: Upstream path -> downstream path, where the names legitimately differ.
#: Every entry here is a collision `check_downstream_superset.py` reports: the
#: same path already means something else downstream, so copying onto it would
#: destroy a feature.
PATH_MAP = {
    "misroute_audit.py": "audit_routing.py",
    # Relocations, verified by symbol overlap rather than by name:
    # upstream summary.py shares 7 symbols with downstream
    # observability/summary.py, and surface_status.py shares 22 with
    # observability/surface_status.py. Without these the sync writes a SECOND
    # copy at the top level and downstream ends up with two of each — one
    # imported by existing code, one dead and drifting.
    "summary.py": "observability/summary.py",
    "surface_status.py": "observability/surface_status.py",
    # Upstream `observability.py` is a MODULE with 14 symbols; downstream
    # `observability/` is a PACKAGE whose __init__ shares NONE of them. Landing
    # the module at `observability.py` next to the package makes the package win
    # the import and the module's contents unreachable — code present, silently
    # never executed. Placed inside the package instead; re-exporting from
    # __init__ is a public-API decision left to the human doing the merge.
    "observability.py": "observability/core.py",
}

#: Downstream paths this script must never write, because the downstream file is
#: a DIFFERENT feature that happens to share a name, or is a merge rather than a
#: replace. Listed explicitly so the reason survives.
DO_NOT_OVERWRITE = {
    "audit_routing.py": (
        "downstream audit_routing.py is the misroute scorer; upstream's is the "
        "live compliance log. The scorer arrives via PATH_MAP from "
        "misroute_audit.py instead."
    ),
    "commands/audit.py": (
        "upstream has verify/export/misroute subcommands, downstream has only "
        "misroute. Needs a merge decision, not an overwrite."
    ),
}


def _check_rewrite_order() -> list[str]:
    """Each pattern must not be a substring of a LATER pattern's source.

    If it is, the earlier rewrite fires inside the later one's text and the
    later rule never matches what it was written for. Checked rather than
    assumed, because the failure is silent: the output still looks like code.
    """
    problems = []
    for i, (src, _) in enumerate(REWRITES):
        for later_src, _ in REWRITES[i + 1 :]:
            if src in later_src:
                problems.append(
                    f"{src!r} precedes {later_src!r} but is a substring of it — "
                    f"the second rule will never match its intended text"
                )
    return problems


def rewrite(text: str) -> str:
    for src, dst in REWRITES:
        text = text.replace(src, dst)
    return text


def _iter_upstream_files():
    for path in sorted(UPSTREAM_SRC.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(UPSTREAM_SRC))
        if rel in EXCLUDED_PATHS:
            continue
        if path.suffix in {".pyc", ".pyo", ".db", ".sqlite3"}:
            continue
        yield path, rel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downstream", type=Path, default=DOWNSTREAM_ROOT_DEFAULT)
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    order_problems = _check_rewrite_order()
    if order_problems:
        print("REWRITE ORDER BROKEN:", file=sys.stderr)
        for p in order_problems:
            print(f"  {p}", file=sys.stderr)
        return 1

    dst_pkg = args.downstream / "src" / "llm_router"
    if not dst_pkg.exists():
        print(f"no downstream package at {dst_pkg}", file=sys.stderr)
        return 1

    # A file landing where a directory already lives (or the reverse) produces a
    # tree Python cannot import unambiguously — the package shadows the module
    # and its contents become unreachable code that still passes every syntax
    # check. Detected up front and refused, because the fix is a path decision
    # a human has to make, not something to guess mid-write.
    structural: list[str] = []
    for _, rel in _iter_upstream_files():
        target = dst_pkg / rewrite(PATH_MAP.get(rel, rel))
        # `foo.py` and `foo/` coexist happily ON DISK — the collision is at
        # IMPORT time, where the package wins and the module is unreachable. So
        # the test is against the suffix-stripped path, not the path itself.
        # The first version of this check compared `target.is_dir()` and found
        # nothing, because `observability.py` is not the directory
        # `observability` and never will be.
        if target.suffix == ".py" and target.with_suffix("").is_dir():
            structural.append(
                f"  {rel} -> {target.relative_to(dst_pkg)} — a PACKAGE named "
                f"{target.stem!r} already exists downstream. Both can sit on "
                f"disk, but the package wins the import and this module's "
                f"contents become unreachable code that still passes every "
                f"syntax check. Add a PATH_MAP entry."
            )
        elif target.parent.exists() and target.parent.is_file():
            structural.append(
                f"  {rel} -> {target.relative_to(dst_pkg)} — its parent is a FILE "
                f"downstream, so the directory cannot be created."
            )
    if structural:
        print("STRUCTURAL COLLISIONS — refusing to write:\n", file=sys.stderr)
        print("\n".join(structural), file=sys.stderr)
        return 1

    written = skipped_protected = unchanged = 0
    new_files: list[str] = []
    binary: list[str] = []

    for src_path, rel in _iter_upstream_files():
        target_rel = PATH_MAP.get(rel, rel)
        if target_rel in DO_NOT_OVERWRITE and rel not in PATH_MAP:
            skipped_protected += 1
            if args.verbose:
                print(f"  PROTECTED {target_rel}: {DO_NOT_OVERWRITE[target_rel]}")
            continue

        target = dst_pkg / rewrite(target_rel)
        try:
            content = src_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            binary.append(rel)
            if args.apply:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, target)
                written += 1
            continue

        new_content = rewrite(content)
        existing = target.read_text(encoding="utf-8") if target.exists() else None
        if existing == new_content:
            unchanged += 1
            continue
        if existing is None:
            new_files.append(str(target.relative_to(dst_pkg)))
        if args.apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_content, encoding="utf-8")
        written += 1

    # Downstream files with no upstream counterpart. NEVER deleted -- several
    # are live downstream-only modules, and deciding one is obsolete is a human
    # call this script has no basis to make.
    upstream_targets = {
        rewrite(PATH_MAP.get(rel, rel)) for _, rel in _iter_upstream_files()
    }
    downstream_only = sorted(
        str(p.relative_to(dst_pkg))
        for p in dst_pkg.rglob("*.py")
        if "__pycache__" not in p.parts
        and str(p.relative_to(dst_pkg)) not in upstream_targets
    )

    mode = "APPLIED" if args.apply else "DRY RUN — nothing written"
    print(f"=== sync_downstream: {mode} ===")
    print(f"  files written/changed : {written}")
    print(f"  already identical     : {unchanged}")
    print(f"  protected (not copied): {skipped_protected}")
    print(f"  new downstream files  : {len(new_files)}")
    print(f"  binary copied verbatim: {len(binary)}")
    print(f"  downstream-only, LEFT ALONE: {len(downstream_only)}")

    if args.verbose:
        for group, items in (
            ("NEW", new_files),
            ("DOWNSTREAM-ONLY (kept)", downstream_only),
            ("BINARY", binary),
        ):
            if items:
                print(f"\n{group}:")
                for i in items[:40]:
                    print(f"  {i}")
                if len(items) > 40:
                    print(f"  … {len(items) - 40} more")

    if not args.apply:
        print("\nRe-run with --apply to write. Nothing is ever deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
