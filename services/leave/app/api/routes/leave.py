import logging
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import models
from app.database.session import get_db
from app.schemas.leave import (
  LeaveApplyRequest,
  LeaveBalanceResponse,
  LeaveHistoryFilter,
  ManagerLeaveFilter,
  LeaveRequestBase,
)
from app.services.leave_service import (
  get_leave_balance,
  apply_for_leave,
  get_manager_leave_requests,
  approve_leave,
  reject_leave,
  get_employee_leave_history,
)
from app.api.deps import get_current_user, require_role
from app.database.models import LeaveStatus
from app.schemas.employee import Role

router = APIRouter(prefix="/leave", tags=["leave"])

logger = logging.getLogger("leave-service")


@router.get("/balance", response_model=LeaveBalanceResponse)
async def view_leave_balance(
  db: AsyncSession = Depends(get_db),
  current_user=Depends(get_current_user),
):
  logger.info(
    "API: view_leave_balance",
    extra={"employee_id": current_user.id},
  )
  try:
    resp = await get_leave_balance(db, employee_id=current_user.id)
  except Exception as exc:
    logger.exception(
      "API: view_leave_balance failed",
      extra={"employee_id": current_user.id},
    )
    # Let exception middleware convert to HTTP response
    raise

  logger.info(
    "API: view_leave_balance success",
    extra={
      "employee_id": current_user.id,
      "num_leave_types": len(resp.balances),
    },
  )
  return resp


@router.post("/apply", response_model=LeaveRequestBase)
async def apply_leave(
  payload: LeaveApplyRequest,
  db: AsyncSession = Depends(get_db),
  current_user=Depends(get_current_user),
):
  logger.info(
    "API: apply_leave",
    extra={
      "employee_id": current_user.id,
      "leave_type_code": payload.leave_type_code,
      "start_date": str(payload.start_date),
      "end_date": str(payload.end_date),
      "days": payload.days,
      "reporting_manager_id": payload.reporting_manager_id,
    },
  )
  try:
    lr = await apply_for_leave(db, employee_id=current_user.id, payload=payload)
  except Exception as exc:
    logger.exception(
      "API: apply_leave failed in service layer",
      extra={"employee_id": current_user.id},
    )
    raise

  try:
    dto = await _to_leave_request_base(db, lr)
  except Exception as exc:
    logger.exception(
      "API: apply_leave failed while mapping response",
      extra={"leave_request_id": getattr(lr, "id", None)},
    )
    raise

  logger.info(
    "API: apply_leave success",
    extra={"leave_request_id": dto.id, "employee_id": current_user.id},
  )
  return dto


@router.get("/manager/requests", response_model=List[LeaveRequestBase])
async def manager_view_requests(
  status: LeaveStatus | None = Query(default=None),
  employee_id: int | None = Query(default=None),
  start_date_from: str | None = Query(default=None),
  start_date_to: str | None = Query(default=None),
  page: int = Query(default=1, ge=1),
  page_size: int = Query(default=20, ge=1, le=100),
  db: AsyncSession = Depends(get_db),
  current_user=Depends(require_role(Role.manager.value)),
):
  logger.info(
    "API: manager_view_requests",
    extra={
      "manager_id": current_user.id,
      "status": status.value if status else None,
      "employee_id": employee_id,
      "start_date_from": start_date_from,
      "start_date_to": start_date_to,
      "page": page,
      "page_size": page_size,
    },
  )
  filters = ManagerLeaveFilter(
    status=status,
    employee_id=employee_id,
    start_date_from=start_date_from,
    start_date_to=start_date_to,
    page=page,
    page_size=page_size,
  )

  try:
    items = await get_manager_leave_requests(
      db, manager_id=current_user.id, filters=filters
    )
  except Exception as exc:
    logger.exception(
      "API: manager_view_requests failed",
      extra={"manager_id": current_user.id},
    )
    raise

  logger.info(
    "API: manager_view_requests success",
    extra={"manager_id": current_user.id, "result_count": len(items)},
  )
  return items


@router.post("/{leave_id}/approve", response_model=LeaveRequestBase)
async def approve(
  leave_id: int,
  db: AsyncSession = Depends(get_db),
  current_user=Depends(require_role(Role.manager.value)),
):
  logger.info(
    "API: approve_leave",
    extra={"manager_id": current_user.id, "leave_request_id": leave_id},
  )
  try:
    lr = await approve_leave(
      db, manager_id=current_user.id, leave_request_id=leave_id
    )
  except Exception as exc:
    logger.exception(
      "API: approve_leave failed in service layer",
      extra={"manager_id": current_user.id, "leave_request_id": leave_id},
    )
    raise

  try:
    dto = await _to_leave_request_base(db, lr)
  except Exception as exc:
    logger.exception(
      "API: approve_leave failed while mapping response",
      extra={"leave_request_id": getattr(lr, "id", None)},
    )
    raise

  logger.info(
    "API: approve_leave success",
    extra={
      "leave_request_id": dto.id,
      "employee_id": dto.employee_id,
      "manager_id": current_user.id,
    },
  )
  return dto


