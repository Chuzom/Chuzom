#!/usr/bin/env python3
"""Extract every documented shell command and prove it runs.

WHY THIS EXISTS
===============

README.md promises `pip install chuzom-router && chuzom install --host claude-code`
and "Get Started (60 seconds)". Those are testable claims, and nothing tested them.

This audit examined four documented claims this week and all four were false — a
gate reported PASS on gitignored files, a test passed on the developer's own
routing history, SECURITY.md asserted the opposite of shipped behaviour, and a
docstring claimed a sandbox that shell execution bypasses. The prior on an
unexecuted doc claim is not neutral.

WHAT IT CHECKS

Commands are PARSED out of fenced blocks, not listed here, so a command added to
the README later is covered without editing this script — the same reason
lint_workflow_shell_portability parses rather than greps.

Each is classified:

    RUNNABLE   safe to execute in a sandbox and expected to exit 0
    SKIPPED    explicitly marked non-executable, or needs credentials/network
               that a clean check cannot supply

A command is only SKIPPED for a stated reason. "It failed and I do not know why"
is not one — that is the finding.

GUARDS THE GUARD

Extracting zero commands FAILS. A doc-checker that finds nothing passes
vacuously, which is failure mode #1 in the list above and the single most likely
way this script becomes decorative.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

#: Docs whose shell blocks are treated as promises to the user.
_DOCS = ["README.md"]

#: Prefixes that identify a line as a command rather than output or a comment.
_CMD_START = ("pip ", "pipx ", "uv ", "chuzom", "python ", "python3 ", "claude ", "npx ")

#: Commands whose non-zero exit is CORRECT on a clean machine, with what must
#: appear in their output to prove they failed usefully rather than merely failed.
#: `chuzom doctor` reporting "hooks not installed" on a fresh box is the tool
#: working; a checker that demanded exit 0 would push someone to weaken it.
_EXPECTED_NONZERO: dict[str, str] = {
    "chuzom doctor": "fix:",
}

#: Commands that cannot be verified in a clean sandbox, each with the reason.
#: A reason is mandatory — an unexplained skip is how a check quietly stops checking.
_SKIP: dict[str, str] = {
    "claude mcp": "requires an installed Claude Code host, not present in CI",
    "ollama": "requires a running Ollama daemon; optional dependency by design",
    "chuzom install": "mutates ~/.claude/settings.json — needs an isolated HOME, see --deep",
    "chuzom-onboard": "interactive prompts",
    "chuzom-quickstart": "interactive prompts",
    "--watch": "long-running watch mode; never exits, so it cannot be checked this way",
    "pip install chuzom": (
        "installs the PUBLISHED package over the source tree being checked. "
        "Verifying it needs a genuinely isolated environment — the clean-container "
        "install job in doc 34 Step 1 — not this in-tree checker, which would "
        "shadow the working copy and then report on the wrong code."
    ),
}


@dataclass
class Cmd:
    doc: str
    line: int
    text: str

    @property
    def skip_reason(self) -> str | None:
        """Match anywhere, not just at the start.

        The first version checked `startswith` only, and let
        `pip install X && chuzom install --host claude-code` through — the
        compound form of a command already on the skip list. Found by running the
        extractor rather than by reviewing it, which is the entire argument for
        this script existing.
        """
        for needle, reason in _SKIP.items():
            if needle in self.text:
                return reason
        return None


def extract(doc: Path) -> list[Cmd]:
    """Pull command lines out of fenced code blocks."""
    out: list[Cmd] = []
    in_block = False
    for i, raw in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        if raw.lstrip().startswith("```"):
            in_block = not in_block
            continue
        if not in_block:
            continue
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip an inline trailing comment so `pip install x  # note` still runs.
        line = re.split(r"\s+#\s", line)[0].strip()
        if line.startswith(_CMD_START):
            out.append(Cmd(doc.name, i, line))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="execute RUNNABLE commands")
    args = ap.parse_args()

    cmds: list[Cmd] = []
    for name in _DOCS:
        path = _ROOT / name
        if not path.is_file():
            print(f"FAIL: documented file {name} not found", file=sys.stderr)
            return 1
        cmds.extend(extract(path))

    if not cmds:
        # The vacuity guard. See the module docstring.
        print(
            "FAIL: extracted ZERO commands from "
            f"{', '.join(_DOCS)}. Either the docs stopped showing commands, or "
            "this extractor is broken. A doc-checker that finds nothing passes "
            "while checking nothing — that is the defect this guards against.",
            file=sys.stderr,
        )
        return 1

    runnable = [c for c in cmds if not c.skip_reason]
    skipped = [c for c in cmds if c.skip_reason]

    print(f"extracted {len(cmds)} commands: {len(runnable)} runnable, {len(skipped)} skipped\n")
    for c in skipped:
        print(f"  SKIP  {c.doc}:{c.line}  {c.text}")
        print(f"        reason: {c.skip_reason}")
    if skipped:
        print()

    if not args.run:
        for c in runnable:
            print(f"  RUNNABLE  {c.doc}:{c.line}  {c.text}")
        print("\n(dry run — pass --run to execute)")
        return 0

    failures = []
    for c in runnable:
        proc = subprocess.run(  # noqa: S602 — commands come from our own README
            c.text, shell=True, capture_output=True, text=True, timeout=300,
        )
        expect = next((v for k, v in _EXPECTED_NONZERO.items() if k in c.text), None)
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            ok = True
        elif expect is not None:
            # Non-zero is allowed, but only if it still tells the user what to do.
            ok = expect in out
        else:
            ok = False
        status = "ok" if ok else f"EXIT {proc.returncode}"
        note = "  (expected non-zero, remediation printed)" if ok and proc.returncode else ""
        print(f"  [{status:>7}]  {c.doc}:{c.line}  {c.text}{note}")
        if not ok:
            failures.append((c, proc))

    if failures:
        print(f"\nFAIL: {len(failures)} documented command(s) do not work:\n")
        for c, proc in failures:
            print(f"  {c.doc}:{c.line}  {c.text}")
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            for line in err[:4]:
                print(f"      {line}")
            print()
        print("Fix the doc where it is wrong, or the code where the doc is right.")
        return 1

    print(f"\ndocs-commands OK: {len(runnable)} documented commands all exit 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
