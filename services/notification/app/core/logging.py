# app/core/logging.py
import json
import logging
import sys
from typing import Any, Dict

from app.core.config import settings


class JsonFormatter(logging.Formatter):
  def format(self, record: logging.LogRecord) -> str:
    log: Dict[str, Any] = {
      "timestamp": self.formatTime(record, self.datefmt),
      "level": record.levelname,
      "logger": record.name,
      "message": record.getMessage(),
      "service": getattr(record, "service", None),
    }

    # include extra fields
    for key, value in record.__dict__.items():
      if key in (
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
      ):
        continue
      if key not in log:
        log[key] = value

    return json.dumps(log)


def configure_logging(service_name: str = "notification-service") -> None:
  root = logging.getLogger()
  root.setLevel(settings.log_level)

  handler = logging.StreamHandler(sys.stdout)

  # Use JSON formatter for structured logs
  formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
  handler.setFormatter(formatter)

  # clear existing handlers if rerun (e.g. in tests)
  root.handlers.clear()
  root.addHandler(handler)

  # Attach service name via LoggerAdapter if you want, but a simple filter works too.
  class ServiceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
      # inject "service" into every record
      if not hasattr(record, "service"):
        record.service = service_name
      return True

  root.addFilter(ServiceFilter())