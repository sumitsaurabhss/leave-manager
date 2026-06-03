import asyncio

from fastapi import APIRouter, HTTPException, Depends, Request
import httpx
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.circuit import users_cb

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def proxy_register_user(
  payload: dict,
  request: Request,
):
  """
  Proxy to POST /api/v1/auth/register on users-service.
  """
  url = f"{settings.users_service_url}/api/v1/auth/register"

  logger_id = request.headers.get("x-logger-id")

  @users_cb
  def call_users():
    with httpx.Client() as client:
      headers = {}
      if logger_id:
        headers["X-Logger-Id"] = logger_id
      return client.post(url, json=payload, headers=headers, timeout=5.0)

  try:
    resp = await asyncio.to_thread(call_users)
  except Exception as exc:
    raise HTTPException(status_code=503, detail=f"Users service error: {exc}")

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()


@router.post("/token")
async def proxy_login_for_access_token(
  request: Request,
  form_data: OAuth2PasswordRequestForm = Depends(),
):
  """
  Proxy to POST /api/v1/auth/token on users-service.
  Mirrors FastAPI's OAuth2PasswordRequestForm, so the client sends
  application/x-www-form-urlencoded with 'username' and 'password'.
  """
  url = f"{settings.users_service_url}/api/v1/auth/token"

  form_dict = {
    "username": form_data.username,
    "password": form_data.password,
  }

  logger_id = request.headers.get("x-logger-id")

  @users_cb
  def call_users():
    with httpx.Client() as client:
      headers = {
        "Content-Type": "application/x-www-form-urlencoded",
      }
      if logger_id:
        headers["X-Logger-Id"] = logger_id

      return client.post(
        url,
        data=form_dict,  # forwards as form-encoded
        headers=headers,
        timeout=5.0,
      )

  try:
    resp = await asyncio.to_thread(call_users)
  except Exception as exc:
    raise HTTPException(status_code=503, detail=f"Users service error: {exc}")

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()