@router.post("/{leave_id}/reject", response_model=LeaveRequestBase)
async def reject(
  leave_id: int,
  reason: str,
  db: AsyncSession = Depends(get_db),
  current_user=Depends(require_role(Role.manager.value)),
):
  logger.info(
    "API: reject_leave",
    extra={
      "manager_id": current_user.id,
      "leave_request_id": leave_id,
      "reason": reason,
    },
  )
  try:
    lr = await reject_leave(
      db,
      manager_id=current_user.id,
      leave_request_id=leave_id,
      reason=reason,
    )
  except Exception as exc:
    logger.exception(
      "API: reject_leave failed in service layer",
      extra={"manager_id": current_user.id, "leave_request_id": leave_id},
    )
    raise

  try:
    dto = await _to_leave_request_base(db, lr)
  except Exception as exc:
    logger.exception(
      "API: reject_leave failed while mapping response",
      extra={"leave_request_id": getattr(lr, "id", None)},
    )
    raise

  logger.info(
    "API: reject_leave success",
    extra={
      "leave_request_id": dto.id,
      "employee_id": dto.employee_id,
      "manager_id": current_user.id,
      "reason": reason,
    },
  )
  return dto


@router.get("/history", response_model=List[LeaveRequestBase])
async def history(
  status: LeaveStatus | None = Query(default=None),
  start_date_from: str | None = Query(default=None),
  start_date_to: str | None = Query(default=None),
  page: int = Query(default=1, ge=1),
  page_size: int = Query(default=20, ge=1, le=100),
  db: AsyncSession = Depends(get_db),
  current_user=Depends(get_current_user),
):
  logger.info(
    "API: employee_history",
    extra={
      "employee_id": current_user.id,
      "status": status.value if status else None,
      "start_date_from": start_date_from,
      "start_date_to": start_date_to,
      "page": page,
      "page_size": page_size,
    },
  )
  filters = LeaveHistoryFilter(
    status=status,
    start_date_from=start_date_from,
    start_date_to=start_date_to,
    page=page,
    page_size=page_size,
  )

  try:
    items = await get_employee_leave_history(
      db, employee_id=current_user.id, filters=filters
    )
  except Exception as exc:
    logger.exception(
      "API: employee_history failed",
      extra={"employee_id": current_user.id},
    )
    raise

  logger.info(
    "API: employee_history success",
    extra={"employee_id": current_user.id, "result_count": len(items)},
  )
  return items


# ----- Private helpers -----


async def _to_leave_request_base(
  db: AsyncSession, lr: models.LeaveRequest
) -> LeaveRequestBase:
  """
  Load the necessary joins (Employee, LeaveType) for a single LeaveRequest
  and map it to LeaveRequestBase used as response_model.
  """
  logger.debug(
    "Mapping LeaveRequest to LeaveRequestBase",
    extra={
      "leave_request_id": lr.id,
      "employee_id": lr.employee_id,
      "leave_type_id": lr.leave_type_id,
    },
  )

  try:
    stmt = (
      select(models.LeaveRequest, models.Employee, models.LeaveType)
      .join(models.Employee, models.LeaveRequest.employee_id == models.Employee.id)
      .join(models.LeaveType, models.LeaveRequest.leave_type_id == models.LeaveType.id)
      .where(models.LeaveRequest.id == lr.id)
    )
    result = await db.execute(stmt)
    row = result.first()
  except Exception as exc:
    logger.exception(
      "Error executing join query for LeaveRequestBase",
      extra={"leave_request_id": lr.id},
    )
    raise

  if not row:
    logger.warning(
      "LeaveRequest join query returned no row; returning minimal data",
      extra={"leave_request_id": lr.id},
    )
    return LeaveRequestBase(
      id=lr.id,
      leave_type_code="",
      leave_type_name="",
      start_date=lr.start_date,
      end_date=lr.end_date,
      days=lr.days,
      reason=lr.reason,
      status=lr.status,
      rejection_reason=lr.rejection_reason,
      created_at=lr.created_at,
      updated_at=lr.updated_at,
      employee_id=lr.employee_id,
      employee_name="",
      reporting_manager_id=lr.reporting_manager_id,
    )

  lr_db, emp, lt = row

  dto = LeaveRequestBase(
    id=lr_db.id,
    leave_type_code=lt.code,
    leave_type_name=lt.name,
    start_date=lr_db.start_date,
    end_date=lr_db.end_date,
    days=lr_db.days,
    reason=lr_db.reason,
    status=lr_db.status,
    rejection_reason=lr_db.rejection_reason,
    created_at=lr_db.created_at,
    updated_at=lr_db.updated_at,
    employee_id=emp.id,
    employee_name=emp.full_name,
    reporting_manager_id=lr_db.reporting_manager_id,
  )

  logger.debug(
    "Mapped LeaveRequest to LeaveRequestBase",
    extra={
      "leave_request_id": dto.id,
      "employee_id": dto.employee_id,
      "leave_type_code": dto.leave_type_code,
    },
  )

  return dto