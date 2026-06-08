import logging
from datetime import date, datetime
from typing import List, Optional, Iterable, Tuple

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


# ---------------------------------------------------------------------------
# Helpers: DB loading & queries
# ---------------------------------------------------------------------------

async def _execute_query(
  db: AsyncSession,
  stmt,
  error_message: str,
  error_code: str,
  log_extra: Optional[dict] = None,
):
  """
  Execute a SQLAlchemy query with consistent error handling.
  Returns the AsyncResult.
  """
  try:
    return await db.execute(stmt)
  except Exception as exc:
    logger.exception(error_message, extra=log_extra or {})
    raise APIError(500, error_message, code=error_code) from exc


async def _load_leave_type_by_code(
  db: AsyncSession,
  leave_type_code: str,
  employee_id: Optional[int] = None,
) -> models.LeaveType:
  result = await _execute_query(
    db,
    select(models.LeaveType).where(models.LeaveType.code == leave_type_code),
    error_message="Error loading leave type",
    error_code="leave_type_query_failed",
    log_extra={
      "external_user_id": employee_id,
      "leave_type_code": leave_type_code,
    },
  )
  leave_type = result.scalar_one_or_none()
  if not leave_type:
    logger.warning(
      "Invalid leave type requested",
      extra={
        "external_user_id": employee_id,
        "leave_type_code": leave_type_code,
      },
    )
    raise APIError(400, "Invalid leave type", code="invalid_leave_type")
  return leave_type


async def _load_leave_balance_for_employee_and_type(
  db: AsyncSession,
  employee_id: int,
  leave_type_id: int,
  context: str,
) -> models.LeaveBalance:
  """
  Load balance with consistent error handling.
  context is used for logging (e.g. 'apply', 'approve').
  """
  result = await _execute_query(
    db,
    select(models.LeaveBalance).where(
      and_(
        models.LeaveBalance.employee_id == employee_id,
        models.LeaveBalance.leave_type_id == leave_type_id,
      )
    ),
    error_message=f"Error fetching leave balance for {context}",
    error_code="leave_balance_query_failed",
    log_extra={
      "external_user_id": employee_id,
      "leave_type_id": leave_type_id,
    },
  )
  return result.scalar_one_or_none()


async def _load_leave_request_for_update(
  db: AsyncSession,
  leave_request_id: int,
  context: str,
) -> models.LeaveRequest:
  """
  Load LeaveRequest row with FOR UPDATE for approval/rejection flows.
  """
  result = await _execute_query(
    db,
    select(models.LeaveRequest)
    .where(models.LeaveRequest.id == leave_request_id)
    .with_for_update(),
    error_message=f"Error loading leave request for {context}",
    error_code="leave_request_query_failed",
    log_extra={"leave_request_id": leave_request_id},
  )
  leave_req = result.scalar_one_or_none()
  if not leave_req:
    logger.warning(
      "Leave request not found",
      extra={"leave_request_id": leave_request_id, "context": context},
    )
    raise APIError(404, "Leave request not found", code="not_found")
  return leave_req


# ---------------------------------------------------------------------------
# Helpers: validation
# ---------------------------------------------------------------------------

def _validate_leave_dates(
  employee_id: int,
  start_date: date,
  end_date: date,
) -> None:
  today = date.today()

  if start_date < today or end_date < today:
    logger.warning(
      "Leave dates in the past",
      extra={
        "external_user_id": employee_id,
        "start_date": str(start_date),
        "end_date": str(end_date),
      },
    )
    raise APIError(
      400,
      "Leave dates cannot be in the past",
      code="invalid_dates",
    )

  if start_date > end_date:
    logger.warning(
      "Invalid leave date range: start after end",
      extra={
        "external_user_id": employee_id,
        "start_date": str(start_date),
        "end_date": str(end_date),
      },
    )
    raise APIError(
      400,
      "Start date must be before or equal to end date",
      code="invalid_dates",
    )


def _ensure_sufficient_balance(
  employee_id: int,
  leave_type_code: str,
  requested_days: int,
  balance: Optional[models.LeaveBalance],
  context: str,
) -> None:
  if not balance or balance.remaining < requested_days:
    logger.warning(
      "Insufficient leave balance",
      extra={
        "external_user_id": employee_id,
        "leave_type_code": leave_type_code,
        "requested_days": requested_days,
        "remaining": balance.remaining if balance else None,
        "context": context,
      },
    )
    raise APIError(
      400,
      "Insufficient leave balance"
      if context == "apply"
      else "Insufficient leave balance at approval time",
      code="insufficient_balance",
    )


