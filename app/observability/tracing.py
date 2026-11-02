"""Tracing opcional com OpenTelemetry.

Só ativa se ENABLE_TRACING=true E os pacotes opentelemetry-* estiverem
instalados (ver requirements: bloco opcional). Falha de import não derruba a API.
"""

import logging

logger = logging.getLogger(__name__)


def setup_tracing(app, settings) -> None:
    if not settings.enable_tracing:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("ENABLE_TRACING=true mas pacotes opentelemetry não instalados; ignorando.")
        return

    provider = TracerProvider(resource=Resource.create({"service.name": settings.app_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry tracing habilitado.")
