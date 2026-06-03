# app/api/routes/auth_proxy.py
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Depends, Request
import httpx
from fastapi.security import OAuth2PasswordRequestForm

from app.core.circuit import users_cb
from app.infra.service_discovery import discover_service_url

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("gateway.auth")


async def get_users_base_url() -> str:
  # Wrap blocking discovery in a thread to avoid blocking event loop
  return await asyncio.to_thread(discover_service_url, "users-service")


@router.post("/register")
async def proxy_register_user(
  payload: dict,
  request: Request,
):
  """
  Proxy to POST /api/v1/auth/register on users-service.
  """
  try:
    base_url = await get_users_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for users-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(status_code=503, detail=f"Users service discovery error: {exc}")

  url = f"{base_url}/api/v1/auth/register"
  logger.info(
    "Proxying register to users-service",
    extra={"url": url},
  )

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
    logger.exception(
      "Error calling users-service for register",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(status_code=503, detail=f"Users service error: {exc}")

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Users-service returned error for register",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()


@router.post("/token")
async def proxy_login_for_access_token(
  request: Request,
  form_data: OAuth2PasswordRequestForm = Depends(),
):
  """
  Proxy to POST /api/v1/auth/token on users-service.
  """
  try:
    base_url = await get_users_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for users-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(status_code=503, detail=f"Users service discovery error: {exc}")

  url = f"{base_url}/api/v1/auth/token"
  logger.info(
    "Proxying token request to users-service",
    extra={"url": url},
  )

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
        data=form_dict,
        headers=headers,
        timeout=5.0,
      )

  try:
    resp = await asyncio.to_thread(call_users)
  except Exception as exc:
    logger.exception(
      "Error calling users-service for token",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(status_code=503, detail=f"Users service error: {exc}")

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Users-service returned error for token",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()