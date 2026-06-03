# app/schemas/error.py
from pydantic import BaseModel
from typing import Optional


class ErrorResponse(BaseModel):
  detail: str
  code: Optional[str] = None
  path: Optional[str] = None