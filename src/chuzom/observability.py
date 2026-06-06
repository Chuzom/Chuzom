"""OpenTelemetry exporter — send every routing decision as a span + metric.

When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, Chuzom emits:

    Spans      one per routing decision, named ``chuzom.route``,
               attributes capture the full audit: model_chosen, tier,
               task_type, complexity, cost, latency, outcome, agent_id,
               session_id, framework, host, inversion.

    Metrics    Counter:    chuzom.routing.decisions
                          chuzom.routing.inversions{direction}
                          chuzom.safety.pii_catches
               Histogram: chuzom.routing.cost_usd{tier, model}
                          chuzom.routing.latency_ms{tier, model, outcome}

    Logs       WARN  on inversions
               INFO  on PII catches forced to local
               ERROR on budget breaches

Compatible with any OTLP-aware backend: Honeycomb, Grafana Cloud, Datadog,
Jaeger, New Relic, AWS X-Ray, GCP Cloud Trace, local OTel Collector.

Config via standard OTel env vars:

    OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
    OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=KEY
    OTEL_SERVICE_NAME=chuzom          (default: chuzom)
    OTEL_TRACES_EXPORTER=otlp          (auto)
    OTEL_METRICS_EXPORTER=otlp         (auto)
    OTEL_LOGS_EXPORTER=otlp            (auto)

If the OpenTelemetry SDK isn't installed, this module is a no-op — every
function returns silently. Install it via:

    pip install "chuzom-router[tracing]"
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any


_log = logging.getLogger("chuzom.observability")


# ────────────────────────────────────────────────────────────────────────
# Availability detection
# ────────────────────────────────────────────────────────────────────────

def _otel_installed() -> bool:
    try:
        import opentelemetry  # noqa: F401
        from opentelemetry import metrics, trace  # noqa: F401

        return True
    except ImportError:
        return False


def is_enabled() -> bool:
    """True if (a) OTel SDK is importable AND (b) an endpoint is configured.

    Configuration is detected via the standard `OTEL_EXPORTER_OTLP_ENDPOINT`
    env var. If absent, observability is silently disabled regardless of
    whether the SDK is installed — users opt in by setting the endpoint.
    """
    if not _otel_installed():
        return False
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))


# ────────────────────────────────────────────────────────────────────────
# Lazy singleton initialization
# ────────────────────────────────────────────────────────────────────────

_initialized = False
_tracer = None
_meter = None
_counter_decisions = None
_counter_inversions = None
_counter_pii = None
_histogram_cost = None
_histogram_latency = None
_logger = None


def _service_name() -> str:
    return os.environ.get("OTEL_SERVICE_NAME", "chuzom")


def setup(force: bool = False) -> bool:
    """Initialize tracer + meter + logger singletons. Idempotent.

    Returns True if observability was set up (SDK present + endpoint
    configured), False otherwise. Subsequent emit_*() calls only do
    work when this returns True.
    """
    global _initialized, _tracer, _meter, _logger
    global _counter_decisions, _counter_inversions, _counter_pii
    global _histogram_cost, _histogram_latency

    if _initialized and not force:
        return _tracer is not None

    if not is_enabled():
        _initialized = True
        return False

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        _log.debug("OTel SDK not available; observability disabled")
        _initialized = True
        return False

    resource = Resource.create({
        "service.name": _service_name(),
        "service.version": _get_version(),
    })

    # Tracer setup
    span_exporter = _make_span_exporter()
    if span_exporter is not None:
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(_service_name())

    # Meter setup
    metric_exporter = _make_metric_exporter()
    if metric_exporter is not None:
        reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=10_000,
        )
        meter_provider = MeterProvider(
            resource=resource, metric_readers=[reader],
        )
        metrics.set_meter_provider(meter_provider)
        _meter = metrics.get_meter(_service_name())

        _counter_decisions = _meter.create_counter(
            "chuzom.routing.decisions",
            description="Routing decisions made",
        )
        _counter_inversions = _meter.create_counter(
            "chuzom.routing.inversions",
            description="Routing inversions detected (up or down)",
        )
        _counter_pii = _meter.create_counter(
            "chuzom.safety.pii_catches",
            description="PII secret patterns caught and forced to local",
        )
        _histogram_cost = _meter.create_histogram(
            "chuzom.routing.cost_usd",
            description="Cost in USD per routing decision",
            unit="USD",
        )
        _histogram_latency = _meter.create_histogram(
            "chuzom.routing.latency_ms",
            description="Latency in milliseconds per routing decision",
            unit="ms",
        )

    # Logger — use a normal Python logger named 'chuzom.routing' so it
    # propagates through any OTel logging handler the user may have set up.
    _logger = logging.getLogger("chuzom.routing")

    _initialized = True
    _log.info(
        "Chuzom observability ready — exporting to %s",
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"],
    )
    return True


def _get_version() -> str:
    try:
        from chuzom import __version__

        return __version__
    except ImportError:
        return "0.0.0"


def _make_span_exporter():
    """Pick the right OTLP exporter (gRPC or HTTP) based on env."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    try:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
        return OTLPSpanExporter()
    except ImportError as exc:
        _log.warning("OTLP span exporter not available: %s", exc)
        return None


def _make_metric_exporter():
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    try:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
        else:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
        return OTLPMetricExporter()
    except ImportError as exc:
        _log.warning("OTLP metric exporter not available: %s", exc)
        return None


# ────────────────────────────────────────────────────────────────────────
# Public emission API — safe to call when observability is disabled
# ────────────────────────────────────────────────────────────────────────

