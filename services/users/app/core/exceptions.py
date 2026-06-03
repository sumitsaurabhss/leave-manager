# app/core/exceptions.py
class APIError(Exception):
  def __init__(self, status_code: int, detail: str, code: str | None = None):
    self.status_code = status_code
    self.detail = detail
    self.code = code