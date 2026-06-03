import json
import logging
import logging.config
import threading
import os
from typing import Optional

from pythonjsonlogger import jsonlogger

DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


# Thread-local storage for correlation / logger ID
_thread_local = threading.local()


# --------- Public API for setting/getting logger id ----------

def set_logger_id(logger_id: Optional[str]) -> None:
  """
  Set per-request/per-task logger_id (e.g. correlation/trace id).
  Call this in FastAPI middleware when you extract it from headers.
  """
  _thread_local.logger_id = logger_id


def get_logger_id() -> Optional[str]:
  """
  Get current logger_id from thread-local storage.
  Use this inside any logging formatter or business code if needed.
  """
  return getattr(_thread_local, "logger_id", None)


# --------- Custom JSON Formatter ----------

class ServiceJsonFormatter(jsonlogger.JsonFormatter):
  """
  JSON formatter for microservices logs.
  Adds logger_id and useful context fields.
  """

  def format(self, record: logging.LogRecord) -> str:
    log_message = {
      "message": record.getMessage(),
      "severity": record.levelname,
      "logger": record.name,
      "module": record.module,
      "module_info": {
        "pathname": record.pathname,
        "line_no": record.lineno,
        "file_name": record.filename,
      },
      "timestamp": {
        "seconds": int(record.created),
        "nanos": 0,
      },
    }

    # Add correlation / logger id if present
    logger_id = get_logger_id()
    if logger_id:
      log_message["logger_id"] = logger_id

    # If extra fields are used via logger = logging.getLogger(__name__)
    # and logger.info("msg", extra={"service": "users-service"}), they
    # will appear in record.__dict__; you can merge selectively.
    if hasattr(record, "service"):
      log_message["service"] = getattr(record, "service")

    return json.dumps(log_message)


def _base_logging_config(service_name: str) -> dict:
  """
  Build a dictConfig for the given microservice.
  Logs JSON to stdout.
  """
  return {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
      "json": {
        "()": ServiceJsonFormatter,
        "format": "%(asctime)s %(process)s %(levelname)s %(name)s %(message)s",
      }
    },
    "handlers": {
      "default": {
        "level": DEFAULT_LOG_LEVEL,
        "formatter": "json",
        "class": "logging.StreamHandler",
        "stream": "ext://sys.stdout",
      },
    },
    "loggers": {
      # Root logger for this service
      service_name: {
        "handlers": ["default"],
        "level": DEFAULT_LOG_LEVEL,
        "propagate": False,
      },
      # Uvicorn loggers (optional) – route through same handler
      "uvicorn": {
        "handlers": ["default"],
        "level": DEFAULT_LOG_LEVEL,
        "propagate": False,
      },
      "uvicorn.error": {
        "handlers": ["default"],
        "level": DEFAULT_LOG_LEVEL,
        "propagate": False,
      },
      "uvicorn.access": {
        "handlers": ["default"],
        "level": DEFAULT_LOG_LEVEL,
        "propagate": False,
      },
    },
    "root": {
      "handlers": ["default"],
      "level": DEFAULT_LOG_LEVEL,
    },
  }


def configure_logging(service_name: str) -> logging.Logger:
  """
  Configure logging for a given service and return a service-level logger.
  Call this once at startup (e.g. in FastAPI startup or main entrypoint).
  """
  config = _base_logging_config(service_name)
  logging.config.dictConfig(config)
  logger = logging.getLogger(service_name)
  logger.info("Logging configured for service '%s'", service_name,
              extra={"service": service_name})
  return logger