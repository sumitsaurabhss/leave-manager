# app/services/employee_service.py
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import models
from app.core.exceptions import APIError

logger = logging.getLogger("leave-service")


async def create_employee_with_balances(
  db: AsyncSession,
  external_user_id: int,
  full_name: str,
  email: str,
) -> models.Employee:
  logger.info(
    "Creating employee in leave-service",
    extra={
      "external_user_id": external_user_id,
      "email": email,
      "full_name": full_name,
    },
  )

  # Phase 1: check if employee exists
  try:
    result = await db.execute(
      select(models.Employee).where(
        models.Employee.external_user_id == external_user_id
      )
    )
    existing = result.scalar_one_or_none()
  except Exception as exc:
    logger.exception(
      "Error querying existing employee in leave-service",
      extra={"external_user_id": external_user_id},
    )
    raise APIError(
      500,
      "Failed to query existing employee",
      code="employee_query_failed",
    ) from exc

  if existing:
    logger.warning(
      "Employee already exists in leave-service",
      extra={"external_user_id": external_user_id, "employee_id": existing.id},
    )
    raise APIError(
      400,
      "Employee already exists in leave service",
      code="employee_exists",
    )

  # Phase 2: create employee row (internal id auto-generated, external_user_id fixed)
  try:
    employee = models.Employee(
      external_user_id=external_user_id,
      full_name=full_name,
      email=email,
    )
    db.add(employee)
    await db.flush()
  except Exception as exc:
    logger.exception(
      "Error creating employee record in leave-service",
      extra={"external_user_id": external_user_id, "email": email},
    )
    raise APIError(
      500,
      "Failed to create employee in leave service",
      code="employee_create_failed",
    ) from exc

  logger.info(
    "Employee record created in leave-service (pending balances)",
    extra={
      "employee_db_id": employee.id,
      "external_user_id": external_user_id,
    },
  )

  # Phase 3: fetch leave types
  try:
    lt_result = await db.execute(select(models.LeaveType))
    leave_types = lt_result.scalars().all()
  except Exception as exc:
    logger.exception(
      "Error fetching leave types for employee",
      extra={
        "external_user_id": external_user_id,
        "employee_db_id": employee.id,
      },
    )
    raise APIError(
      500,
      "Failed to fetch leave types",
      code="leave_types_query_failed",
    ) from exc

  if not leave_types:
    logger.error(
      "Leave types not configured; cannot create balances",
      extra={
        "external_user_id": external_user_id,
        "employee_db_id": employee.id,
      },
    )
    raise APIError(
      500,
      "Leave types not configured",
      code="leave_types_missing",
    )

  # Phase 4: create balances keyed by external_user_id
  balances: list[models.LeaveBalance] = []
  try:
    for lt in leave_types:
      balance = models.LeaveBalance(
        employee_id=external_user_id,  # <- external id, not employee.id
        leave_type_id=lt.id,
        total_allocated=lt.annual_allocation,
        used=0,
      )
      balances.append(balance)
      logger.debug(
        "Initializing leave balance for employee",
        extra={
          "external_user_id": external_user_id,
          "leave_type_code": lt.code,
          "annual_allocation": lt.annual_allocation,
        },
      )

    db.add_all(balances)

    # Phase 5: commit everything
    await db.commit()
    await db.refresh(employee)
  except Exception as exc:
    logger.exception(
      "Error creating leave balances for employee; rolling back",
      extra={
        "external_user_id": external_user_id,
        "employee_db_id": getattr(employee, "id", None),
      },
    )
    await db.rollback()
    raise APIError(
      500,
      "Failed to create leave balances",
      code="leave_balances_create_failed",
    ) from exc

  # Final: log summary of leave balances
  balance_summary = [
    {
      "leave_type_id": b.leave_type_id,
      "total_allocated": b.total_allocated,
      "used": b.used,
    }
    for b in balances
  ]

  logger.info(
    "Employee created with initial leave balances",
    extra={
      "external_user_id": external_user_id,
      "employee_db_id": employee.id,
      "leave_balances": balance_summary,
    },
  )

  return employee