def _ensure_manager_authorized_for_request(
  leave_req: models.LeaveRequest,
  manager_id: int,
  action: str,
) -> None:
  """
  Ensure that the given manager_id is the owner of the leave request.
  """
  if leave_req.reporting_manager_id != manager_id:
    logger.warning(
      f"Manager not authorized to {action} leave request",
      extra={
        "leave_request_id": leave_req.id,
        "manager_external_user_id": manager_id,
        "owner_manager_external_user_id": leave_req.reporting_manager_id,
      },
    )
    raise APIError(
      403,
      f"Not authorized to {action} this request",
      code="not_authorized",
    )


def _ensure_pending_status_for_action(
  leave_req: models.LeaveRequest,
  action: str,
) -> None:
  """
  Ensure leave request is in Pending status for approve/reject actions.
  """
  if leave_req.status != LeaveStatus.pending:
    logger.warning(
      f"Cannot {action} leave request in non-pending status",
      extra={
        "leave_request_id": leave_req.id,
        "current_status": leave_req.status.value,
      },
    )
    raise APIError(
      400,
      f"Only pending requests can be {action}ed",
      code="invalid_status",
    )


# ---------------------------------------------------------------------------
# Helpers: mapping / DTOs
# ---------------------------------------------------------------------------

def _map_leave_balance_rows_to_response(
  employee_id: int,
  rows: Iterable[Tuple[models.LeaveBalance, models.LeaveType]],
) -> LeaveBalanceResponse:
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


def _map_manager_rows_to_leave_request_base(
  rows: Iterable[Tuple[models.LeaveRequest, models.Employee, models.LeaveType]],
) -> List[LeaveRequestBase]:
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


def _map_employee_history_rows_to_leave_request_base(
  employee_id: int,
  rows: Iterable[Tuple[models.LeaveRequest, models.LeaveType]],
) -> List[LeaveRequestBase]:
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
      employee_name="",  # If needed, join Employee to fill this
      reporting_manager_id=lr.reporting_manager_id,
    )
    for lr, lt in rows
  ]


# ---------------------------------------------------------------------------
# Helpers: pagination and filters
# ---------------------------------------------------------------------------

def _apply_pagination(stmt, page: int, page_size: int):
  offset = (page - 1) * page_size
  return stmt.offset(offset).limit(page_size)


def _apply_manager_filters(stmt, filters: ManagerLeaveFilter):
  if filters.status:
    stmt = stmt.where(models.LeaveRequest.status == filters.status)
  if filters.employee_id:
    stmt = stmt.where(models.LeaveRequest.employee_id == filters.employee_id)
  if filters.start_date_from:
    stmt = stmt.where(models.LeaveRequest.start_date >= filters.start_date_from)
  if filters.start_date_to:
    stmt = stmt.where(models.LeaveRequest.start_date <= filters.start_date_to)
  return stmt


def _apply_employee_history_filters(stmt, filters: LeaveHistoryFilter):
  if filters.status:
    stmt = stmt.where(models.LeaveRequest.status == filters.status)
  if filters.start_date_from:
    stmt = stmt.where(models.LeaveRequest.start_date >= filters.start_date_from)
  if filters.start_date_to:
    stmt = stmt.where(models.LeaveRequest.start_date <= filters.start_date_to)
  return stmt


# ---------------------------------------------------------------------------
# Helpers: notifications
# ---------------------------------------------------------------------------

def _publish_leave_notification(event_type: str, data: dict, routing_key: str) -> None:
  payload = {
    "event_type": event_type,
    "data": data,
  }
  publish_notification(payload, routing_key=routing_key)


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

async def get_leave_balance(
  db: AsyncSession,
  employee_id: int,
) -> LeaveBalanceResponse:
  logger.info(
    "Fetching leave balance",
    extra={"external_user_id": employee_id},
  )

  result = await _execute_query(
    db,
    select(models.LeaveBalance, models.LeaveType)
    .join(models.LeaveType, models.LeaveBalance.leave_type_id == models.LeaveType.id)
    .where(models.LeaveBalance.employee_id == employee_id),
    error_message="Error fetching leave balance from DB",
    error_code="leave_balance_query_failed",
    log_extra={"external_user_id": employee_id},
  )
  rows = result.all()

  return _map_leave_balance_rows_to_response(employee_id, rows)


