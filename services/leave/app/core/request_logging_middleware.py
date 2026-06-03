import uuid
from typing import Callable, Awaitable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import set_logger_id


class LoggerIdMiddleware(BaseHTTPMiddleware):
  """
  Middleware that extracts/creates a logger_id (correlation id) per request
  and stores it in thread-local storage for logging.
  """

  def __init__(self, app, header_name: str = "X-Logger-Id"):
    super().__init__(app)
    self.header_name = header_name

  async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable]):
    # Extract logger_id from incoming header, or generate one.
    incoming_id = request.headers.get(self.header_name)
    logger_id = incoming_id or str(uuid.uuid4())

    # Store in thread-local so formatter can attach it to logs
    set_logger_id(logger_id)

    # You may also want to set it on request.state if needed:
    request.state.logger_id = logger_id

    # Call downstream
    response = await call_next(request)

    # Echo header back in the response for clients / other services
    response.headers[self.header_name] = logger_id

    return response