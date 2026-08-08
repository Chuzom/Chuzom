#!/usr/bin/env python3
"""CHZ-SURF-01 guard — no emitter may hardcode a tool name into a message.

The bug this prevents
─────────────────────
Routing hooks tell the caller which tool to call. Tool names are tier-dependent
(``CHUZOM_SLIM``), and the DEFAULT tier (``consolidated``) registers none of the
legacy ``llm_query``/``llm_analyze``/``llm_code``/``llm_research``/``llm_generate``
names — they live behind ``llm(task=…)``. A hint that names one of them produces
``Error: No such tool available``; the caller then does the work on the expensive
model, and the savings dashboard cannot tell that apart from "chose not to route".
The failure is invisible in every metric we have, which is why it needs a lint.

The rule
────────
A legacy tool name may appear as a BARE string (``tool = "llm_code"``, a TOOL_MAP
value, a set member) — those are logical identifiers used for state, matching and
telemetry, and they are correct. It may NOT appear EMBEDDED IN PROSE — that string
is on its way to a human or a model, and it must be resolved through
``chuzom.tool_surface`` first.

    tool = "llm_code"                             # OK  — logical identifier
    TOOL_MAP = {"code": "llm_code"}               # OK  — logical identifier
    f"  • llm_code: for code tasks"               # FAIL — embedded in a message
    f"  • {route_tool('llm_code')}: for code…"    # OK  — resolved

Also flagged: ``{route_tool('x')}(`` — appending an argument list to a display
form yields the uncallable ``llm(task="code")(prompt=…)``. Use ``route_call``.

Run:  python3 scripts/lint_tool_surface.py [paths...]
Exit: 0 clean, 1 violations found.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The whole package, not just hooks: the same defect shipped in CLI output
# (`run llm_savings to verify`) and in GENERATED rules/agent files, which teach a
# model the wrong name for as long as the file exists.
DEFAULT_TARGETS = [REPO / "src" / "chuzom"]

# Tool names that are NOT registered under at least one tier and therefore must
# never be spoken aloud unresolved. Longest-first for stable matching.
GUARDED = (
    "llm_check_usage",
    "llm_session_savings",
    "llm_session_spend",
    "llm_set_profile",
    "llm_research",
    "llm_generate",
    "llm_analyze",
    "llm_delegate",
    "llm_savings",
    "llm_query",
    "llm_health",
    "llm_usage",
    "llm_code",
)

# A string is "prose" if it carries anything beyond the bare identifier: spaces,
# punctuation, formatting. A bare name (or a dotted/qualified variant) is a
# logical identifier and is allowed.
_BARE = re.compile(r"^[\w./:|-]*$")

# Files exempt from the lint, with the reason. The loader blocks legitimately name
# the tools in their explanatory comments — comments are not string constants, so
# they never reach this check — but the fallback lambdas do format names.
EXEMPT: dict[str, str] = {}

# Call names whose string arguments are logical inputs, not output.
RESOLVER_CALLS = {
    "route_tool", "route_call", "route_call_with_complexity", "call_parts",
    "resolve", "resolve_name", "is_registered", "_door_for",
    # localize() rewrites a whole blob, so a template passed to it is already safe.
    "localize", "_localize_banner",
}

# No \s* before the "(": prose like `{route_tool('llm_query')} (external)` is
# fine, only a directly-appended argument list `{route_tool('x')}(prompt=…)` is
# the uncallable double call.
DOUBLE_CALL = re.compile(r"\{\s*route_tool\([^)]*\)\s*\}\(")

# Escape hatch for a template whose names ARE resolved, just at render time rather
# than at the literal. Requires a reason so it can't become a silent blanket mute.
PRAGMA = re.compile(r"#\s*chz-surface-ok:\s*\S+")


def _has_pragma(src_lines: list[str], lineno: int) -> bool:
    """True if the statement opening at ``lineno`` carries a justified pragma.

    Checked on the statement's own line OR the line immediately above it. The
    line-above form is the one to use for triple-quoted templates: a trailing
    ``#`` comment after ``\"\"\"`` is not a comment at all, it is the first line of
    the string, and it would print inside the banner.
    """
    if not 1 <= lineno <= len(src_lines):
        return False
    # Look back a few lines: Python folds adjacent string literals into a SINGLE
    # Constant node reported at the first literal's line, so the pragma often sits
    # above the enclosing `return (` rather than immediately above the text.
    for back in range(0, 4):
        idx = lineno - 1 - back
        if idx >= 0 and PRAGMA.search(src_lines[idx]):
            return True
    return False


def _docstrings(tree: ast.AST) -> set[int]:
    """id() of every Constant node that is a docstring (documentation, not output)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _resolver_args(tree: ast.AST) -> set[int]:
    """id() of string Constants passed directly to a resolver call."""
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
        if name not in RESOLVER_CALLS:
            continue
        # Walk INTO each argument: a template is often passed as
        # localize("""…""".strip()), so the Constant is nested under a method
        # call rather than being a direct argument.
        for a in list(node.args) + [k.value for k in node.keywords]:
            for sub in ast.walk(a):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.add(id(sub))
    return out


