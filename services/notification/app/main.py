# app/main.py
import asyncio
import logging

from app.core.logging import configure_logging
from app.consumers.leave_consumer import start_leave_notifications_consumer


async def main():
  configure_logging(service_name="notification-service")
  logger = logging.getLogger("notification-service")
  logger.info("Starting Notification Service...")
  await start_leave_notifications_consumer()


if __name__ == "__main__":
  asyncio.run(main())