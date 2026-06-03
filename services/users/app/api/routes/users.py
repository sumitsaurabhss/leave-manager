# app/api/routes/users.py
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.deps import get_current_user, require_role
from app.database.session import get_db
from app.database import models
from app.schemas.user import UserOut

router = APIRouter(tags=["users"])
logger = logging.getLogger("users-service")


@router.get("/me", response_model=UserOut)
async def read_me(
        current_user: models.User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
  result = await db.execute(
    select(models.User).where(models.User.id == current_user.id)
  )
  user = result.scalar_one_or_none()

  if user is None:
    logger.warning(
      "Current user not found in DB",
      extra={"user_id": current_user.id, "email": current_user.email},
    )
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail="User not found",
    )

  logger.info(
    "API: /users/me",
    extra={
      "user_id": user.id,
      "email": user.email,
      "full_name": user.full_name,
    },
  )
  return user


@router.get("/", response_model=List[UserOut])
async def list_users(
  db: AsyncSession = Depends(get_db),
  _: models.User = Depends(require_role("manager")),
):
  logger.info("API: list_users called by manager")
  result = await db.execute(select(models.User))
  users = result.scalars().all()
  logger.info(
    "API: list_users success",
    extra={"count": len(users)},
  )
  return users