# Variables that hold a LOGICAL tool name (used for state, matching, telemetry).
# Interpolating one into an f-string emits the unresolved name — which is the
# original bug. The display-resolved siblings must be used instead.
#
# This check exists because the literal-scan above cannot see it: `{tool:32}` in
# an ASCII box contains no tool name in the source at all. That variant survived
# the first fix and was only caught by the end-to-end trace.
LOGICAL_TOOL_VARS = {
    "tool": "tool_disp / route_call(tool, …)",
    "_ctx_tool": "_ctx_disp / _ctx_call",
    "expected_tool": "_expected_disp / _expected_call",
}


def _logical_var_interpolations(tree: ast.AST, src_lines: list[str]) -> list[tuple[int, str, str]]:
    """(lineno, var, suggestion) for each f-string interpolation of a logical var."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        for part in node.values:
            if not isinstance(part, ast.FormattedValue):
                continue
            v = part.value
            if isinstance(v, ast.Name) and v.id in LOGICAL_TOOL_VARS:
                ln = getattr(part, "lineno", getattr(node, "lineno", 0))
                if _has_pragma(src_lines, ln):
                    continue
                out.append((ln, v.id, LOGICAL_TOOL_VARS[v.id]))
    return out


def check_file(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8", errors="replace")
    src_lines = src.splitlines()
    problems: list[str] = []

    for m in DOUBLE_CALL.finditer(src):
        line = src[: m.start()].count("\n") + 1
        problems.append(
            f"{path}:{line}: route_tool(...) followed by '(' builds an uncallable "
            f"double call like llm(task=\"code\")(prompt=…) — use route_call() instead"
        )

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return problems + [f"{path}: SyntaxError: {e}"]

    # Only the routing hooks carry these variable names with this meaning.
    if path.parent.name == "hooks":
        for ln, var, better in _logical_var_interpolations(tree, src_lines):
            problems.append(
                f"{path}:{ln}: f-string interpolates the LOGICAL tool variable "
                f"{var!r} — this emits an unresolved name (the CHZ-SURF-01 bug). "
                f"Use {better}, or add '# chz-surface-ok: <reason>' if the value "
                f"is internal (telemetry, state key, debug log)."
            )

    skip = _docstrings(tree) | _resolver_args(tree)

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in skip:
            continue
        text = node.value
        hit = next((g for g in GUARDED if g in text), None)
        if hit is None:
            continue
        if _BARE.match(text.strip()):
            continue  # bare logical identifier — allowed
        if _has_pragma(src_lines, getattr(node, "lineno", 0)):
            continue  # explicitly resolved elsewhere; reason required on the line
        problems.append(
            f"{path}:{getattr(node, 'lineno', '?')}: tool name {hit!r} embedded in an "
            f"emitted string — wrap it in route_tool()/route_call() so it names a tool "
            f"registered under the active CHUZOM_SLIM tier. Offending text: "
            f"{text.strip()[:70]!r}"
        )
    return problems


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or DEFAULT_TARGETS
    files: list[Path] = []
    for t in targets:
        files.extend(sorted(t.rglob("*.py")) if t.is_dir() else [t])

    problems: list[str] = []
    for f in files:
        if f.name in EXEMPT or "__pycache__" in f.parts:
            continue
        problems.extend(check_file(f))

    if problems:
        print(f"CHZ-SURF-01: {len(problems)} violation(s)\n")
        for p in problems:
            print("  " + p)
        print(
            "\nEvery tool name reaching a human or a model must go through "
            "chuzom.tool_surface. See src/chuzom/tool_surface.py for why."
        )
        return 1

    print(f"CHZ-SURF-01: clean ({len(files)} files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
