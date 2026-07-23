"""Objective acceptance-check runners for MGEE milestones.

A milestone is DONE only when an objective, *executable* check passes — never on
the executing model's self-report (docs/agentic-router.md §4.2). Each factory
returns an ``AcceptanceCheck`` (``artifacts -> AcceptanceResult``) usable directly
as ``Milestone.acceptance``.

``reproducible()`` wraps any check to detect non-determinism (flaky): a flaky
failure is reported with ``deterministic=False`` so the engine re-runs it once
instead of escalating on noise.
"""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

from chuzom.agentic.ledger import AcceptanceCheck, AcceptanceResult


def canary_check(marker: str, field: str = "output") -> AcceptanceCheck:
    """Pass iff ``marker`` appears in ``artifacts[field]``."""
    def check(artifacts: dict[str, Any]) -> AcceptanceResult:
        text = str(artifacts.get(field, ""))
        ok = marker in text
        return AcceptanceResult(ok, "" if ok else f"canary {marker!r} not found in {field}")
    return check


def validator_check(
    fn: Callable[[dict[str, Any]], bool], desc: str = ""
) -> AcceptanceCheck:
    """Pass iff the pure predicate ``fn(artifacts)`` is truthy."""
    def check(artifacts: dict[str, Any]) -> AcceptanceResult:
        try:
            ok = bool(fn(artifacts))
        except Exception as exc:  # noqa: BLE001 — a broken validator fails closed, never hangs
            return AcceptanceResult(False, f"validator error: {exc}")
        return AcceptanceResult(ok, "" if ok else f"validator failed: {desc or fn}")
    return check


def diff_check(
    *,
    files: Sequence[str] = (),
    symbols: Sequence[str] = (),
    files_field: str = "files",
    diff_field: str = "diff",
) -> AcceptanceCheck:
    """Structural assertion over produced artifacts: every path in ``files`` must
    appear in ``artifacts[files_field]`` and every string in ``symbols`` must
    appear in ``artifacts[diff_field]``."""
    def check(artifacts: dict[str, Any]) -> AcceptanceResult:
        produced = set(artifacts.get(files_field, []) or [])
        missing_files = [f for f in files if f not in produced]
        diff_text = str(artifacts.get(diff_field, ""))
        missing_syms = [s for s in symbols if s not in diff_text]
        if missing_files or missing_syms:
            parts = []
            if missing_files:
                parts.append(f"missing files: {missing_files}")
            if missing_syms:
                parts.append(f"missing symbols: {missing_syms}")
            return AcceptanceResult(False, "; ".join(parts))
        return AcceptanceResult(True)
    return check


def cmd_check(
    command: Sequence[str], *, cwd: str | None = None, timeout: float = 60.0
) -> AcceptanceCheck:
    """Pass iff ``command`` (argv list, never a shell string) exits 0.

    A timeout or missing binary is a *deterministic* failure — it won't loop.
    """
    def check(_artifacts: dict[str, Any]) -> AcceptanceResult:
        try:
            # argv list, no shell; check=False → we inspect returncode ourselves.
            proc = subprocess.run(
                list(command), cwd=cwd, capture_output=True, text=True,
                timeout=timeout, check=False,
            )
        except FileNotFoundError:
            return AcceptanceResult(False, f"command not found: {command[0]}")
        except subprocess.TimeoutExpired:
            return AcceptanceResult(False, f"timed out after {timeout}s")
        if proc.returncode == 0:
            return AcceptanceResult(True)
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [""]
        return AcceptanceResult(False, f"exit {proc.returncode}: {tail[0][:200]}")
    return check


def lint_check(
    paths: Sequence[str], *, linter: str = "ruff", cwd: str | None = None, timeout: float = 60.0
) -> AcceptanceCheck:
    """Pass iff ``<linter> check <paths>`` exits 0. If the linter binary isn't
    installed the result is marked non-deterministic (unknown), not a hard fail."""
    resolved = shutil.which(linter)
    if resolved is None:
        def unavailable(_artifacts: dict[str, Any]) -> AcceptanceResult:
            return AcceptanceResult(False, f"linter {linter!r} not available", deterministic=False)
        return unavailable
    return cmd_check([resolved, "check", *paths], cwd=cwd, timeout=timeout)


def reproducible(check: AcceptanceCheck, *, times: int = 2) -> AcceptanceCheck:
    """Run ``check`` ``times`` times; if the pass/fail verdict disagrees across
    runs the failure is flagged ``deterministic=False`` (flaky) so the engine
    re-runs once rather than escalating on noise. Agreeing runs pass through."""
    n = max(2, times)

    def wrapped(artifacts: dict[str, Any]) -> AcceptanceResult:
        results = [check(artifacts) for _ in range(n)]
        verdicts = {r.ok for r in results}
        if len(verdicts) > 1:
            return AcceptanceResult(False, "non-reproducible acceptance verdict", deterministic=False)
        return results[0]
    return wrapped
