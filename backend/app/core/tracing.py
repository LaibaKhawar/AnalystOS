"""OpenTelemetry tracing.

One trace per analysis: `analysis` -> `plan` / `tool.<name>` (-> `sql.execute`, `sandbox.run`) / `llm.<purpose>`.
Spans are exported over OTLP/HTTP when OTEL_EXPORTER_OTLP_ENDPOINT is set (Jaeger, Tempo, Honeycomb, ...);
otherwise a provider without exporters is installed, so instrumentation costs almost nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import get_settings

_configured = False


def configure_tracing(service_name: str = "analystos", extra_processor: SpanProcessor | None = None) -> None:
    """Install the tracer provider once per process (API and worker call this at startup)."""
    global _configured
    if _configured and extra_processor is None:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    endpoint = get_settings().otel_exporter_otlp_endpoint
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")))
    if extra_processor is not None:
        provider.add_span_processor(extra_processor)
    trace.set_tracer_provider(provider)
    _configured = True


def tracer() -> trace.Tracer:
    return trace.get_tracer("analystos")


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    """Start a child span; attributes with None values are skipped, others are coerced to str/int/float/bool."""
    with tracer().start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value if isinstance(value, str | int | float | bool) else str(value))
        yield current
