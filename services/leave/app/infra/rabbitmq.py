# app/infra/rabbitmq.py (leave-service; notification publisher)
import json
import logging

import pika

from app.core.config import settings

logger = logging.getLogger("leave-service.rabbitmq")


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


def publish_notification(
  message: dict,
  routing_key: str = "notifications.leave",
) -> None:
  """
  Publish a notification event for leave actions.
  """
  logger.info(
    "Publishing leave notification",
    extra={
      "exchange": "notifications",
      "routing_key": routing_key,
      "event_type": message.get("event_type"),
    },
  )

  conn = get_rabbitmq_connection()
  try:
    channel = conn.channel()

    channel.exchange_declare(
      exchange="notifications",
      exchange_type="topic",
      durable=True,
    )

    channel.basic_publish(
      exchange="notifications",
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
    "Leave notification published",
    extra={"exchange": "notifications", "routing_key": routing_key},
  )