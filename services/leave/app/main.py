import asyncio

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import leave
from app.api.routes import employee
from app.core.config import settings
from app.core.exception_handlers import (
  http_exception_handler,
  validation_exception_handler,
  api_error_handler,
  generic_exception_handler,
)
from app.core.exceptions import APIError
from app.core.logging import configure_logging
from app.core.tracing import init_tracing
from app.database.session import AsyncSessionLocal, engine
from app.services.seed_service import seed_leave_types
from app.infra.employee_events_consumer import start_employee_events_consumer
from app.infra.consul_client import register_service

logger = configure_logging("leave-service")


app = FastAPI(title="Leave Service", version="1.0.0")

init_tracing(app, service_name=settings.app_name or "leave-service")

app.include_router(leave.router, prefix="/api/v1")
app.include_router(employee.router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
  # register with Consul
  health_url = f"http://{settings.service_name}:{settings.service_port}/health"
  try:
    register_service(
      service_name=settings.service_name,
      port=settings.service_port,
      tags=["leave"],
      health_http=health_url,
    )
    logger.info(
      "Registered leave-service with Consul",
      extra={
        "service_name": settings.service_name,
        "service_port": settings.service_port,
        "health_url": health_url,
      },
    )
  except Exception as exc:
    logger.error(
      "Failed to register leave-service with Consul",
      extra={
        "service_name": settings.service_name,
        "service_port": settings.service_port,
        "error": str(exc),
      },
    )

  logger.info("Seeding leave types if necessary...")
  async with AsyncSessionLocal() as db:
    await seed_leave_types(db)

  logger.info("Starting employee events consumer...")
  asyncio.create_task(start_employee_events_consumer())


# global exception handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(Exception, generic_exception_handler)


@app.get("/health")
async def health():
  return {"status": "ok"}