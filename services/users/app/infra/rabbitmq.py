import json
import logging

import pika

from app.core.config import settings

logger = logging.getLogger("users-service.rabbitmq")


def get_rabbitmq_connection() -> pika.BlockingConnection:
  credentials = pika.PlainCredentials(
    settings.rabbitmq_user,
    settings.rabbitmq_password,
  )
  params = pika.ConnectionParameters(
    host=settings.rabbitmq_host,
    port=settings.rabbitmq_port,
    credentials=credentials,
  )
  return pika.BlockingConnection(params)


def publish_event(
  message: dict,
  routing_key: str = "employee.created",
  exchange: str = "user.events",
) -> None:
  """
  Publish user events (e.g. employee_created) so leave-service can consume them.
  """
  logger.info(
    "Publishing RabbitMQ user event",
    extra={
      "exchange": exchange,
      "routing_key": routing_key,
      "event_type": message.get("event_type"),
    },
  )

  conn = get_rabbitmq_connection()
  try:
    channel = conn.channel()

    channel.exchange_declare(
      exchange=exchange,
      exchange_type="topic",
      durable=True,
    )

    channel.basic_publish(
      exchange=exchange,
      routing_key=routing_key,
      body=json.dumps(message).encode("utf-8"),
      properties=pika.BasicProperties(
        content_type="application/json",
        delivery_mode=2,  # persistent
      ),
    )
  finally:
    conn.close()

  logger.info(
    "RabbitMQ user event published",
    extra={"exchange": exchange, "routing_key": routing_key},
  )