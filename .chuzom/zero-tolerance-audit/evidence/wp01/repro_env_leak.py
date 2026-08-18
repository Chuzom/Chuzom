"""CHZ-SA-2026-001 reproducer — does the delegated shell see this process's secrets?

Uses ONLY APIs that exist in the vulnerable build (``default_tool_executor``), so
the same script runs unchanged before and after the fix. That is the point: it
demonstrates the behaviour change, not the presence of a new function.

    VULNERABLE -> exit 1, canary found in child output
    FIXED      -> exit 0, canary absent

Safe: the canary is a fake value this script sets itself. Nothing real is read.
"""

from __future__ import annotations

import os
import sys
import tempfile

CANARY_KNOWN = "sk-NOTREAL-known-000000"
CANARY_UNKNOWN = "sk-NOTREAL-unknown-000000"

os.environ["OPENAI_API_KEY"] = CANARY_KNOWN
os.environ["ACME_INTERNAL_SERVICE_SECRET"] = CANARY_UNKNOWN

from chuzom.agentic.react import default_tool_executor  # noqa: E402

# `env` may or may not be blocked depending on build; `sh -c env` and parameter
# expansion are the interesting cases because a blocklist tends to miss them.
PROBES = [
    "env",
    "sh -c env",
    "echo $OPENAI_API_KEY",
    "echo $ACME_INTERNAL_SERVICE_SECRET",
    "python3 -c 'import os;print(dict(os.environ))'",
]

with tempfile.TemporaryDirectory() as tmp:
    execute = default_tool_executor(cwd=tmp)
    leaked: list[tuple[str, str]] = []
    for probe in PROBES:
        out = execute("bash", {"command": probe})
        for name, canary in (
            ("OPENAI_API_KEY", CANARY_KNOWN),
            ("ACME_INTERNAL_SERVICE_SECRET", CANARY_UNKNOWN),
        ):
            if canary in out:
                leaked.append((probe, name))
        status = "LEAK" if any(c in out for c in (CANARY_KNOWN, CANARY_UNKNOWN)) else "clean"
        print(f"  [{status:5}] {probe}")

print()
if leaked:
    print(f"VULNERABLE — {len(leaked)} leak(s):")
    for probe, name in leaked:
        print(f"    {name} readable via: {probe}")
    sys.exit(1)

print("FIXED — no canary reached the delegated shell via any probe.")
sys.exit(0)
