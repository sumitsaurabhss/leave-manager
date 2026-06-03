import logging
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import models
from app.schemas.leave import (
  LeaveBalanceResponse,
  LeaveBalanceItem,
  LeaveApplyRequest,
  ManagerLeaveFilter,
  LeaveRequestBase,
  LeaveHistoryFilter,
)
from app.core.exceptions import APIError
from app.database.models import LeaveStatus
from app.infra.rabbitmq import publish_notification

logger = logging.getLogger("leave-service")


async def get_leave_balance(
  db: AsyncSession,
  employee_id: int,  # external user id
) -> LeaveBalanceResponse:
  logger.info(
    "Fetching leave balance",
    extra={"external_user_id": employee_id},
  )

  try:
    q = (
      select(models.LeaveBalance, models.LeaveType)
      .join(models.LeaveType, models.LeaveBalance.leave_type_id == models.LeaveType.id)
      .where(models.LeaveBalance.employee_id == employee_id)
    )
    result = await db.execute(q)
    rows = result.all()
  except Exception as exc:
    logger.exception(
      "Error fetching leave balance from DB",
      extra={"external_user_id": employee_id},
    )
    raise APIError(
      500,
      "Failed to fetch leave balance",
      code="leave_balance_query_failed",
    ) from exc

  items: List[LeaveBalanceItem] = []
  for balance, leave_type in rows:
    items.append(
      LeaveBalanceItem(
        leave_type_code=leave_type.code,
        leave_type_name=leave_type.name,
        total_allocated=balance.total_allocated,
        used=balance.used,
        remaining=balance.remaining,
      )
    )

  logger.info(
    "Leave balance calculated",
    extra={
      "external_user_id": employee_id,
      "num_leave_types": len(items),
      "leaves": [
        {
          "leave_type_code": i.leave_type_code,
          "total_allocated": i.total_allocated,
          "used": i.used,
          "remaining": i.remaining,
        }
        for i in items
      ],
    },
  )

  return LeaveBalanceResponse(employee_id=employee_id, balances=items)