def emit_routing_decision(record: Any) -> None:
    """Emit a span + metrics for one LineageRecord.

    `record` is a chuzom.lineage.LineageRecord (or any object exposing the
    same field names). Safe no-op when observability isn't initialized.
    """
    if _tracer is None:
        # Try lazy init once — supports the "set env var then start" flow
        if not setup():
            return

    attributes = _record_to_attributes(record)
    tier = attributes.get("chuzom.model_tier", "unknown")
    model = attributes.get("chuzom.model_chosen", "unknown")
    outcome = attributes.get("chuzom.outcome", "success")

    # Span — represent the routing decision as a span lasting latency_ms
    if _tracer is not None:
        latency_ms = getattr(record, "latency_ms", 0) or 0
        start_ns = (
            (getattr(record, "timestamp", time.time()) * 1e9
             - latency_ms * 1e6)
        )
        with _tracer.start_as_current_span(
            "chuzom.route",
            attributes=attributes,
            start_time=int(start_ns),
        ) as span:
            # Emit inversion / pii as span events
            inversion = attributes.get("chuzom.inversion", "none")
            if inversion != "none":
                span.add_event("inversion_detected", {
                    "chuzom.inversion.direction": inversion,
                    "chuzom.expected_tier_for_complexity":
                        attributes.get("chuzom.complexity", "?"),
                })
            notes = getattr(record, "notes", "") or ""
            if "pii" in notes.lower() or "secret" in notes.lower():
                span.add_event("pii_detected")

    # Metrics
    if _counter_decisions is not None:
        metric_attrs = {
            "tier": tier,
            "task_type": attributes.get("chuzom.task_type", "?"),
            "host": attributes.get("chuzom.host", "?"),
        }
        _counter_decisions.add(1, attributes=metric_attrs)
        _histogram_cost.record(
            attributes.get("chuzom.cost_usd", 0.0),
            attributes={"tier": tier, "model": model},
        )
        _histogram_latency.record(
            attributes.get("chuzom.latency_ms", 0),
            attributes={"tier": tier, "model": model, "outcome": outcome},
        )
        inversion = attributes.get("chuzom.inversion", "none")
        if inversion != "none":
            _counter_inversions.add(
                1, attributes={"direction": inversion},
            )

    # Logs
    if _logger is not None:
        inversion = attributes.get("chuzom.inversion", "none")
        if inversion != "none":
            _logger.warning(
                "Routing inversion %s · complexity=%s · model=%s · cost=$%.4f",
                inversion,
                attributes.get("chuzom.complexity", "?"),
                model,
                attributes.get("chuzom.cost_usd", 0.0),
                extra={"chuzom": attributes},
            )


def emit_pii_catch(record: Any) -> None:
    """Emit a counter increment + INFO log when a PII signal forced local routing."""
    if _counter_pii is not None:
        _counter_pii.add(1)
    if _logger is not None:
        _logger.info(
            "PII pattern caught; forced local routing · model=%s",
            getattr(record, "model_chosen", "?"),
        )


def emit_budget_breach(
    session_id: str, cap_usd: float, consumed_usd: float, proposed_usd: float
) -> None:
    """Emit an ERROR log when an agent session breaches its cap."""
    if _logger is not None:
        _logger.error(
            "Budget breach session=%s · cap=$%.2f · consumed=$%.2f · proposed=$%.2f",
            session_id, cap_usd, consumed_usd, proposed_usd,
        )


@contextmanager
def routing_span(name: str = "chuzom.route", **attributes: Any):
    """Context manager for ad-hoc routing instrumentation outside lineage."""
    if _tracer is None:
        if not setup():
            yield None
            return
    with _tracer.start_as_current_span(name, attributes=attributes) as span:
        yield span


# ────────────────────────────────────────────────────────────────────────
# Internal: convert LineageRecord to span attributes
# ────────────────────────────────────────────────────────────────────────

def _record_to_attributes(record: Any) -> dict:
    """Map a LineageRecord (or compatible) to OTel-friendly attributes.

    All keys are prefixed with `chuzom.` to namespace them in the
    backend so they don't collide with other instrumentation."""
    def _get(name, default=""):
        return getattr(record, name, default)

    def _tier_value(t):
        return t.value if hasattr(t, "value") else str(t)

    return {
        "chuzom.host": _get("host", ""),
        "chuzom.task_type": _get("task_type", ""),
        "chuzom.complexity": _get("complexity", ""),
        "chuzom.classifier_method": _get("classifier_method", ""),
        "chuzom.model_chosen": _get("model_chosen", ""),
        "chuzom.model_tier": _tier_value(_get("model_tier", "unknown")),
        "chuzom.inversion": _tier_value(_get("inversion", "none")),
        "chuzom.outcome": _get("outcome", "success"),
        "chuzom.latency_ms": int(_get("latency_ms", 0) or 0),
        "chuzom.cost_usd": float(_get("cost_usd", 0.0) or 0.0),
        "chuzom.agent_id": _get("agent_id", "") or "",
        "chuzom.session_id": _get("session_id", "") or "",
        "chuzom.framework": _get("framework", "") or "",
    }


def reset_for_test() -> None:
    """Reset module state — used by tests to re-init with fresh exporters."""
    global _initialized, _tracer, _meter, _logger
    global _counter_decisions, _counter_inversions, _counter_pii
    global _histogram_cost, _histogram_latency
    _initialized = False
    _tracer = None
    _meter = None
    _logger = None
    _counter_decisions = None
    _counter_inversions = None
    _counter_pii = None
    _histogram_cost = None
    _histogram_latency = None
