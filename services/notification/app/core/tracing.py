# app/core/tracing.py (notification-service)
import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

logger = logging.getLogger("notification-service.tracing")


def init_tracing(service_name: str) -> None:
  """
  Initialize OpenTelemetry tracing for a non-HTTP notification service.
  You can create spans manually using trace.get_tracer().
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

  logger.info(
    "Tracing initialized (notification-service, no FastAPI instrumentation)",
    extra={
      "service_name": service_name,
      "otlp_endpoint": otlp_endpoint,
    },
  )