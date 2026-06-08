import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import models
from app.core.security import get_password_hash
from app.infra.rabbitmq import publish_event

logger = logging.getLogger("users-service")


async def seed_initial_users(db: AsyncSession):
  logger.info("Checking if initial users are already present")
  result = await db.execute(select(models.User))
  if result.scalars().first():
    logger.info("Users table already has data; skipping initial seed")
    return

  users = [
    models.User(
      email="initial.manager@example.com",
      full_name="Initial Manager",
      hashed_password=get_password_hash("manager"),
      role=models.Role.manager,
    ),
    models.User(
      full_name="User Manager",
      email="user.manager@example.com",
      hashed_password=get_password_hash("manager"),
      role=models.Role.manager,
    ),
    models.User(
      full_name="User Employee",
      email="user.employee@example.com",
      hashed_password=get_password_hash("employee"),
      role=models.Role.employee,
    ),
  ]
  db.add_all(users)
  await db.commit()

  for user in users:
    await db.refresh(user)

  logger.info(
    "Seeded initial users",
    extra={"seeded_emails": [u.email for u in users]},
  )

  # Try to publish employee_created events, but don't crash on failure
  for user in users:
    event = {
      "event_type": "employee_created",
      "data": {
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
      },
    }

    try:
      logger.info(
        "Publishing employee_created event for seeded user",
        extra={"user_id": user.id, "email": user.email},
      )
      publish_event(event)  # uses hr.events / employee.created
    except Exception as exc:
      logger.error(
        "Failed to publish employee_created event for seeded user",
        extra={
          "user_id": user.id,
          "email": user.email,
          "error": str(exc),
        },
      )