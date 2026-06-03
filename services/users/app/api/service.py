# app/api/service.py
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import models
from app.schemas.user import UserCreate

logger = logging.getLogger("users-service")


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[models.User]:
  logger.debug("Fetching user by email", extra={"email": email})
  result = await db.execute(select(models.User).where(models.User.email == email))
  user = result.scalar_one_or_none()
  if user:
    logger.debug("User found by email", extra={"user_id": user.id, "email": email})
  else:
    logger.debug("No user found by email", extra={"email": email})
  return user


async def create_user(
  db: AsyncSession,
  user_in: UserCreate,
  hashed_password: str,
) -> models.User:
  logger.info(
    "Creating user in DB",
    extra={"email": user_in.email, "role": user_in.role.value},
  )
  db_user = models.User(
    email=user_in.email,
    full_name=user_in.full_name,
    hashed_password=hashed_password,
    role=user_in.role,
  )
  db.add(db_user)
  await db.commit()
  await db.refresh(db_user)

  logger.info(
    "User created in DB",
    extra={"user_id": db_user.id, "email": db_user.email},
  )

  return db_user