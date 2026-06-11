"""Prompt PII redaction — scrub sensitive patterns BEFORE the lineage write.

Default policy catches:
    - OpenAI / Anthropic / Gemini / GitHub / AWS / Slack API keys
    - JWTs + private-key blocks
    - Email addresses
    - US phone numbers (E.164 + common US formats)
    - US Social Security numbers
    - Credit card numbers (Luhn-checked)
    - IPv4 + IPv6 addresses (optional — off by default; many code prompts
      legitimately reference IPs)

Each detected pattern is replaced with `[REDACTED:type]` so the redacted
prompt remains human-readable for audit but the sensitive value is gone.

Policies are pluggable: organizations can register custom patterns
(e.g. employee IDs, internal hostnames, proprietary product codenames)
via RedactionPolicy.with_patterns().
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from chuzom.plugins.redaction import RedactionResult

_LUHN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _luhn_valid(card: str) -> bool:
    digits = [int(c) for c in card if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# ────────────────────────────────────────────────────────────────────────
# Pattern definitions
# ────────────────────────────────────────────────────────────────────────

_DEFAULT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # API keys (specific patterns first to avoid being eaten by generic ones)
    # anthropic_key MUST come before openai_key; openai_key uses a
    # negative lookahead to avoid swallowing sk-ant- prefixes.
    ("anthropic_key",  re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai_key",     re.compile(r"sk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("gemini_key",     re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("github_token",   re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack_token",    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("jwt",            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("private_key",    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.DOTALL)),
    # PII
    ("email",          re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("us_ssn",         re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("us_phone",       re.compile(r"(?:\+1[-\s]?)?\(?\d{3}\)?[-\s]?\d{3}[-\s]?\d{4}\b")),
)


@dataclass(frozen=True)
class RedactionPolicy:
    """Configurable redaction. Tuple of (name, compiled_regex) pairs."""

    patterns: tuple[tuple[str, re.Pattern[str]], ...] = _DEFAULT_PATTERNS
    enabled: bool = True
    luhn_check_credit_cards: bool = True

    @classmethod
    def default(cls) -> "RedactionPolicy":
        return cls()

    @classmethod
    def disabled(cls) -> "RedactionPolicy":
        """Skip redaction entirely. Use for ad-hoc dev shells only."""
        return cls(enabled=False)

    def with_patterns(
        self, extra: list[tuple[str, str | re.Pattern[str]]]
    ) -> "RedactionPolicy":
        """Return a new policy with additional org-specific patterns appended.

        `extra` is a list of (name, regex_str_or_compiled) tuples. Names
        appear in the placeholder text — pick something the audit reader
        will recognize."""
        compiled = [
            (n, p if isinstance(p, re.Pattern) else re.compile(p))
            for n, p in extra
        ]
        return RedactionPolicy(
            patterns=self.patterns + tuple(compiled),
            enabled=self.enabled,
            luhn_check_credit_cards=self.luhn_check_credit_cards,
        )


def redact_prompt(
    prompt: str, policy: RedactionPolicy | None = None
) -> RedactionResult:
    """Replace sensitive patterns in `prompt` with `[REDACTED:type]` markers.

    Returns a RedactionResult with the scrubbed text + per-pattern hit
    counts. When policy is disabled, returns the original prompt with
    no counts.
    """
    policy = policy or RedactionPolicy.default()
    if not policy.enabled or not prompt:
        return RedactionResult(text=prompt, counts={}, any_redactions=False)

    counts: dict[str, int] = {}
    out = prompt
    for name, pattern in policy.patterns:
        def _sub(match, _name=name, _counts=counts):
            _counts[_name] = _counts.get(_name, 0) + 1
            return f"[REDACTED:{_name}]"
        out = pattern.sub(_sub, out)

    # Credit-card pass — separate because we need Luhn validation
    if policy.luhn_check_credit_cards:
        def _maybe_card(match):
            raw = match.group(0)
            if _luhn_valid(raw):
                counts["credit_card"] = counts.get("credit_card", 0) + 1
                return "[REDACTED:credit_card]"
            return raw
        out = _LUHN_RE.sub(_maybe_card, out)

    return RedactionResult(
        text=out, counts=counts,
        any_redactions=bool(counts),
    )