async def apply_for_leave(
  db: AsyncSession,
  employee_id: int,  # external user id
  payload: LeaveApplyRequest,
) -> models.LeaveRequest:
  logger.info(
    "Applying for leave",
    extra={
      "external_user_id": employee_id,
      "leave_type_code": payload.leave_type_code,
      "start_date": str(payload.start_date),
      "end_date": str(payload.end_date),
      "days": payload.days,
      "reporting_manager_external_user_id": payload.reporting_manager_id,
    },
  )

  # validate dates
  today = date.today()
  if payload.start_date < today or payload.end_date < today:
    logger.warning(
      "Leave dates in the past",
      extra={
        "external_user_id": employee_id,
        "start_date": str(payload.start_date),
        "end_date": str(payload.end_date),
      },
    )
    raise APIError(
      400,
      "Leave dates cannot be in the past",
      code="invalid_dates",
    )
  if payload.start_date > payload.end_date:
    logger.warning(
      "Invalid leave date range: start after end",
      extra={
        "external_user_id": employee_id,
        "start_date": str(payload.start_date),
        "end_date": str(payload.end_date),
      },
    )
    raise APIError(
      400,
      "Start date must be before or equal to end date",
      code="invalid_dates",
    )

  # load leave type
  try:
    result = await db.execute(
      select(models.LeaveType).where(
        models.LeaveType.code == payload.leave_type_code
      )
    )
    leave_type = result.scalar_one_or_none()
  except Exception as exc:
    logger.exception(
      "Error loading leave type",
      extra={
        "external_user_id": employee_id,
        "leave_type_code": payload.leave_type_code,
      },
    )
    raise APIError(
      500,
      "Failed to fetch leave type",
      code="leave_type_query_failed",
    ) from exc

  if not leave_type:
    logger.warning(
      "Invalid leave type requested",
      extra={
        "external_user_id": employee_id,
        "leave_type_code": payload.leave_type_code,
      },
    )
    raise APIError(400, "Invalid leave type", code="invalid_leave_type")

  # check sufficient balance
  try:
    result = await db.execute(
      select(models.LeaveBalance).where(
        and_(
          models.LeaveBalance.employee_id == employee_id,
          models.LeaveBalance.leave_type_id == leave_type.id,
        )
      )
    )
    balance = result.scalar_one_or_none()
  except Exception as exc:
    logger.exception(
      "Error fetching leave balance for apply",
      extra={
        "external_user_id": employee_id,
        "leave_type_id": leave_type.id,
      },
    )
    raise APIError(
      500,
      "Failed to verify leave balance",
      code="leave_balance_query_failed",
    ) from exc

  if not balance or balance.remaining < payload.days:
    logger.warning(
      "Insufficient leave balance",
      extra={
        "external_user_id": employee_id,
        "leave_type_code": payload.leave_type_code,
        "requested_days": payload.days,
        "remaining": balance.remaining if balance else None,
      },
    )
    raise APIError(
      400,
      "Insufficient leave balance",
      code="insufficient_balance",
    )

  # check overlapping requests (Pending or Approved)
  try:
    result = await db.execute(
      select(models.LeaveRequest).where(
        and_(
          models.LeaveRequest.employee_id == employee_id,
          models.LeaveRequest.status.in_(
            [LeaveStatus.pending, LeaveStatus.approved]
          ),
          models.LeaveRequest.start_date <= payload.end_date,
          models.LeaveRequest.end_date >= payload.start_date,
        )
      )
    )
    existing = result.scalar_one_or_none()
  except Exception as exc:
    logger.exception(
      "Error checking overlapping leave requests",
      extra={"external_user_id": employee_id},
    )
    raise APIError(
      500,
      "Failed to check overlapping leave requests",
      code="overlap_query_failed",
    ) from exc

  if existing:
    logger.warning(
      "Overlapping leave request exists",
      extra={
        "external_user_id": employee_id,
        "existing_request_id": existing.id,
        "existing_start": str(existing.start_date),
        "existing_end": str(existing.end_date),
      },
    )
    raise APIError(
      400,
      "Overlapping leave request exists",
      code="overlapping_leave",
    )

  # create leave request
  leave_req = models.LeaveRequest(
    employee_id=employee_id,  # external id
    leave_type_id=leave_type.id,
    start_date=payload.start_date,
    end_date=payload.end_date,
    days=payload.days,
    reason=payload.reason,
    reporting_manager_id=payload.reporting_manager_id,  # external id
    status=LeaveStatus.pending,
  )

  try:
    db.add(leave_req)
    await db.commit()
    await db.refresh(leave_req)
  except Exception as exc:
    logger.exception(
      "Error creating leave request",
      extra={
        "external_user_id": employee_id,
        "leave_type_id": leave_type.id,
      },
    )
    await db.rollback()
    raise APIError(
      500,
      "Failed to create leave request",
      code="leave_create_failed",
    ) from exc

  logger.info(
    "Leave request created",
    extra={
      "leave_request_id": leave_req.id,
      "external_user_id": employee_id,
      "status": leave_req.status.value,
    },
  )

  # Notify employee and manager that leave was applied
  publish_notification(
    {
      "event_type": "leave_applied",
      "data": {
        "employee_id": leave_req.employee_id,
        "manager_id": leave_req.reporting_manager_id,
        "leave_request_id": leave_req.id,
        "leave_type_id": leave_req.leave_type_id,
        "start_date": str(leave_req.start_date),
        "end_date": str(leave_req.end_date),
        "days": leave_req.days,
      },
    },
    routing_key="notifications.leave.applied",
  )

  return leave_req


async def get_manager_leave_requests(
  db: AsyncSession,
  manager_id: int,  # external user id
  filters: ManagerLeaveFilter,
) -> List[LeaveRequestBase]:
  logger.info(
    "Fetching manager leave requests",
    extra={
      "manager_external_user_id": manager_id,
      "status": filters.status.value if filters.status else None,
      "employee_external_user_id": filters.employee_id,
      "start_date_from": str(filters.start_date_from)
      if filters.start_date_from
      else None,
      "start_date_to": str(filters.start_date_to) if filters.start_date_to else None,
      "page": filters.page,
      "page_size": filters.page_size,
    },
  )

  try:
    q = (
      select(models.LeaveRequest, models.Employee, models.LeaveType)
      .join(
        models.Employee,
        models.LeaveRequest.employee_id == models.Employee.external_user_id,
      )
      .join(
        models.LeaveType,
        models.LeaveRequest.leave_type_id == models.LeaveType.id,
      )
      .where(models.LeaveRequest.reporting_manager_id == manager_id)
    )

    if filters.status:
      q = q.where(models.LeaveRequest.status == filters.status)
    if filters.employee_id:
      q = q.where(models.LeaveRequest.employee_id == filters.employee_id)
    if filters.start_date_from:
      q = q.where(models.LeaveRequest.start_date >= filters.start_date_from)
    if filters.start_date_to:
      q = q.where(models.LeaveRequest.start_date <= filters.start_date_to)

    q = q.order_by(models.LeaveRequest.created_at.desc())

    offset = (filters.page - 1) * filters.page_size
    q = q.offset(offset).limit(filters.page_size)

    result = await db.execute(q)
    rows = result.all()
  except Exception as exc:
    logger.exception(
      "Error fetching manager leave requests",
      extra={"manager_external_user_id": manager_id},
    )
    raise APIError(
      500,
      "Failed to fetch manager leave requests",
      code="manager_requests_query_failed",
    ) from exc

  logger.info(
    "Manager leave requests fetched",
    extra={
      "manager_external_user_id": manager_id,
      "result_count": len(rows),
    },
  )

  return [
    LeaveRequestBase(
      id=lr.id,
      leave_type_code=lt.code,
      leave_type_name=lt.name,
      start_date=lr.start_date,
      end_date=lr.end_date,
      days=lr.days,
      reason=lr.reason,
      status=lr.status,
      rejection_reason=lr.rejection_reason,
      created_at=lr.created_at,
      updated_at=lr.updated_at,
      employee_id=emp.external_user_id,
      employee_name=emp.full_name,
      reporting_manager_id=lr.reporting_manager_id,
    )
    for lr, emp, lt in rows
  ]


