import enum
from sqlalchemy import Column, Integer, String, Enum, Boolean
from sqlalchemy.orm import relationship
from app.database.base import Base


class Role(str, enum.Enum):
  employee = "employee"
  manager = "manager"


class User(Base):
  __tablename__ = "users"

  id = Column(Integer, primary_key=True, index=True)
  email = Column(String, unique=True, index=True, nullable=False)
  full_name = Column(String, nullable=True)
  hashed_password = Column(String, nullable=False)
  role = Column(Enum(Role), nullable=False, default=Role.employee)