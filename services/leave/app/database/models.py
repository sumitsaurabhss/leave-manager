import enum
from datetime import date, datetime

from sqlalchemy import (
  Column,
  Integer,
  String,
  Boolean,
  Date,
  DateTime,
  Enum,
  ForeignKey,
  UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database.base import Base


class LeaveStatus(str, enum.Enum):
  pending = "pending"
  approved = "approved"
  rejected = "rejected"
  cancelled = "cancelled"


class Employee(Base):
  __tablename__ = "employees"

  id = Column(Integer, primary_key=True, index=True)
  external_user_id = Column(Integer, unique=True, index=True, nullable=False)
  full_name = Column(String, nullable=False)
  email = Column(String, nullable=False)

  leave_balances = relationship("LeaveBalance", back_populates="employee")

  leave_requests = relationship(
    "LeaveRequest",
    back_populates="employee",
    foreign_keys="LeaveRequest.employee_id",
  )


class LeaveType(Base):
  __tablename__ = "leave_types"

  id = Column(Integer, primary_key=True, index=True)
  code = Column(String, unique=True, index=True, nullable=False)
  name = Column(String, nullable=False)
  annual_allocation = Column(Integer, nullable=False)


class LeaveBalance(Base):
  __tablename__ = "leave_balances"
  __table_args__ = (
    UniqueConstraint("employee_id", "leave_type_id", name="uq_balance_employee_type"),
  )

  id = Column(Integer, primary_key=True, index=True)
  employee_id = Column(Integer, ForeignKey("employees.external_user_id"), nullable=False)
  leave_type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False)
  total_allocated = Column(Integer, nullable=False, default=0)
  used = Column(Integer, nullable=False, default=0)

  employee = relationship("Employee", back_populates="leave_balances")
  leave_type = relationship("LeaveType")

  @property
  def remaining(self) -> int:
    return self.total_allocated - self.used


class LeaveRequest(Base):
  __tablename__ = "leave_requests"

  id = Column(Integer, primary_key=True, index=True)
  employee_id = Column(Integer, ForeignKey("employees.external_user_id"), nullable=False)
  leave_type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False)

  start_date = Column(Date, nullable=False)
  end_date = Column(Date, nullable=False)
  days = Column(Integer, nullable=False)
  reason = Column(String, nullable=True)

  reporting_manager_id = Column(Integer, ForeignKey("employees.external_user_id"), nullable=False)

  status = Column(Enum(LeaveStatus), default=LeaveStatus.pending, nullable=False)
  rejection_reason = Column(String, nullable=True)

  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
  updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

  employee = relationship("Employee", foreign_keys=[employee_id], back_populates="leave_requests")
  leave_type = relationship("LeaveType")
  reporting_manager = relationship("Employee", foreign_keys=[reporting_manager_id])