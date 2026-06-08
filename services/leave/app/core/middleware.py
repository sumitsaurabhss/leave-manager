import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.schemas.error import ErrorResponse

logger = logging.getLogger(__name__)


class ExceptionMiddleware(BaseHTTPMiddleware):
  async def dispatch(self, request: Request, call_next):
    try:
      return await call_next(request)
    except Exception as exc:
      logger.exception(f"Unhandled exception in middleware: {exc}")
      return JSONResponse(
        status_code=500,
        content=ErrorResponse(
          detail="Internal Server Error",
          code="internal_error",
          path=request.url.path,
        ).model_dump(),
      )