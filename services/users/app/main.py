# app/main.py
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, users
from app.core.exceptions import APIError
from app.core import exception_handlers
from app.core.middleware import ExceptionMiddleware
from app.core.logging import configure_logging  # <-- shared logging helper
from app.database.session import AsyncSessionLocal
from app.database.seed_users import seed_initial_users

logger = configure_logging("users-service")

app = FastAPI(
  title="Users Service",
  version="1.0.0",
)

# Routers
app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(users.router, prefix="/api/v1/users")


@app.on_event("startup")
async def seed_initial_manager():
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