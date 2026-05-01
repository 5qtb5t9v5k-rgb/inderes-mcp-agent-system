"""OpenTelemetry setup. Console exporter in dev.

MAF emits OTel spans natively; we just need a tracer provider with an exporter.
This module is import-once: `setup_tracing()` is idempotent.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

_initialized = False


def setup_tracing(service_name: str = "inderes-agent") -> None:
    global _initialized
    if _initialized:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _initialized = True


def tracer():
    return trace.get_tracer("inderes_agent")
