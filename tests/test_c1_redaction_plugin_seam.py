"""C-1 Plugin seam: redaction inversion of control.

Tests that redaction_routing.py no longer imports chuzom.enterprise.redaction
directly. Instead, it calls get_redactor() from the plugin registry.
Enterprise code registers a concrete redactor at bootstrap time.
"""
from __future__ import annotations

import os
import pytest

from chuzom.plugins.redaction import (
    Redactor,
    RedactionResult,
    get_redactor,
    register_redactor,
)
from chuzom.redaction_routing import maybe_redact


# Test utilities

class MockRedactor(Redactor):
    """Test redactor that prefixes with [MOCK]."""

    def redact_prompt(self, prompt: str) -> RedactionResult:
        # Match enterprise redaction behavior: empty prompts return unchanged
        if not prompt:
            return RedactionResult(text=prompt, counts={}, any_redactions=False)
        return RedactionResult(
            text=f"[MOCK] {prompt}",
            counts={"mock": 1},
            any_redactions=True,
        )


class FailingRedactor(Redactor):
    """Test redactor that always fails."""

    def redact_prompt(self, prompt: str) -> RedactionResult:
        raise ValueError("redactor is broken")


# Tests

class TestPluginRegistry:
    """Test the redactor plugin registry mechanics."""

    def setup_method(self):
        """Clear registry before each test."""
        # Access private dict to clear it
        import chuzom.plugins.redaction as r
        r._REDACTORS.clear()

    def test_register_and_get_redactor(self):
        """Redactors can be registered and retrieved."""
        mock = MockRedactor()
        register_redactor(mock)
        assert get_redactor() is mock

    def test_get_redactor_when_not_registered(self):
        """get_redactor() returns None when nothing is registered."""
        assert get_redactor() is None

    def test_register_named_redactor(self):
        """Redactors can be registered with custom names."""
        mock = MockRedactor()
        register_redactor(mock, name="custom")
        assert get_redactor(name="custom") is mock
        assert get_redactor() is None  # default is still empty


class TestMaybeRedactNoPlugin:
    """Test maybe_redact behavior when no plugin is registered."""

    def setup_method(self):
        """Clear registry and disable redaction env."""
        import chuzom.plugins.redaction as r
        r._REDACTORS.clear()
        os.environ.pop("CHUZOM_REDACTION", None)

    def test_redaction_off_no_plugin(self):
        """CHUZOM_REDACTION=off returns prompt unchanged, no plugin needed."""
        os.environ["CHUZOM_REDACTION"] = "off"
        prompt = "secret api key sk-ant-12345"
        text, counts = maybe_redact(prompt)
        assert text == prompt
        assert counts == {}

    def test_redaction_on_but_no_plugin_fails_open(self):
        """CHUZOM_REDACTION=on with no plugin returns prompt unchanged, logs warning."""
        os.environ["CHUZOM_REDACTION"] = "on"
        prompt = "secret api key sk-ant-12345"
        text, counts = maybe_redact(prompt)
        assert text == prompt
        assert counts == {}


class TestMaybeRedactWithPlugin:
    """Test maybe_redact behavior when a plugin is registered."""

    def setup_method(self):
        """Clear registry and register a test redactor."""
        import chuzom.plugins.redaction as r
        r._REDACTORS.clear()
        os.environ.pop("CHUZOM_REDACTION", None)
        register_redactor(MockRedactor())

    def test_redaction_off_ignores_plugin(self):
        """CHUZOM_REDACTION=off skips redaction even if plugin is registered."""
        os.environ["CHUZOM_REDACTION"] = "off"
        prompt = "test prompt"
        text, counts = maybe_redact(prompt)
        assert text == prompt
        assert counts == {}

    def test_redaction_on_uses_plugin(self):
        """CHUZOM_REDACTION=on uses the registered plugin."""
        os.environ["CHUZOM_REDACTION"] = "on"
        prompt = "test prompt"
        text, counts = maybe_redact(prompt)
        assert text == "[MOCK] test prompt"
        assert counts == {"mock": 1}

    def test_redaction_on_empty_prompt(self):
        """Redaction skips empty prompts."""
        os.environ["CHUZOM_REDACTION"] = "on"
        text, counts = maybe_redact("")
        assert text == ""
        assert counts == {}


class TestMaybeRedactFailureHandling:
    """Test that broken redactors fail open."""

    def setup_method(self):
        """Clear registry and register a failing redactor."""
        import chuzom.plugins.redaction as r
        r._REDACTORS.clear()
        os.environ.pop("CHUZOM_REDACTION", None)
        register_redactor(FailingRedactor())

    def test_failing_redactor_fails_open(self):
        """If plugin.redact_prompt() raises, return prompt unchanged."""
        os.environ["CHUZOM_REDACTION"] = "on"
        prompt = "test prompt"
        text, counts = maybe_redact(prompt)
        assert text == prompt
        assert counts == {}


class TestEnterpriseBootstrap:
    """Test that enterprise bootstrap registers the redactor correctly."""

    def test_enterprise_bootstrap_registers_redactor(self):
        """After importing chuzom.enterprise, redactor is registered."""
        # Clear registry first
        import chuzom.plugins.redaction as r
        r._REDACTORS.clear()

        # Import enterprise (which calls bootstrap in __init__)
        import chuzom.enterprise  # noqa: F401

        # Redactor should now be registered
        redactor = get_redactor()
        assert redactor is not None

    def test_enterprise_redactor_redacts_api_keys(self):
        """Enterprise redactor should redact known API key patterns."""
        import chuzom.enterprise  # noqa: F401

        os.environ["CHUZOM_REDACTION"] = "on"
        prompt = "Use this key: sk-ant-abcd1234efgh5678ijkl9012"
        text, counts = maybe_redact(prompt)

        # Should contain redaction marker
        assert "[REDACTED:" in text
        assert "anthropic_key" in counts
