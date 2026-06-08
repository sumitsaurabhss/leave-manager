import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import models

logger = logging.getLogger("leave-service")


async def seed_leave_types(db: AsyncSession) -> None:
  logger.info("Checking if leave types are already seeded")

  existing = await db.execute(select(models.LeaveType))
  if existing.scalars().first():
    logger.info("Leave types already present; skipping seed")
    return

  types = [
    models.LeaveType(code="CASUAL", name="Casual Leave", annual_allocation=12),
    models.LeaveType(code="SICK", name="Sick Leave", annual_allocation=10),
    models.LeaveType(
      code="PRIVILEGE",
      name="Privilege Leave",
      annual_allocation=15,
    ),
  ]
  db.add_all(types)
  await db.commit()

  logger.info(
    "Leave types seeded",
    extra={"codes": [t.code for t in types]},
  )