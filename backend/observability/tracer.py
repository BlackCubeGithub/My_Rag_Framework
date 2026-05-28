"""
OpenTelemetry Tracer Setup
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource

from backend.config import settings


def setup_tracing(app=None):
    """Initialize OpenTelemetry tracing"""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # lazy import

    resource = Resource.create({
        "service.name": settings.OTEL_SERVICE_NAME,
        "service.version": settings.VERSION,
    })

    provider = TracerProvider(resource=resource)

    if settings.DEBUG:
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))

    trace.set_tracer_provider(provider)

    if app:
        FastAPIInstrumentor.instrument_app(app)

    return trace.get_tracer(settings.OTEL_SERVICE_NAME)


def get_tracer(name: str = None):
    """Get a tracer instance"""
    return trace.get_tracer(name or settings.OTEL_SERVICE_NAME)
