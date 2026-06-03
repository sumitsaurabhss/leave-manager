# app/api/routes/users_proxy.py
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
import httpx
import pybreaker

from app.core.auth import get_current_user, UserContext
from app.core.circuit import users_cb
from app.infra.service_discovery import discover_service_url

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger("gateway.users")


async def get_users_base_url() -> str:
  return await asyncio.to_thread(discover_service_url, "users-service")


@router.get("/me")
async def proxy_me(
  request: Request,
  current_user: UserContext = Depends(get_current_user),
):
  """
  Proxy to GET /api/v1/users/me.
  """
  try:
    base_url = await get_users_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for users-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(status_code=503, detail=f"Users service discovery error: {exc}")

  url = f"{base_url}/api/v1/users/me"
  auth_header = request.headers.get("authorization")
  logger_id = request.headers.get("x-logger-id")

  logger.info(
    "Proxying /users/me to users-service",
    extra={"url": url},
  )

  @users_cb
  def call_users():
    with httpx.Client() as client:
      headers = {
        "X-User-Id": str(current_user.user_id),
        "X-User-Email": current_user.email,
        "X-User-Role": current_user.role,
      }
      if auth_header:
        headers["Authorization"] = auth_header
      if logger_id:
        headers["X-Logger-Id"] = logger_id

      return client.get(url, headers=headers, timeout=5.0)

  try:
    resp = await asyncio.to_thread(call_users)
  except pybreaker.CircuitBreakerError:
    logger.warning(
      "Circuit breaker open for users-service /users/me",
      extra={"url": url},
    )
    raise HTTPException(status_code=503, detail="Users service temporarily disabled")
  except Exception as exc:
    logger.exception(
      "Error calling users-service /users/me",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(status_code=503, detail=f"Users service error: {exc}")

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Users-service returned error for /users/me",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()


@router.get("/")
async def proxy_list_users(
  request: Request,
  current_user: UserContext = Depends(get_current_user),
):
  """
  Proxy to GET /api/v1/users/, intended for managers.
  """
  try:
    base_url = await get_users_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for users-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(status_code=503, detail=f"Users service discovery error: {exc}")

  url = f"{base_url}/api/v1/users/"
  auth_header = request.headers.get("authorization")
  logger_id = request.headers.get("x-logger-id")

  logger.info(
    "Proxying /users/ to users-service",
    extra={"url": url},
  )

  @users_cb
  def call_users():
    with httpx.Client() as client:
      headers = {
        "X-User-Id": str(current_user.user_id),
        "X-User-Email": current_user.email,
        "X-User-Role": current_user.role,
      }
      if auth_header:
        headers["Authorization"] = auth_header
      if logger_id:
        headers["X-Logger-Id"] = logger_id

      return client.get(url, headers=headers, timeout=5.0)

  try:
    resp = await asyncio.to_thread(call_users)
  except pybreaker.CircuitBreakerError:
    logger.warning(
      "Circuit breaker open for users-service /users/",
      extra={"url": url},
    )
    raise HTTPException(status_code=503, detail="Users service temporarily disabled")
  except Exception as exc:
    logger.exception(
      "Error calling users-service /users/",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(status_code=503, detail=f"Users service error: {exc}")

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Users-service returned error for /users/",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()