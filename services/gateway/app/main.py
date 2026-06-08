from fastapi import FastAPI

from app.api.routes import auth_proxy, users_proxy, leave_proxy
from app.core.logging import configure_logging
from app.core.request_logging_middleware import LoggerIdMiddleware
from app.core.tracing import init_tracing
from app.core.config import settings
from app.infra.consul_client import register_service

logger = configure_logging("gateway")

app = FastAPI(title="API Gateway", version="1.0.0")

# Middleware for correlation IDs
app.add_middleware(LoggerIdMiddleware)

# OpenTelemetry tracing
init_tracing(app, service_name=settings.app_name or "gateway")

# Register gateway in Consul (port 8000 inside container)
register_service(
  service_name=settings.app_name or "gateway",
  port=8000,
  health_http="http://gateway:8000/health",
)

# Routers
app.include_router(auth_proxy.router)
app.include_router(users_proxy.router)
app.include_router(leave_proxy.router)


@app.get("/health")
async def health():
  return {"status": "ok"}