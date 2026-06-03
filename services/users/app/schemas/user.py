from pydantic import BaseModel, EmailStr
from typing import Optional
from app.database.models import Role


class UserBase(BaseModel):
  email: EmailStr
  full_name: Optional[str] = None
  role: Role = Role.employee


class UserCreate(UserBase):
  password: str


class UserOut(UserBase):
  id: int

  class Config:
    from_attributes = True