async def approve_leave(
  db: AsyncSession,
  manager_id: int,  # external user id
  leave_request_id: int,
) -> models.LeaveRequest:
  logger.info(
    "Approving leave request",
    extra={"manager_external_user_id": manager_id, "leave_request_id": leave_request_id},
  )

  try:
    result = await db.execute(
      select(models.LeaveRequest)
      .where(models.LeaveRequest.id == leave_request_id)
      .with_for_update()
    )
    leave_req = result.scalar_one_or_none()
  except Exception as exc:
    logger.exception(
      "Error loading leave request for approval",
      extra={"leave_request_id": leave_request_id},
    )
    raise APIError(
      500,
      "Failed to load leave request",
      code="leave_request_query_failed",
    ) from exc

  if not leave_req:
    logger.warning(
      "Leave request not found for approval",
      extra={"leave_request_id": leave_request_id},
    )
    raise APIError(404, "Leave request not found", code="not_found")

  if leave_req.reporting_manager_id != manager_id:
    logger.warning(
      "Manager not authorized to approve leave request",
      extra={
        "leave_request_id": leave_request_id,
        "manager_external_user_id": manager_id,
        "owner_manager_external_user_id": leave_req.reporting_manager_id,
      },
    )
    raise APIError(
      403,
      "Not authorized to approve this request",
      code="not_authorized",
    )

  if leave_req.status != LeaveStatus.pending:
    logger.warning(
      "Cannot approve leave request in non-pending status",
      extra={
        "leave_request_id": leave_request_id,
        "current_status": leave_req.status.value,
      },
    )
    raise APIError(
      400,
      "Only pending requests can be approved",
      code="invalid_status",
    )

  # deduct balance
  try:
    balance_result = await db.execute(
      select(models.LeaveBalance)
      .where(
        and_(
          models.LeaveBalance.employee_id == leave_req.employee_id,
          models.LeaveBalance.leave_type_id == leave_req.leave_type_id,
        )
      )
      .with_for_update()
    )
    balance = balance_result.scalar_one_or_none()
  except Exception as exc:
    logger.exception(
      "Error fetching balance at approval time",
      extra={
        "employee_external_user_id": leave_req.employee_id,
        "leave_type_id": leave_req.leave_type_id,
      },
    )
    raise APIError(
      500,
      "Failed to verify balance at approval time",
      code="leave_balance_query_failed",
    ) from exc

  if not balance or balance.remaining < leave_req.days:
    logger.warning(
      "Insufficient balance at approval time",
      extra={
        "employee_external_user_id": leave_req.employee_id,
        "leave_type_id": leave_req.leave_type_id,
        "requested_days": leave_req.days,
        "remaining": balance.remaining if balance else None,
      },
    )
    raise APIError(
      400,
      "Insufficient leave balance at approval time",
      code="insufficient_balance",
    )

  balance.used += leave_req.days

  leave_req.status = LeaveStatus.approved
  leave_req.updated_at = datetime.utcnow()

  try:
    await db.commit()
    await db.refresh(leave_req)
  except Exception as exc:
    logger.exception(
      "Error committing approved leave request",
      extra={"leave_request_id": leave_req.id},
    )
    await db.rollback()
    raise APIError(
      500,
      "Failed to approve leave request",
      code="leave_approve_failed",
    ) from exc

  logger.info(
    "Leave request approved",
    extra={
      "leave_request_id": leave_req.id,
      "employee_external_user_id": leave_req.employee_id,
      "manager_external_user_id": manager_id,
    },
  )

  # send notification via RabbitMQ (employee notification on approval)
  publish_notification(
    {
      "event_type": "leave_approved",
      "data": {
        "employee_id": leave_req.employee_id,
        "leave_request_id": leave_req.id,
        "manager_id": manager_id,
      },
    },
    routing_key="notifications.leave.approved",
  )

  return leave_req


