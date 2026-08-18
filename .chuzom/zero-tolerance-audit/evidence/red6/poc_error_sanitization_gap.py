"""RED-6 PoC (sandboxed, no real network/creds): does error_sanitization.py's own
_SENSITIVE_PATTERNS (independent of secret_scrubber.SECRET_PATTERNS) redact a
provider API key that appears inside a raw exception message -- as would happen
when an upstream SDK echoes the (invalid/rejected) key back in its error text,
or a bearer token appears in a raised HTTPError's body/headers repr?

Uses ONLY synthetic/fake key-shaped strings, clearly marked, no live network call.
"""
import sys
sys.path.insert(0, "/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882/src")

from chuzom.error_sanitization import sanitize_error_message, sanitize_exception  # noqa: E402
from chuzom.secret_scrubber import scrub_text  # noqa: E402

FAKE_ANTHROPIC_KEY = "sk-ant-api03-FAKE1234567890abcdefFAKE1234567890abcdefFAKE"
FAKE_OPENAI_KEY = "sk-proj-FAKE1234567890abcdefFAKEabcdefFAKE1234567890"
FAKE_GH_TOKEN = "ghp_FAKE1234567890abcdefFAKE1234567890"
FAKE_BEARER = "Bearer FAKE1234567890abcdefFAKEtoken1234567890"

raw_exc_message = (
    f"AuthenticationError: Incorrect API key provided: {FAKE_ANTHROPIC_KEY}. "
    f"You can find your API key at https://console.anthropic.com. "
    f"Retry with fallback key {FAKE_OPENAI_KEY} failed too. "
    f"Also tried GH token {FAKE_GH_TOKEN} for the private registry lookup. "
    f"Request headers included Authorization: {FAKE_BEARER}"
)

class FakeAuthError(Exception):
    pass

exc = FakeAuthError(raw_exc_message)

sanitized_via_error_sanitization = sanitize_exception(exc)
sanitized_via_error_message_fn = sanitize_error_message(raw_exc_message)
sanitized_via_canonical_scrubber = scrub_text(raw_exc_message)

print("=== RAW (never shown to user; ground truth) ===")
print(raw_exc_message)
print()
print("=== error_sanitization.sanitize_exception() output (what a user-facing")
print("    error handler in the codebase would actually return/display) ===")
print(sanitized_via_error_sanitization)
print()
print("=== Does error_sanitization's output still contain the fake secrets? ===")
for name, val in [("anthropic_key", FAKE_ANTHROPIC_KEY), ("openai_key", FAKE_OPENAI_KEY),
                   ("gh_token", FAKE_GH_TOKEN), ("bearer", FAKE_BEARER)]:
    leaked = val in sanitized_via_error_sanitization
    print(f"  {name}: {'LEAKED (present verbatim)' if leaked else 'redacted'}")
print()
print("=== For comparison: secret_scrubber.scrub_text() (the codebase's own")
print("    documented 'canonical'/'single source of truth' scrubber) on the SAME input ===")
print(sanitized_via_canonical_scrubber)
print()
print("=== Does the canonical scrubber redact them? ===")
for name, val in [("anthropic_key", FAKE_ANTHROPIC_KEY), ("openai_key", FAKE_OPENAI_KEY),
                   ("gh_token", FAKE_GH_TOKEN), ("bearer", FAKE_BEARER)]:
    leaked = val in sanitized_via_canonical_scrubber
    print(f"  {name}: {'LEAKED (present verbatim)' if leaked else 'redacted'}")
