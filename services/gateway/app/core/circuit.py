import pybreaker

from app.core.config import settings

users_cb = pybreaker.CircuitBreaker(
  fail_max=settings.cb_failure_threshold,
  reset_timeout=settings.cb_recovery_timeout,
  name="users_service_cb",
)

leave_cb = pybreaker.CircuitBreaker(
  fail_max=settings.cb_failure_threshold,
  reset_timeout=settings.cb_recovery_timeout,
  name="leave_service_cb",
)