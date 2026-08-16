#!/usr/bin/env python3
"""CHZ-SR-01 — a ratchet on modules that resolve the chuzom state directory themselves.

WHY THIS EXISTS (audit #37)

`chuzom.paths` is the one module that knows where state lives and honours `CHUZOM_HOME`.
Almost nothing asks it. A survey on 2026-08-15 counted **120 sites in `src/chuzom/`** that
compose `~/.chuzom` directly, plus 55 more in `src/chuzom/hooks/` that run as separate
processes. `usage.db` alone is reached ~23 different ways.

That is not untidiness. It is what let `session_store.py` read the operator's real session
content while `is_isolated()` returned True, and what let a sandboxed test destroy live
data in `evidence/AUDITOR_INCIDENT.md`. One artefact with many answers means many chances
for two of them to disagree, on the single file that carries billing and routing history.

WHAT THIS DOES, AND WHAT IT DELIBERATELY DOES NOT

It does NOT migrate anything. Rerouting 120 sites relocates every existing user's data and
any of them could have a caller depending on the current path — the survey's options (a)
and (b), both explicitly the owner's call, both explicitly not a bug fix.

It stops the number GROWING. New code must go through `chuzom.paths`; existing sites are
recorded in a baseline that can only shrink.

ON BASELINES, HONESTLY

Audit #22 filed the G4 ratchet as an antipattern because it grandfathered a *can't-fail
test* inside a release gate — a baseline that hid a defect while reporting clean. This
baseline is a different thing: it records a known, measured, documented migration backlog
whose exact size is the point, and the gate FAILS if the count rises. The distinction is
that nothing here is hidden — the number is the finding.

If the baseline is ever raised to accommodate new code, that is the antipattern arriving,
and the commit doing it should be challenged.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "chuzom"
BASELINE = REPO / ".chuzom" / "zero-tolerance-audit" / "state_root_baseline.json"

#: `~/.claude`, `~/.cursor`, `~/.codex`, `~/.gemini` and friends belong to OTHER tools.
#: Redirecting those because chuzom was sandboxed would be a new defect, not a fix — so
#: a site only counts when the path it composes is chuzom's own.
_CHUZOM_DIR_NAMES = (".chuzom",)


def _composes_chuzom_state(tree: ast.AST) -> list[int]:
    """Lines where this module builds a chuzom state path from the real home.

    Matches the two shapes the survey found: `Path.home() / ".chuzom"` and
    `os.path.expanduser("~/.chuzom...")`. Deliberately syntactic — a resolver reached
    through a variable or a helper will be missed, and that limit is stated rather than
    papered over, because a check that appears exhaustive is the shape this audit keeps
    finding.
    """
    hits: list[int] = []
    for node in ast.walk(tree):
        # Path.home() / ".chuzom"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            right = node.right
            if (
                isinstance(right, ast.Constant)
                and isinstance(right.value, str)
                and right.value in _CHUZOM_DIR_NAMES
            ):
                hits.append(node.lineno)
        # os.path.expanduser("~/.chuzom/...") / Path("~/.chuzom").expanduser()
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if v.startswith("~/.chuzom") or v.startswith("~\\.chuzom"):
                hits.append(node.lineno)
    return sorted(set(hits))


def scan() -> dict[str, int]:
    """Map module path -> count of direct state-root resolutions."""
    out: dict[str, int] = {}
    for p in sorted(SRC.rglob("*.py")):
        if p.name == "paths.py":
            continue  # the canonical resolver is where this is SUPPOSED to happen
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        n = len(_composes_chuzom_state(tree))
        if n:
            out[str(p.relative_to(REPO))] = n
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-baseline", action="store_true")
    ns = ap.parse_args()

    found = scan()
    total = sum(found.values())

    if ns.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"total": total, "by_file": found}, indent=2, sort_keys=True) + "\n"
        )
        print(f"wrote baseline: {total} direct resolutions across {len(found)} modules")
        return 0

    if not BASELINE.exists():
        print(f"CHZ-SR-01: no baseline at {BASELINE.relative_to(REPO)}; run --write-baseline")
        return 1

    base = json.loads(BASELINE.read_text())
    prev = base["total"]

    if total > prev:
        print(f"CHZ-SR-01: direct state-root resolutions ROSE {prev} -> {total}\n")
        for f, n in sorted(found.items()):
            was = base["by_file"].get(f, 0)
            if n > was:
                print(f"  {f}: {was} -> {n}")
        print(
            "\nNew code must resolve state through chuzom.paths.state_path(), which "
            "honours CHUZOM_HOME. Every direct resolution is another way for two parts "
            "of the codebase to disagree about where usage.db lives — which is how a "
            "sandboxed test destroyed live data (evidence/AUDITOR_INCIDENT.md).\n"
            "Do NOT raise the baseline to make this pass."
        )
        return 1

    if total < prev:
        print(
            f"CHZ-SR-01: down {prev} -> {total}. Migration progress — "
            f"run --write-baseline to lock it in."
        )
        return 0

    print(f"CHZ-SR-01: holding at {total} direct resolutions across {len(found)} modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
