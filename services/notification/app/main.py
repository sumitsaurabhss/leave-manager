# app/main.py
import asyncio
import logging

from app.core.config import settings
from app.core.logging import configure_logging
from app.consumers.leave_consumer import start_leave_notifications_consumer

from app.core.tracing import init_tracing


async def main():
  configure_logging(service_name="notification-service")
  logger = logging.getLogger("notification-service")
  logger.info("Starting Notification Service...")
  init_tracing(service_name=settings.app_name or "notification-service")
  await start_leave_notifications_consumer()


if __name__ == "__main__":
  asyncio.run(main())