async def reject_leave(
  db: AsyncSession,
  manager_id: int,  # external user id
  leave_request_id: int,
  reason: str,
) -> models.LeaveRequest:
  logger.info(
    "Rejecting leave request",
    extra={
      "manager_external_user_id": manager_id,
      "leave_request_id": leave_request_id,
      "reason": reason,
    },
  )

  try:
    result = await db.execute(
      select(models.LeaveRequest)
      .where(models.LeaveRequest.id == leave_request_id)
      .with_for_update()
    )
    leave_req = result.scalar_one_or_none()
  except Exception as exc:
    logger.exception(
      "Error loading leave request for rejection",
      extra={"leave_request_id": leave_request_id},
    )
    raise APIError(
      500,
      "Failed to load leave request",
      code="leave_request_query_failed",
    ) from exc

  if not leave_req:
    logger.warning(
      "Leave request not found for rejection",
      extra={"leave_request_id": leave_request_id},
    )
    raise APIError(404, "Leave request not found", code="not_found")

  if leave_req.reporting_manager_id != manager_id:
    logger.warning(
      "Manager not authorized to reject leave request",
      extra={
        "leave_request_id": leave_request_id,
        "manager_external_user_id": manager_id,
        "owner_manager_external_user_id": leave_req.reporting_manager_id,
      },
    )
    raise APIError(
      403,
      "Not authorized to reject this request",
      code="not_authorized",
    )

  if leave_req.status != LeaveStatus.pending:
    logger.warning(
      "Cannot reject leave request in non-pending status",
      extra={
        "leave_request_id": leave_request_id,
        "current_status": leave_req.status.value,
      },
    )
    raise APIError(
      400,
      "Only pending requests can be rejected",
      code="invalid_status",
    )

  leave_req.status = LeaveStatus.rejected
  leave_req.rejection_reason = reason
  leave_req.updated_at = datetime.utcnow()

  try:
    await db.commit()
    await db.refresh(leave_req)
  except Exception as exc:
    logger.exception(
      "Error committing rejected leave request",
      extra={"leave_request_id": leave_req.id},
    )
    await db.rollback()
    raise APIError(
      500,
      "Failed to reject leave request",
      code="leave_reject_failed",
    ) from exc

  logger.info(
    "Leave request rejected",
    extra={
      "leave_request_id": leave_req.id,
      "employee_external_user_id": leave_req.employee_id,
      "manager_external_user_id": manager_id,
      "reason": reason,
    },
  )

  publish_notification(
    {
      "event_type": "leave_rejected",
      "data": {
        "employee_id": leave_req.employee_id,
        "leave_request_id": leave_req.id,
        "manager_id": manager_id,
        "reason": reason,
      },
    },
    routing_key="notifications.leave.rejected",
  )

  return leave_req


async def get_employee_leave_history(
  db: AsyncSession,
  employee_id: int,  # external user id
  filters: LeaveHistoryFilter,
) -> List[LeaveRequestBase]:
  logger.info(
    "Fetching employee leave history",
    extra={
      "external_user_id": employee_id,
      "status": filters.status.value if filters.status else None,
      "start_date_from": str(filters.start_date_from)
      if filters.start_date_from
      else None,
      "start_date_to": str(filters.start_date_to)
      if filters.start_date_to
      else None,
      "page": filters.page,
      "page_size": filters.page_size,
    },
  )

  try:
    q = (
      select(models.LeaveRequest, models.LeaveType)
      .join(
        models.LeaveType,
        models.LeaveRequest.leave_type_id == models.LeaveType.id,
      )
      .where(models.LeaveRequest.employee_id == employee_id)
    )

    if filters.status:
      q = q.where(models.LeaveRequest.status == filters.status)
    if filters.start_date_from:
      q = q.where(models.LeaveRequest.start_date >= filters.start_date_from)
    if filters.start_date_to:
      q = q.where(models.LeaveRequest.start_date <= filters.start_date_to)

    q = q.order_by(models.LeaveRequest.created_at.desc())
    offset = (filters.page - 1) * filters.page_size
    q = q.offset(offset).limit(filters.page_size)

    result = await db.execute(q)
    rows = result.all()
  except Exception as exc:
    logger.exception(
      "Error fetching employee leave history",
      extra={"external_user_id": employee_id},
    )
    raise APIError(
      500,
      "Failed to fetch leave history",
      code="leave_history_query_failed",
    ) from exc

  logger.info(
    "Employee leave history fetched",
    extra={"external_user_id": employee_id, "result_count": len(rows)},
  )

  return [
    LeaveRequestBase(
      id=lr.id,
      leave_type_code=lt.code,
      leave_type_name=lt.name,
      start_date=lr.start_date,
      end_date=lr.end_date,
      days=lr.days,
      reason=lr.reason,
      status=lr.status,
      rejection_reason=lr.rejection_reason,
      created_at=lr.created_at,
      updated_at=lr.updated_at,
      employee_id=employee_id,
      employee_name="",  # can be filled if you join Employee
      reporting_manager_id=lr.reporting_manager_id,
    )
    for lr, lt in rows
  ]