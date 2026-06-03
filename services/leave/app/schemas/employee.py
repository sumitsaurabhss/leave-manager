# services/leave/app/schemas/employee.py
import enum

from pydantic import BaseModel, EmailStr
from typing import Optional


class Role(str, enum.Enum):
  employee = "employee"
  manager = "manager"


class EmployeeCreate(BaseModel):
  external_user_id: int
  full_name: Optional[str]
  email: EmailStr
  # manager_external_id: Optional[int] = None


class EmployeeOut(BaseModel):
  id: int
  external_user_id: int
  full_name: Optional[str]
  email: EmailStr

  class Config:
    from_attributes = True