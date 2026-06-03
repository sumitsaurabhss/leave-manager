import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import APIError
from app.schemas.error import ErrorResponse

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
  # Override default FastAPI HTTPException JSON format if you want
  logger.warning(f"HTTPException: {exc.detail} path={request.url.path}")
  return JSONResponse(
    status_code=exc.status_code,
    content=ErrorResponse(
      detail=str(exc.detail),
      code=str(exc.status_code),
      path=request.url.path,
    ).model_dump(),
  )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
  logger.info(f"Validation error on path={request.url.path}: {exc.errors()}")
  return JSONResponse(
    status_code=422,
    content=ErrorResponse(
      detail="Validation error",
      code="validation_error",
      path=request.url.path,
    ).model_dump(),
  )


async def api_error_handler(request: Request, exc: APIError):
  logger.error(f"APIError: {exc.detail} path={request.url.path}")
  return JSONResponse(
    status_code=exc.status_code,
    content=ErrorResponse(
      detail=exc.detail,
      code=exc.code,
      path=request.url.path,
    ).model_dump(),
  )


async def generic_exception_handler(request: Request, exc: Exception):
  logger.exception(f"Unhandled exception on path={request.url.path}: {exc}")
  return JSONResponse(
    status_code=500,
    content=ErrorResponse(
      detail="Internal Server Error",
      code="internal_error",
      path=request.url.path,
    ).model_dump(),
  )