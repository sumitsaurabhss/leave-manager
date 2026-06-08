import asyncio
import json
import logging
from typing import Any, Dict

import aio_pika
from aio_pika import IncomingMessage, ExchangeType

from app.core.config import settings

logger = logging.getLogger("notification-service.leave-consumer")


async def handle_leave_applied(data: Dict[str, Any]):
  emp_id = data.get("employee_id")
  mgr_id = data.get("manager_id")
  lr_id = data.get("leave_request_id")
  leave_type = data.get("leave_type")
  start = data.get("start_date")
  end = data.get("end_date")
  days = data.get("days")

  logger.info(
    "Leave applied notification",
    extra={
      "event": "leave_applied",
      "employee_id": emp_id,
      "manager_id": mgr_id,
      "leave_request_id": lr_id,
      "leave_type": leave_type,
      "days": days,
      "start_date": start,
      "end_date": end,
    },
  )


async def handle_leave_approved(data: Dict[str, Any]):
  emp_id = data.get("employee_id")
  mgr_id = data.get("manager_id")
  lr_id = data.get("leave_request_id")

  logger.info(
    "Leave approved notification",
    extra={
      "event": "leave_approved",
      "employee_id": emp_id,
      "manager_id": mgr_id,
      "leave_request_id": lr_id,
    },
  )


async def handle_leave_rejected(data: Dict[str, Any]):
  emp_id = data.get("employee_id")
  mgr_id = data.get("manager_id")
  lr_id = data.get("leave_request_id")
  reason = data.get("reason")

  logger.info(
    "Leave rejected notification",
    extra={
      "event": "leave_rejected",
      "employee_id": emp_id,
      "manager_id": mgr_id,
      "leave_request_id": lr_id,
      "reason": reason,
    },
  )


async def handle_event(message: IncomingMessage):
  async with message.process():
    try:
      payload = json.loads(message.body)
    except json.JSONDecodeError:
      logger.error(
        "Failed to decode notification message",
        extra={"raw_body": message.body.decode("utf-8", errors="replace")},
      )
      return

    event_type = payload.get("event_type")
    data = payload.get("data", {}) or {}

    logger.debug(
      "Received notification event",
      extra={"event_type": event_type},
    )

    try:
      if event_type == "leave_applied":
        await handle_leave_applied(data)
      elif event_type == "leave_approved":
        await handle_leave_approved(data)
      elif event_type == "leave_rejected":
        await handle_leave_rejected(data)
      else:
        logger.warning(
          "Unknown notification event type",
          extra={"event_type": event_type},
        )
    except Exception as exc:
      logger.exception(
        "Error processing notification event",
        extra={"event_type": event_type, "error": str(exc)},
      )


async def start_leave_notifications_consumer():
  while True:
    try:
      logger.info(
        "Connecting to RabbitMQ",
        extra={
          "host": settings.rabbitmq_host,
          "port": settings.rabbitmq_port,
        },
      )
      connection = await aio_pika.connect_robust(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_user,
        password=settings.rabbitmq_password,
      )

      channel = await connection.channel()
      await channel.set_qos(prefetch_count=10)

      exchange = await channel.declare_exchange(
        "notifications",
        ExchangeType.TOPIC,
        durable=True,
      )

      queue = await channel.declare_queue(
        "notification-service.leave-events",
        durable=True,
      )

      await queue.bind(exchange, routing_key="notifications.leave.*")
      await queue.consume(handle_event)

      logger.info(
        "Notification service started, listening for leave events",
        extra={"queue": queue.name},
      )

      # keep consumer alive until connection is lost
      while True:
        await asyncio.sleep(5)

    except Exception as exc:
      logger.exception(
        "Error in RabbitMQ consumer loop",
        extra={"error": str(exc)},
      )
      logger.info("Retrying RabbitMQ connection in 5 seconds...")
      await asyncio.sleep(5)