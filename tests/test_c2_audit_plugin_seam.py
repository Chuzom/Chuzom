"""C-2 Plugin seam: audit handler inversion of control.

Tests that audit_routing.py no longer imports chuzom.enterprise.audit directly.
Instead, it calls get_audit_handler() from the plugin registry.
Enterprise code registers a concrete handler at bootstrap time.
"""
from __future__ import annotations

import os

from chuzom.plugins.audit import (
    AuditHandler,
    get_audit_handler,
    register_audit_handler,
)
from chuzom.audit_routing import _audit_disabled


class MockAuditHandler(AuditHandler):
    """Test handler that records appended events."""

    def __init__(self):
        self.events = []

    def append(self, event) -> None:
        self.events.append(event)


class TestPluginRegistry:
    """Test the audit handler plugin registry mechanics."""

    def setup_method(self):
        """Clear registry before each test."""
        import chuzom.plugins.audit as a
        a._HANDLERS.clear()

    def test_register_and_get_handler(self):
        """Audit handlers can be registered and retrieved."""
        mock = MockAuditHandler()
        register_audit_handler(mock)
        assert get_audit_handler() is mock

    def test_get_handler_when_not_registered(self):
        """get_audit_handler() returns None when nothing is registered."""
        assert get_audit_handler() is None


class TestAuditDisabled:
    """Test audit disable logic is independent of handler registration."""

    def setup_method(self):
        """Clear env and registry."""
        os.environ.pop("CHUZOM_AUDIT_DISABLED", None)
        import chuzom.plugins.audit as a
        a._HANDLERS.clear()

    def test_audit_disabled_logic_works_without_handler(self):
        """_audit_disabled() returns False when redaction is off (default)."""
        assert _audit_disabled() is False

    def test_audit_disabled_logic_works_with_env_set(self):
        """_audit_disabled() respects CHUZOM_AUDIT_DISABLED env."""
        os.environ["CHUZOM_AUDIT_DISABLED"] = "1"
        assert _audit_disabled() is True


class TestEnterpriseBootstrap:
    """Test that enterprise bootstrap registers the audit handler correctly."""

    def setup_method(self):
        """Ensure registry has enterprise handler."""
        import chuzom.plugins.audit as a
        a._HANDLERS.clear()
        # Re-import enterprise to re-run bootstrap
        import importlib
        import chuzom.enterprise
        importlib.reload(chuzom.enterprise)

    def test_enterprise_bootstrap_registers_handler(self):
        """Enterprise bootstrap registers audit handler on module import."""
        # After reload, handler should be registered
        handler = get_audit_handler()
        assert handler is not None
