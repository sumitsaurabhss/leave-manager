from fastapi import Depends, Header, HTTPException, status


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
  try:
    user_id = int(x_user_id)
  except ValueError:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Invalid user id header",
    )

  return UserContext(user_id=user_id, email=x_user_email, role=x_user_role)


def require_role(required_role: str):
  async def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
    if user.role != required_role:
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
      )
    return user

  return dependency