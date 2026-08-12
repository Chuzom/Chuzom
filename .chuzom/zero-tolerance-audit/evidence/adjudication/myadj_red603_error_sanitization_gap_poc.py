"""Independent PoC for RED6-03.

Claim under test: `error_sanitization.sanitize_error_message()` (used by
`admin_api.py`'s global unhandled-exception handler) fails to redact raw
API-key-shaped secret values that `secret_scrubber.scrub_text()` DOES catch.

FAKE key values only. No network calls.
Must run under `<WORKTREE>/.venv-audit/bin/python`.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/"
                    "b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882/src")

from chuzom.error_sanitization import sanitize_error_message  # noqa: E402
from chuzom.secret_scrubber import scrub_text  # noqa: E402

# Simulates a realistic unhandled-exception message a provider SDK / httpx
# error could plausibly produce (e.g. a connection/auth error that echoes the
# outgoing request's Authorization header or URL). FAKE values only.
FAKE_ANTHROPIC_KEY = "sk-ant-api03-FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE"
FAKE_GH_TOKEN = "ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE00"
raw_exc_msg = (
    f"httpx.ConnectError: request failed; Authorization: Bearer {FAKE_ANTHROPIC_KEY} "
    f"(retry token {FAKE_GH_TOKEN}) to https://api.anthropic.com/v1/messages"
)

sanitized_by_error_module = sanitize_error_message(raw_exc_msg)
scrubbed_by_secret_scrubber = scrub_text(raw_exc_msg)

print("=== RAW (never shown to a real user; printed here only for this redacted PoC) ===")
print(raw_exc_msg.replace(FAKE_ANTHROPIC_KEY, "<FAKE_ANTHROPIC_KEY>")
                 .replace(FAKE_GH_TOKEN, "<FAKE_GH_TOKEN>"))

print()
print("=== error_sanitization.sanitize_error_message() output ===")
leak_in_error_module = FAKE_ANTHROPIC_KEY in sanitized_by_error_module or FAKE_GH_TOKEN in sanitized_by_error_module
print(sanitized_by_error_module.replace(FAKE_ANTHROPIC_KEY, "<FAKE_ANTHROPIC_KEY_STILL_PRESENT>")
                               .replace(FAKE_GH_TOKEN, "<FAKE_GH_TOKEN_STILL_PRESENT>"))
print(f"Fake secret STILL PRESENT after error_sanitization: {leak_in_error_module}")

print()
print("=== secret_scrubber.scrub_text() output (for comparison — NOT what admin_api.py calls) ===")
leak_in_scrubber = FAKE_ANTHROPIC_KEY in scrubbed_by_secret_scrubber or FAKE_GH_TOKEN in scrubbed_by_secret_scrubber
print(scrubbed_by_secret_scrubber)
print(f"Fake secret STILL PRESENT after secret_scrubber.scrub_text: {leak_in_scrubber}")

assert leak_in_error_module, "PoC FAILED to reproduce: error_sanitization unexpectedly redacted the fake secret"
assert not leak_in_scrubber, "sanity check failed: secret_scrubber should have redacted this"
print()
print("PoC RESULT: REPRODUCED — the module actually wired into admin_api.py's global "
      "exception handler (error_sanitization.sanitize_error_message) leaves sk-ant-/ghp_/"
      "Bearer-shaped secrets in an unhandled-exception message UNREDACTED, while the "
      "codebase's own broader scrubber (secret_scrubber.scrub_text, used elsewhere e.g. "
      "logging.py) would have caught the same input.")
