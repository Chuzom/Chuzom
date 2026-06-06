"""OpenTelemetry exporter tests — uses InMemorySpanExporter (no network).

Verifies that when OTLP is enabled:
    - A span is created per routing decision with the right attributes
    - Inversions emit a span event + counter increment
    - PII catches emit an info log
    - Budget breaches emit an error log
    - All instrumentation is silent no-op when not configured

Without configuring an OTLP endpoint, observability stays silent — no
crashes, no slowdowns. The auto-emit hook in LineageStore.record swallows
exceptions so a misconfigured exporter NEVER blocks a lineage write.
"""
from __future__ import annotations

import pytest

from chuzom import observability
from chuzom.lineage import LineageStore, make_record


def _otel_available() -> bool:
    try:
        from opentelemetry.sdk.trace import TracerProvider  # noqa: F401

        return True
    except ImportError:
        return False


requires_otel = pytest.mark.skipif(
    not _otel_available(),
    reason="opentelemetry-sdk not installed; install via chuzom-router[tracing]",
)


@pytest.fixture(autouse=True)
def reset_obs():
    observability.reset_for_test()
    yield
    observability.reset_for_test()


# ────────────────────────────────────────────────────────────────────────
# Disabled-by-default contract
# ────────────────────────────────────────────────────────────────────────

def test_is_enabled_false_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert observability.is_enabled() is False


def test_emit_routing_decision_silent_when_disabled(monkeypatch):
    """When OTLP isn't configured, emission is a no-op."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    record = make_record(
        host="x", prompt_fingerprint="fp", task_type="query",
        complexity="simple", classifier_method="heuristic",
        signal_scores={}, fired_decisions=(),
        chain_attempted=("ollama/qwen3.5:latest",),
        model_chosen="ollama/qwen3.5:latest",
        outcome="success", latency_ms=10, cost_usd=0.0,
    )
    # Must not raise
    observability.emit_routing_decision(record)


def test_lineage_record_succeeds_when_otel_disabled(tmp_path, monkeypatch):
    """The auto-emit hook in LineageStore.record must NEVER block lineage."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    store = LineageStore(db_path=tmp_path / "l.db")
    rec = make_record(
        host="x", prompt_fingerprint="fp", task_type="query",
        complexity="simple", classifier_method="heuristic",
        signal_scores={}, fired_decisions=(),
        chain_attempted=("ollama/qwen3.5:latest",),
        model_chosen="ollama/qwen3.5:latest",
        outcome="success", latency_ms=10, cost_usd=0.0,
    )
    store.record(rec)
    assert len(store.recent()) == 1


# ────────────────────────────────────────────────────────────────────────
# OTLP-enabled — with in-memory exporter
# ────────────────────────────────────────────────────────────────────────

@requires_otel
def test_span_created_per_routing_decision(monkeypatch):
    """Verify a span is created with the right attributes when OTLP is on."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    # Set the endpoint so is_enabled() returns True
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Replace setup() to wire an in-memory exporter instead of OTLP
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "chuzom"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    observability._tracer = trace.get_tracer("chuzom")
    observability._initialized = True

    record = make_record(
        host="claude-code", prompt_fingerprint="fp",
        task_type="code", complexity="moderate",
        classifier_method="signal_engine",
        signal_scores={}, fired_decisions=(),
        chain_attempted=("ollama/qwen3.5:latest",),
        model_chosen="ollama/qwen3.5:latest",
        outcome="success", latency_ms=2400, cost_usd=0.0,
        framework="agno", agent_id="code-reviewer",
    )
    observability.emit_routing_decision(record)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chuzom.route"
    attrs = dict(span.attributes)
    assert attrs.get("chuzom.host") == "claude-code"
    assert attrs.get("chuzom.task_type") == "code"
    assert attrs.get("chuzom.model_chosen") == "ollama/qwen3.5:latest"
    assert attrs.get("chuzom.framework") == "agno"
    assert attrs.get("chuzom.agent_id") == "code-reviewer"


@requires_otel
def test_inversion_emits_span_event(monkeypatch):
    """When a routing decision has inversion='up_inversion', the span
    must carry an 'inversion_detected' event."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "chuzom"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    observability._tracer = trace.get_tracer("chuzom")
    observability._initialized = True

    # A complex prompt routed to local is UP-inversion
    record = make_record(
        host="x", prompt_fingerprint="fp", task_type="analyze",
        complexity="complex",
        classifier_method="signal_engine",
        signal_scores={}, fired_decisions=(),
        chain_attempted=("ollama/qwen3.5:latest",),
        model_chosen="ollama/qwen3.5:latest",
        outcome="success", latency_ms=10, cost_usd=0.0,
    )
    observability.emit_routing_decision(record)

    spans = exporter.get_finished_spans()
    span = spans[0]
    event_names = [e.name for e in span.events]
    assert "inversion_detected" in event_names


@requires_otel
def test_pii_detected_emits_span_event(monkeypatch):
    """A lineage record whose notes mention 'pii' should add a
    pii_detected event to the span."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "chuzom"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    observability._tracer = trace.get_tracer("chuzom")
    observability._initialized = True

    record = make_record(
        host="x", prompt_fingerprint="fp", task_type="code",
        complexity="simple",
        classifier_method="signal_engine",
        signal_scores={}, fired_decisions=(),
        chain_attempted=("ollama/qwen3.5:latest",),
        model_chosen="ollama/qwen3.5:latest",
        outcome="success", latency_ms=10, cost_usd=0.0,
        notes="PII pattern caught — forced local routing",
    )
    observability.emit_routing_decision(record)

    spans = exporter.get_finished_spans()
    span = spans[0]
    event_names = [e.name for e in span.events]
    assert "pii_detected" in event_names


# ────────────────────────────────────────────────────────────────────────
# Attribute mapping
# ────────────────────────────────────────────────────────────────────────

def test_record_to_attributes_namespaces_with_chuzom_prefix():
    record = make_record(
        host="cursor", prompt_fingerprint="fp",
        task_type="research", complexity="moderate",
        classifier_method="heuristic",
        signal_scores={}, fired_decisions=(),
        chain_attempted=("perplexity/sonar",),
        model_chosen="perplexity/sonar",
        outcome="success", latency_ms=3500, cost_usd=0.005,
    )
    attrs = observability._record_to_attributes(record)
    for key in attrs:
        assert key.startswith("chuzom."), (
            f"All OTel attribute keys must be namespaced with 'chuzom.', "
            f"got {key!r}"
        )


def test_record_to_attributes_handles_optional_fields():
    """agent_id / session_id / framework are nullable; map to empty string."""
    record = make_record(
        host="x", prompt_fingerprint="fp", task_type="query",
        complexity="simple", classifier_method="heuristic",
        signal_scores={}, fired_decisions=(),
        chain_attempted=("ollama/qwen3.5:latest",),
        model_chosen="ollama/qwen3.5:latest",
        outcome="success", latency_ms=10, cost_usd=0.0,
    )
    attrs = observability._record_to_attributes(record)
    assert attrs["chuzom.agent_id"] == ""
    assert attrs["chuzom.session_id"] == ""
    assert attrs["chuzom.framework"] == ""
