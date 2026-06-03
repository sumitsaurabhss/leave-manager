import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
import httpx
import pybreaker

from app.core.auth import get_current_user, UserContext
from app.core.config import settings
from app.core.circuit import users_cb

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def proxy_me(
  request: Request,
  current_user: UserContext = Depends(get_current_user),
):
  """
  Proxy to GET /api/v1/users/me.
  """
  url = f"{settings.users_service_url}/api/v1/users/me"
  auth_header = request.headers.get("authorization")
  logger_id = request.headers.get("x-logger-id")

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
    raise HTTPException(status_code=503, detail="Users service temporarily disabled")
  except Exception as exc:
    raise HTTPException(status_code=503, detail=f"Users service error: {exc}")

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
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
  url = f"{settings.users_service_url}/api/v1/users/"
  auth_header = request.headers.get("authorization")
  logger_id = request.headers.get("x-logger-id")

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
    raise HTTPException(status_code=503, detail="Users service temporarily disabled")
  except Exception as exc:
    raise HTTPException(status_code=503, detail=f"Users service error: {exc}")

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()