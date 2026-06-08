from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

security = HTTPBearer()


class UserContext:
  def __init__(self, user_id: int, email: str, role: str):
    self.user_id = user_id
    self.email = email
    self.role = role


def get_current_user(
  credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserContext:
  token = credentials.credentials
  try:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
  except jwt.ExpiredSignatureError:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
  except jwt.PyJWTError:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or malformed token")

  user_id: Optional[int] = payload.get("user_id")
  email: Optional[str] = payload.get("email") or payload.get("sub")
  role: Optional[str] = payload.get("role")

  if user_id is None or email is None:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Invalid token payload",
    )

  return UserContext(user_id=user_id, email=email, role=role or "employee")