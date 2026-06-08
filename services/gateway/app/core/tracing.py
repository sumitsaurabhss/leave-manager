import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

logger = logging.getLogger("tracing")


def init_tracing(app, service_name: str) -> None:
  """
  Initialize OpenTelemetry tracing for a FastAPI app and httpx.
  """
  otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

  resource = Resource.create(
    attributes={
      "service.name": service_name,
    }
  )

  provider = TracerProvider(resource=resource)
  exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
  span_processor = BatchSpanProcessor(exporter)
  provider.add_span_processor(span_processor)
  trace.set_tracer_provider(provider)

  # Instrument FastAPI and httpx
  FastAPIInstrumentor.instrument_app(app)
  HTTPXClientInstrumentor().instrument()

  logger.info(
    "Tracing initialized",
    extra={
      "service_name": service_name,
      "otlp_endpoint": otlp_endpoint,
    },
  )