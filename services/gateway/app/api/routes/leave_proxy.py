# app/api/routes/leave_proxy.py
import asyncio
from typing import Optional

import httpx
import pybreaker
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
import logging

from app.core.auth import get_current_user, UserContext
from app.core.circuit import leave_cb
from app.infra.service_discovery import discover_service_url

router = APIRouter(prefix="/leave", tags=["leave"])
logger = logging.getLogger("gateway.leave")


async def get_leave_base_url() -> str:
  """
  Resolve base URL for leave-service via Consul in a thread,
  to avoid blocking the event loop.
  """
  return await asyncio.to_thread(discover_service_url, "leave-service")


def _user_headers(current_user: UserContext, logger_id: Optional[str]) -> dict:
  headers = {
    "X-User-Id": str(current_user.user_id),
    "X-User-Email": current_user.email,
    "X-User-Role": current_user.role,
  }
  if logger_id:
    headers["X-Logger-Id"] = logger_id
  return headers


@router.get("/balance")
async def proxy_leave_balance(
  request: Request,
  current_user: UserContext = Depends(get_current_user),
):
  """
  Proxy GET /api/v1/leave/balance.
  """
  try:
    base_url = await get_leave_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for leave-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service discovery error: {exc}",
    )

  url = f"{base_url}/api/v1/leave/balance"
  logger_id = request.headers.get("x-logger-id")

  logger.info(
    "Proxying leave balance to leave-service",
    extra={"url": url},
  )

  @leave_cb
  def call_leave():
    with httpx.Client() as client:
      return client.get(
        url,
        headers=_user_headers(current_user, logger_id),
        timeout=5.0,
      )

  try:
    resp = await asyncio.to_thread(call_leave)
  except pybreaker.CircuitBreakerError:
    logger.warning(
      "Circuit breaker open for leave-service /balance",
      extra={"url": url},
    )
    raise HTTPException(
      status_code=503,
      detail="Leave service temporarily disabled",
    )
  except Exception as exc:
    logger.exception(
      "Error calling leave-service /balance",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service error: {exc}",
    )

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Leave-service returned error for /balance",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()


@router.post("/apply")
async def proxy_apply_leave(
  request: Request,
  payload: dict,
  current_user: UserContext = Depends(get_current_user),
):
  """
  Proxy POST /api/v1/leave/apply.
  """
  try:
    base_url = await get_leave_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for leave-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service discovery error: {exc}",
    )

  url = f"{base_url}/api/v1/leave/apply"
  logger_id = request.headers.get("x-logger-id")

  logger.info(
    "Proxying leave apply to leave-service",
    extra={"url": url},
  )

  @leave_cb
  def call_leave():
    with httpx.Client() as client:
      return client.post(
        url,
        json=payload,
        headers=_user_headers(current_user, logger_id),
        timeout=5.0,
      )

  try:
    resp = await asyncio.to_thread(call_leave)
  except pybreaker.CircuitBreakerError:
    logger.warning(
      "Circuit breaker open for leave-service /apply",
      extra={"url": url},
    )
    raise HTTPException(
      status_code=503,
      detail="Leave service temporarily disabled",
    )
  except Exception as exc:
    logger.exception(
      "Error calling leave-service /apply",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service error: {exc}",
    )

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Leave-service returned error for /apply",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()


@router.get("/manager/requests")
async def proxy_manager_view_requests(
  request: Request,
  status: Optional[str] = Query(default=None),
  employee_id: Optional[int] = Query(default=None),
  start_date_from: Optional[str] = Query(default=None),
  start_date_to: Optional[str] = Query(default=None),
  page: int = Query(default=1, ge=1),
  page_size: int = Query(default=20, ge=1, le=100),
  current_user: UserContext = Depends(get_current_user),
):
  """
  Proxy GET /api/v1/leave/manager/requests.
  The leave service enforces manager role.
  """
  try:
    base_url = await get_leave_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for leave-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service discovery error: {exc}",
    )

  url = f"{base_url}/api/v1/leave/manager/requests"

  params = {
    "page": page,
    "page_size": page_size,
  }
  if status is not None:
    params["status"] = status
  if employee_id is not None:
    params["employee_id"] = employee_id
  if start_date_from is not None:
    params["start_date_from"] = start_date_from
  if start_date_to is not None:
    params["start_date_to"] = start_date_to

  logger_id = request.headers.get("x-logger-id")

  logger.info(
    "Proxying manager leave requests to leave-service",
    extra={"url": url, "params": params},
  )

  @leave_cb
  def call_leave():
    with httpx.Client() as client:
      return client.get(
        url,
        params=params,
        headers=_user_headers(current_user, logger_id),
        timeout=5.0,
      )

  try:
    resp = await asyncio.to_thread(call_leave)
  except pybreaker.CircuitBreakerError:
    logger.warning(
      "Circuit breaker open for leave-service /manager/requests",
      extra={"url": url},
    )
    raise HTTPException(
      status_code=503,
      detail="Leave service temporarily disabled",
    )
  except Exception as exc:
    logger.exception(
      "Error calling leave-service /manager/requests",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service error: {exc}",
    )

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Leave-service returned error for /manager/requests",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()


