import logging
from fastapi import Depends, Header, HTTPException, status

logger = logging.getLogger("users-service")


class UserContext:
  def __init__(self, user_id: int, email: str | None, role: str):
    self.id = user_id
    self.email = email
    self.role = role


async def get_current_user(
  x_user_id: str = Header(..., alias="X-User-Id"),
  x_user_email: str | None = Header(None, alias="X-User-Email"),
  x_user_role: str = Header(..., alias="X-User-Role"),
) -> UserContext:
  logger.debug(
    "Resolving current user from headers",
    extra={
      "x_user_id": x_user_id,
      "x_user_email": x_user_email,
      "x_user_role": x_user_role,
    },
  )

  try:
    user_id = int(x_user_id)
  except ValueError:
    logger.warning(
      "Invalid X-User-Id header",
      extra={"x_user_id": x_user_id},
    )
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Invalid user id header",
    )

  user = UserContext(user_id=user_id, email=x_user_email, role=x_user_role)

  logger.info(
    "Current user resolved from headers",
    extra={"user_id": user.id, "email": user.email, "role": user.role},
  )

  return user


def require_role(required_role: str):
  async def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
    if user.role != required_role:
      logger.warning(
        "Access denied: insufficient role",
        extra={
          "required_role": required_role,
          "user_role": user.role,
          "user_id": user.id,
        },
      )
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
      )

    logger.debug(
      "Access granted based on role",
      extra={"required_role": required_role, "user_role": user.role},
    )
    return user

  return dependency