async def apply_for_leave(
  db: AsyncSession,
  employee_id: int,
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

  # Validate dates
  _validate_leave_dates(employee_id, payload.start_date, payload.end_date)

  # Load leave type
  leave_type = await _load_leave_type_by_code(
    db, payload.leave_type_code, employee_id=employee_id
  )

  # Check sufficient balance
  balance = await _load_leave_balance_for_employee_and_type(
    db=db,
    employee_id=employee_id,
    leave_type_id=leave_type.id,
    context="apply",
  )
  _ensure_sufficient_balance(
    employee_id=employee_id,
    leave_type_code=payload.leave_type_code,
    requested_days=payload.days,
    balance=balance,
    context="apply",
  )

  # Check overlapping requests (Pending or Approved)
  overlap_stmt = select(models.LeaveRequest).where(
    and_(
      models.LeaveRequest.employee_id == employee_id,
      models.LeaveRequest.status.in_([LeaveStatus.pending, LeaveStatus.approved]),
      models.LeaveRequest.start_date <= payload.end_date,
      models.LeaveRequest.end_date >= payload.start_date,
    )
  )
  overlap_result = await _execute_query(
    db,
    overlap_stmt,
    error_message="Error checking overlapping leave requests",
    error_code="overlap_query_failed",
    log_extra={"external_user_id": employee_id},
  )
  existing = overlap_result.scalar_one_or_none()
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

  # Create leave request
  leave_req = models.LeaveRequest(
    employee_id=employee_id,
    leave_type_id=leave_type.id,
    start_date=payload.start_date,
    end_date=payload.end_date,
    days=payload.days,
    reason=payload.reason,
    reporting_manager_id=payload.reporting_manager_id,
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
  _publish_leave_notification(
    event_type="leave_applied",
    data={
      "employee_id": leave_req.employee_id,
      "manager_id": leave_req.reporting_manager_id,
      "leave_request_id": leave_req.id,
      "leave_type_id": leave_req.leave_type_id,
      "start_date": str(leave_req.start_date),
      "end_date": str(leave_req.end_date),
      "days": leave_req.days,
    },
    routing_key="notifications.leave.applied",
  )

  return leave_req


async def get_manager_leave_requests(
  db: AsyncSession,
  manager_id: int,
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

  base_stmt = (
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
    .order_by(models.LeaveRequest.created_at.desc())
  )

  stmt = _apply_manager_filters(base_stmt, filters)
  stmt = _apply_pagination(stmt, filters.page, filters.page_size)

  result = await _execute_query(
    db,
    stmt,
    error_message="Error fetching manager leave requests",
    error_code="manager_requests_query_failed",
    log_extra={"manager_external_user_id": manager_id},
  )
  rows = result.all()

  logger.info(
    "Manager leave requests fetched",
    extra={
      "manager_external_user_id": manager_id,
      "result_count": len(rows),
    },
  )

  return _map_manager_rows_to_leave_request_base(rows)


async def approve_leave(
  db: AsyncSession,
  manager_id: int,
  leave_request_id: int,
) -> models.LeaveRequest:
  logger.info(
    "Approving leave request",
    extra={"manager_external_user_id": manager_id, "leave_request_id": leave_request_id},
  )

  leave_req = await _load_leave_request_for_update(
    db, leave_request_id, context="approval"
  )

  _ensure_manager_authorized_for_request(leave_req, manager_id, action="approve")
  _ensure_pending_status_for_action(leave_req, action="approve")

  # Deduct balance
  balance = await _load_leave_balance_for_employee_and_type(
    db=db,
    employee_id=leave_req.employee_id,
    leave_type_id=leave_req.leave_type_id,
    context="approve",
  )
  _ensure_sufficient_balance(
    employee_id=leave_req.employee_id,
    leave_type_code="",
    requested_days=leave_req.days,
    balance=balance,
    context="approve",
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

  _publish_leave_notification(
    event_type="leave_approved",
    data={
      "employee_id": leave_req.employee_id,
      "leave_request_id": leave_req.id,
      "manager_id": manager_id,
    },
    routing_key="notifications.leave.approved",
  )

  return leave_req


async def reject_leave(
  db: AsyncSession,
  manager_id: int,
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

  leave_req = await _load_leave_request_for_update(
    db, leave_request_id, context="rejection"
  )

  _ensure_manager_authorized_for_request(leave_req, manager_id, action="reject")
  _ensure_pending_status_for_action(leave_req, action="reject")

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

  _publish_leave_notification(
    event_type="leave_rejected",
    data={
      "employee_id": leave_req.employee_id,
      "leave_request_id": leave_req.id,
      "manager_id": manager_id,
      "reason": reason,
    },
    routing_key="notifications.leave.rejected",
  )

  return leave_req


async def get_employee_leave_history(
  db: AsyncSession,
  employee_id: int,
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

  base_stmt = (
    select(models.LeaveRequest, models.LeaveType)
    .join(
      models.LeaveType,
      models.LeaveRequest.leave_type_id == models.LeaveType.id,
    )
    .where(models.LeaveRequest.employee_id == employee_id)
    .order_by(models.LeaveRequest.created_at.desc())
  )

  stmt = _apply_employee_history_filters(base_stmt, filters)
  stmt = _apply_pagination(stmt, filters.page, filters.page_size)

  result = await _execute_query(
    db,
    stmt,
    error_message="Error fetching employee leave history",
    error_code="leave_history_query_failed",
    log_extra={"external_user_id": employee_id},
  )
  rows = result.all()

  logger.info(
    "Employee leave history fetched",
    extra={"external_user_id": employee_id, "result_count": len(rows)},
  )

  return _map_employee_history_rows_to_leave_request_base(employee_id, rows)