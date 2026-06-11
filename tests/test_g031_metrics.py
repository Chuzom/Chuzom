"""G-031 — Prometheus exposition endpoint on the admin API.

The metrics module is intentionally dep-free (no ``prometheus_client``
in the runtime requirements) so the exposition-format renderer lives
in ``chuzom.metrics``. Tests cover both layers:

* Renderer + escaping primitives are pure functions and trivially
  unit-testable.
* The endpoint integration confirms the right collectors fire, the
  Content-Type matches the Prometheus 0.0.4 protocol, and the
  ``# HELP`` / ``# TYPE`` headers appear before the samples.

Auth model is intentionally **unauthenticated** by default — that's
the Prometheus convention. The tests pin that contract so a future
"close /metrics by default" refactor doesn't quietly break scrapers.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from chuzom.admin_actions import AdminActionLog
from chuzom.admin_api import (
    RuntimeProviderRegistry,
    create_app,
    get_admin_action_log,
    get_audit_log,
    get_identity_store,
    get_policy_version_store,
    get_provider_registry,
    get_session_store,
)
from chuzom.agents.session import SessionStore
from chuzom.enterprise.audit import AuditEvent, AuditLog
from chuzom.enterprise.identity import IdentityStore
from chuzom.metrics import (
    Metric,
    _escape_label_value,
    _render_labels,
    collect_all,
    render,
)
from chuzom.policy_versions import PolicyVersionStore


# ── 1. Renderer primitives ──────────────────────────────────────────────────


def test_escape_label_value_backslash_and_quote() -> None:
    assert _escape_label_value('a"b\\c') == 'a\\"b\\\\c'


def test_escape_label_value_newline() -> None:
    assert _escape_label_value("line1\nline2") == "line1\\nline2"


def test_escape_label_value_plain_string_unchanged() -> None:
    assert _escape_label_value("ollama/llama3") == "ollama/llama3"


def test_render_labels_empty() -> None:
    assert _render_labels({}) == ""


def test_render_labels_sorted_alphabetically() -> None:
    """Sorted output makes the exposition deterministic — diff-able
    across scrapes."""
    assert _render_labels({"b": "2", "a": "1"}) == '{a="1",b="2"}'


def test_render_single_counter_metric() -> None:
    m = Metric(
        name="chuzom_test_total",
        help_text="A test counter.",
        kind="counter",
        samples=(({"foo": "bar"}, 5.0),),
    )
    output = render([m])
    lines = output.splitlines()
    assert lines[0] == "# HELP chuzom_test_total A test counter."
    assert lines[1] == "# TYPE chuzom_test_total counter"
    assert lines[2] == 'chuzom_test_total{foo="bar"} 5.0'


def test_render_multiple_metrics_separator() -> None:
    """Each metric prints its own HELP+TYPE; samples follow."""
    m1 = Metric("a", "First", "gauge", (({}, 1.0),))
    m2 = Metric("b", "Second", "counter", (({}, 2.0),))
    out = render([m1, m2])
    # The order of metric blocks matches the input order.
    assert out.index("# HELP a") < out.index("# HELP b")
    assert "a 1.0" in out
    assert "b 2.0" in out


def test_render_unlabelled_metric_omits_braces() -> None:
    m = Metric("x", "h", "gauge", (({}, 3.14),))
    out = render([m])
    assert "x 3.14" in out
    assert "x{} 3.14" not in out


def test_render_trailing_newline_per_spec() -> None:
    """The exposition spec requires a trailing newline."""
    out = render([Metric("x", "h", "gauge", (({}, 1.0),))])
    assert out.endswith("\n")


# ── 2. Collectors with broken inputs degrade gracefully ────────────────────


def test_collect_all_swallows_broken_collectors(tmp_path: Path) -> None:
    """Pass a sessions store whose connection is closed — the
    collector raises mid-iteration, but the renderer still produces
    a Prometheus-shaped block (with empty samples). Pinning this so
    one broken subsystem cannot take down the whole scrape."""
    sessions = SessionStore(
        db_path=tmp_path / "sessions.db", check_same_thread=False,
    )
    sessions._conn.close()  # force any query to fail
    output = collect_all(
        sessions=sessions,
        include_subscription_pressure=False,
    )
    # Headers still appear (the metric is "expected absent" but its
    # shape is announced).
    assert "# HELP chuzom_session_count" in output
    assert "# TYPE chuzom_session_count gauge" in output


# ── 3. Endpoint integration ────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> IdentityStore:
    return IdentityStore(
        db_path=tmp_path / "identity.db", check_same_thread=False
    )


@pytest.fixture
def audit_log(tmp_path: Path) -> AuditLog:
    return AuditLog(db_path=tmp_path / "audit.db", check_same_thread=False)


@pytest.fixture
def admin_log(tmp_path: Path) -> AdminActionLog:
    return AdminActionLog(
        db_path=tmp_path / "admin_actions.db", check_same_thread=False
    )


@pytest.fixture
def registry() -> RuntimeProviderRegistry:
    return RuntimeProviderRegistry()


@pytest.fixture
def sessions(tmp_path: Path) -> SessionStore:
    return SessionStore(
        db_path=tmp_path / "sessions.db", check_same_thread=False
    )


@pytest.fixture
def policy_store(tmp_path: Path) -> PolicyVersionStore:
    return PolicyVersionStore(
        db_path=tmp_path / "policy_versions.db", check_same_thread=False
    )


@pytest.fixture
def app_with_admin(
    store: IdentityStore,
    audit_log: AuditLog,
    admin_log: AdminActionLog,
    registry: RuntimeProviderRegistry,
    sessions: SessionStore,
    policy_store: PolicyVersionStore,
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: store
    app.dependency_overrides[get_audit_log] = lambda: audit_log
    app.dependency_overrides[get_admin_action_log] = lambda: admin_log
    app.dependency_overrides[get_provider_registry] = lambda: registry
    app.dependency_overrides[get_session_store] = lambda: sessions
    app.dependency_overrides[get_policy_version_store] = lambda: policy_store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_metrics_endpoint_returns_200_unauthenticated(
    app_with_admin: TestClient,
) -> None:
    """Prometheus convention: ``/metrics`` is open. Pinning that
    contract so future "lock everything" refactors don't break
    scrapers without thought."""
    resp = app_with_admin.get("/metrics")
    assert resp.status_code == 200


def test_metrics_endpoint_content_type_is_prometheus_format(
    app_with_admin: TestClient,
) -> None:
    resp = app_with_admin.get("/metrics")
    assert "text/plain" in resp.headers["content-type"]
    assert "version=0.0.4" in resp.headers["content-type"]


def test_metrics_body_contains_session_count_with_sample(
    app_with_admin: TestClient, sessions: SessionStore,
) -> None:
    sessions.create(agent_id="a", budget_usd=1.0)
    sessions.create(agent_id="b", budget_usd=1.0)
    body = app_with_admin.get("/metrics").text
    assert "# TYPE chuzom_session_count gauge" in body
    # The actual sample line carries a state label and the count.
    assert 'chuzom_session_count{state="active"} 2.0' in body


def test_metrics_body_contains_admin_action_counter(
    app_with_admin: TestClient, admin_log: AdminActionLog,
) -> None:
    admin_log.append(
        actor_user_id="u", actor_email="a@x",
        action="provider:disable", resource_id="openai", detail={},
    )
    body = app_with_admin.get("/metrics").text
    assert "# TYPE chuzom_admin_actions_total counter" in body
    assert (
        'chuzom_admin_actions_total{action="provider:disable"} 1.0'
        in body
    )


def test_metrics_body_contains_audit_chain_length(
    app_with_admin: TestClient, audit_log: AuditLog,
) -> None:
    for i in range(3):
        audit_log.append(AuditEvent(
            type="t", actor_id=f"a{i}", actor_email=f"a{i}@x",
            org_id="o", resource="r", action="x", detail={},
        ))
    body = app_with_admin.get("/metrics").text
    assert "chuzom_audit_chain_length 3.0" in body


def test_metrics_body_contains_disabled_providers_and_models(
    app_with_admin: TestClient, registry: RuntimeProviderRegistry,
) -> None:
    registry.disable("openai", reason="x")
    registry.disable_model("anthropic/claude-haiku", reason="x")
    body = app_with_admin.get("/metrics").text
    assert "chuzom_disabled_providers 1.0" in body
    assert "chuzom_disabled_models 1.0" in body


def test_metrics_body_contains_policy_active_version(
    app_with_admin: TestClient, policy_store: PolicyVersionStore,
) -> None:
    # No version pushed yet → -1 sentinel.
    pre = app_with_admin.get("/metrics").text
    assert "chuzom_policy_active_version -1.0" in pre
    # Push one — version 1 is active.
    policy_store.push(
        yaml_text="name: v1\n",
        actor_user_id="u", actor_email="u@x",
    )
    post = app_with_admin.get("/metrics").text
    assert "chuzom_policy_active_version 1.0" in post


def test_metrics_body_emits_self_cost_gauge(
    app_with_admin: TestClient,
) -> None:
    """The scrape-cost gauge must appear so operators can graph it."""
    body = app_with_admin.get("/metrics").text
    assert "# TYPE chuzom_metrics_render_seconds gauge" in body
    # The value is non-negative.
    line = next(
        ln for ln in body.splitlines()
        if ln.startswith("chuzom_metrics_render_seconds ")
    )
    value = float(line.split()[-1])
    assert value >= 0.0


def test_metrics_body_has_help_before_type_before_sample(
    app_with_admin: TestClient,
) -> None:
    """Spec invariant — header lines come before the first sample
    for every metric. Pinning the order so a future "buffer
    metrics in a dict" refactor doesn't accidentally interleave
    them."""
    body = app_with_admin.get("/metrics").text
    name = "chuzom_audit_chain_length"
    help_pos = body.index(f"# HELP {name}")
    type_pos = body.index(f"# TYPE {name}")
    # The first sample line: name followed by space + number.
    sample_pos = next(
        i for i, line in enumerate(body.splitlines())
        if line.startswith(f"{name} ")
    )
    sample_char = sum(
        len(ln) + 1
        for ln in body.splitlines()[:sample_pos]
    )
    assert help_pos < type_pos < sample_char
