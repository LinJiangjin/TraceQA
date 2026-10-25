"""OpenTelemetry。

为什么一开始就埋：FDE 交付后要回答"为什么慢""为什么贵""为什么答错了"，
没有 trace 就只能靠猜。上线后再补埋点的成本是现在的十倍。
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.config import get_settings

settings = get_settings()


def setup_tracing() -> None:
    provider = TracerProvider(resource=Resource.create({"service.name": settings.app_name}))

    if settings.otel_endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint)))
    elif settings.debug:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)


def get_tracer(name: str = "tracingqa"):
    return trace.get_tracer(name)
