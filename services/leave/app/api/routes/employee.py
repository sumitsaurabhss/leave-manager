import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.employee import EmployeeCreate, EmployeeOut
from app.services.employee_service import create_employee_with_balances

from app.services.leave_service import get_leave_balance

router = APIRouter(prefix="/employees", tags=["employees"])

logger = logging.getLogger("leave-service")


@router.post("/", response_model=EmployeeOut, status_code=201)
async def register_employee(
  payload: EmployeeCreate,
  db: AsyncSession = Depends(get_db),
):
  logger.info(
    "API: register_employee (leave-service)",
    extra={
      "external_user_id": payload.external_user_id,
      "email": payload.email,
      "full_name": payload.full_name,
    },
  )

  employee = await create_employee_with_balances(
    db=db,
    external_user_id=payload.external_user_id,
    full_name=payload.full_name,
    email=payload.email,
  )
  leave_balance = await get_leave_balance(db, employee_id=employee.id)
  return employee