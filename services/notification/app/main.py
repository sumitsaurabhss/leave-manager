import asyncio

from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.tracing import init_tracing
from app.infra.consul_client import register_service
from app.consumers.leave_consumer import start_leave_notifications_consumer

logger = configure_logging("notification-service")

app = FastAPI(title="Notification Service", version="1.0.0")


@app.on_event("startup")
async def on_startup():
  # Logging
  logger.info("Starting Notification Service (FastAPI)...")

  # Tracing
  init_tracing(service_name=settings.app_name or "notification-service")

  # Consul registration (with HTTP health check)
  service_name = settings.app_name or "notification-service"
  service_port = int(getattr(settings, "service_port", 8003) or 8003)

  # Inside Docker network, the service is reachable by container name + port.
  # If container_name=notification-service, health URL is:
  health_url = f"http://notification-service:{service_port}/health"

  register_service(
    service_name=service_name,
    port=service_port,
    health_http=health_url,
  )

  # Start RabbitMQ consumer in background
  loop = asyncio.get_event_loop()
  loop.create_task(start_leave_notifications_consumer())
  logger.info("Leave notifications consumer started in background")


@app.get("/health")
async def health():
  return {"status": "ok", "service": "notification-service"}