# app/main.py
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, users
from app.core.config import settings
from app.core.exceptions import APIError
from app.core import exception_handlers
from app.core.middleware import ExceptionMiddleware
from app.core.logging import configure_logging  # <-- shared logging helper
from app.core.tracing import init_tracing
from app.database.session import AsyncSessionLocal
from app.database.seed_users import seed_initial_users
from app.infra.consul_client import register_service

logger = configure_logging("users-service")

app = FastAPI(
  title="Users Service",
  version="1.0.0",
)

# OpenTelemetry tracing
init_tracing(app, service_name=settings.app_name or "users-service")

# Routers
app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(users.router, prefix="/api/v1/users")


@app.on_event("startup")
async def startup():
  # Register with Consul
  health_url = f"http://{settings.service_name}:{settings.service_port}/health"
  try:
    register_service(
      service_name=settings.service_name,
      port=settings.service_port,
      tags=["users"],
      health_http=health_url,
    )
    logger.info(
      "Registered users-service with Consul",
      extra={
        "service_name": settings.service_name,
        "service_port": settings.service_port,
        "health_url": health_url,
      },
    )
  except Exception as exc:
    logger.error(
      "Failed to register service with Consul",
      extra={
        "service_name": settings.service_name,
        "service_port": settings.service_port,
        "error": str(exc),
      },
    )

  # Seed initial users
  logger.info("Users-service startup: seeding initial users if needed")
  async with AsyncSessionLocal() as db:
    await seed_initial_users(db)
  logger.info("Users-service startup: seeding completed")


# Exception handlers
app.add_exception_handler(
  StarletteHTTPException, exception_handlers.http_exception_handler
)
app.add_exception_handler(
  RequestValidationError, exception_handlers.validation_exception_handler
)
app.add_exception_handler(APIError, exception_handlers.api_error_handler)
app.add_exception_handler(Exception, exception_handlers.generic_exception_handler)

app.add_middleware(ExceptionMiddleware)


@app.get("/health")
async def health():
  logger.debug("Health check called")
  return {"status": "ok"}