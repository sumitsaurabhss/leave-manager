# app/infra/employee_events_consumer.py
import asyncio
import json
import logging
from typing import Any, Dict

import aio_pika
from aio_pika import IncomingMessage, ExchangeType

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.services.employee_service import create_employee_with_balances

logger = logging.getLogger("leave-service")


async def process_employee_created(payload: Dict[str, Any]) -> None:
  data = payload.get("data", {}) or {}
  user_id = data.get("user_id")
  full_name = data.get("full_name")
  email = data.get("email")
  # manager_id = data.get("manager_id")

  if user_id is None or full_name is None or email is None:
    logger.warning("Received invalid employee_created event: %s", payload)
    return

  logger.info(
    "Processing employee_created event for user_id=%s, email=%s",
    user_id,
    email,
  )

  async with AsyncSessionLocal() as db:
    await create_employee_with_balances(
      db=db,
      external_user_id=user_id,
      full_name=full_name,
      email=email,
      # manager_external_id=manager_id,
    )


async def handle_message(message: IncomingMessage) -> None:
  async with message.process():
    try:
      payload = json.loads(message.body)
    except json.JSONDecodeError:
      logger.error("Failed to decode employee event message: %s", message.body)
      return

    event_type = payload.get("event_type")
    if event_type == "employee_created":
      await process_employee_created(payload)
    else:
      logger.info("Ignoring unknown event_type=%s", event_type)


async def start_employee_events_consumer() -> None:
  """
  Connects to RabbitMQ, declares exchange/queue, and consumes employee events.
  Keeps retrying on failure.
  """
  while True:
    try:
      logger.info(
        "Connecting to RabbitMQ at %s:%s for employee events...",
        settings.rabbitmq_host,
        settings.rabbitmq_port,
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
        "hr.events",
        ExchangeType.TOPIC,
        durable=True,
      )

      queue = await channel.declare_queue(
        "leave-service.employee-events",
        durable=True,
      )

      await queue.bind(exchange, routing_key="employee.created")

      logger.info("Leave-service subscribed to employee.created events")

      await queue.consume(handle_message)

      # Keep running until connection is closed or error occurs
      while True:
        await asyncio.sleep(1)

    except Exception as exc:
      logger.error(
        "Employee events consumer error: %s. Reconnecting in 5s...", exc
      )
      await asyncio.sleep(5)