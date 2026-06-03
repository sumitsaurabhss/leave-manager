# app/schemas/leave.py
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from app.database.models import LeaveStatus


class LeaveBalanceItem(BaseModel):
  leave_type_code: str
  leave_type_name: str
  total_allocated: int
  used: int
  remaining: int


class LeaveBalanceResponse(BaseModel):
  employee_id: int
  balances: List[LeaveBalanceItem]


class LeaveApplyRequest(BaseModel):
  leave_type_code: str
  start_date: date
  end_date: date
  days: int
  reason: Optional[str] = None
  reporting_manager_id: int


class LeaveRequestBase(BaseModel):
  id: int
  leave_type_code: str
  leave_type_name: str
  start_date: date
  end_date: date
  days: int
  reason: Optional[str]
  status: LeaveStatus
  rejection_reason: Optional[str]
  created_at: datetime
  updated_at: datetime
  employee_id: int
  employee_name: str
  reporting_manager_id: int


class LeaveHistoryFilter(BaseModel):
  status: Optional[LeaveStatus] = None
  start_date_from: Optional[date] = None
  start_date_to: Optional[date] = None
  page: int = Field(default=1, ge=1)
  page_size: int = Field(default=20, ge=1, le=100)


class ManagerLeaveFilter(BaseModel):
  status: Optional[LeaveStatus] = None
  employee_id: Optional[int] = None
  start_date_from: Optional[date] = None
  start_date_to: Optional[date] = None
  page: int = Field(default=1, ge=1)
  page_size: int = Field(default=20, ge=1, le=100)