@router.post("/{leave_id}/approve")
async def proxy_approve_leave(
  request: Request,
  leave_id: int = Path(...),
  current_user: UserContext = Depends(get_current_user),
):
  """
  Proxy POST /api/v1/leave/{leave_id}/approve.
  """
  try:
    base_url = await get_leave_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for leave-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service discovery error: {exc}",
    )

  url = f"{base_url}/api/v1/leave/{leave_id}/approve"
  logger_id = request.headers.get("x-logger-id")

  logger.info(
    "Proxying approve leave to leave-service",
    extra={"url": url, "leave_id": leave_id},
  )

  @leave_cb
  def call_leave():
    with httpx.Client() as client:
      return client.post(
        url,
        headers=_user_headers(current_user, logger_id),
        timeout=5.0,
      )

  try:
    resp = await asyncio.to_thread(call_leave)
  except pybreaker.CircuitBreakerError:
    logger.warning(
      "Circuit breaker open for leave-service /approve",
      extra={"url": url},
    )
    raise HTTPException(
      status_code=503,
      detail="Leave service temporarily disabled",
    )
  except Exception as exc:
    logger.exception(
      "Error calling leave-service /approve",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service error: {exc}",
    )

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Leave-service returned error for /approve",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()


@router.post("/{leave_id}/reject")
async def proxy_reject_leave(
  request: Request,
  leave_id: int = Path(...),
  reason: str = Query(...),
  current_user: UserContext = Depends(get_current_user),
):
  """
  Proxy POST /api/v1/leave/{leave_id}/reject?reason=...
  """
  try:
    base_url = await get_leave_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for leave-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service discovery error: {exc}",
    )

  url = f"{base_url}/api/v1/leave/{leave_id}/reject"
  params = {"reason": reason}
  logger_id = request.headers.get("x-logger-id")

  logger.info(
    "Proxying reject leave to leave-service",
    extra={"url": url, "leave_id": leave_id, "reason": reason},
  )

  @leave_cb
  def call_leave():
    with httpx.Client() as client:
      return client.post(
        url,
        params=params,
        headers=_user_headers(current_user, logger_id),
        timeout=5.0,
      )

  try:
    resp = await asyncio.to_thread(call_leave)
  except pybreaker.CircuitBreakerError:
    logger.warning(
      "Circuit breaker open for leave-service /reject",
      extra={"url": url},
    )
    raise HTTPException(
      status_code=503,
      detail="Leave service temporarily disabled",
    )
  except Exception as exc:
    logger.exception(
      "Error calling leave-service /reject",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service error: {exc}",
    )

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Leave-service returned error for /reject",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()


@router.get("/history")
async def proxy_leave_history(
  request: Request,
  status: Optional[str] = Query(default=None),
  start_date_from: Optional[str] = Query(default=None),
  start_date_to: Optional[str] = Query(default=None),
  page: int = Query(default=1, ge=1),
  page_size: int = Query(default=20, ge=1, le=100),
  current_user: UserContext = Depends(get_current_user),
):
  """
  Proxy GET /api/v1/leave/history.
  """
  try:
    base_url = await get_leave_base_url()
  except Exception as exc:
    logger.error(
      "Service discovery failed for leave-service",
      extra={"error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service discovery error: {exc}",
    )

  url = f"{base_url}/api/v1/leave/history"

  params = {
    "page": page,
    "page_size": page_size,
  }
  if status is not None:
    params["status"] = status
  if start_date_from is not None:
    params["start_date_from"] = start_date_from
  if start_date_to is not None:
    params["start_date_to"] = start_date_to

  logger_id = request.headers.get("x-logger-id")

  logger.info(
    "Proxying leave history to leave-service",
    extra={"url": url, "params": params},
  )

  @leave_cb
  def call_leave():
    with httpx.Client() as client:
      return client.get(
        url,
        params=params,
        headers=_user_headers(current_user, logger_id),
        timeout=5.0,
      )

  try:
    resp = await asyncio.to_thread(call_leave)
  except pybreaker.CircuitBreakerError:
    logger.warning(
      "Circuit breaker open for leave-service /history",
      extra={"url": url},
    )
    raise HTTPException(
      status_code=503,
      detail="Leave service temporarily disabled",
    )
  except Exception as exc:
    logger.exception(
      "Error calling leave-service /history",
      extra={"url": url, "error": str(exc)},
    )
    raise HTTPException(
      status_code=503,
      detail=f"Leave service error: {exc}",
    )

  if resp.status_code >= 400:
    try:
      detail = resp.json()
    except Exception:
      detail = resp.text
    logger.warning(
      "Leave-service returned error for /history",
      extra={"status_code": resp.status_code, "detail": detail},
    )
    raise HTTPException(status_code=resp.status_code, detail=detail)

  return resp.json()