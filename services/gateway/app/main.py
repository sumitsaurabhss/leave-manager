from fastapi import FastAPI

from app.api.routes import auth_proxy, users_proxy, leave_proxy
from app.core.logging import configure_logging
from app.core.request_logging_middleware import LoggerIdMiddleware

logger = configure_logging("gateway")  # root logger for gateway

app = FastAPI(title="API Gateway", version="1.0.0")

app.add_middleware(LoggerIdMiddleware)

app.include_router(auth_proxy.router)
app.include_router(users_proxy.router)
app.include_router(leave_proxy.router)


@app.get("/health")
async def health():
  return {"status": "ok"}