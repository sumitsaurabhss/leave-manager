from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  app_name: str = "API Gateway"

  # JWT config – must match signing key used by users-service
  jwt_secret_key: str
  jwt_algorithm: str = "HS256"

  # Static service discovery via env (Docker DNS names)
  users_service_url: str  # e.g. http://users-service:8001
  leave_service_url: str  # e.g. http://leave-service:8002

  # Circuit breaker config
  cb_failure_threshold: int = 5
  cb_recovery_timeout: int = 30  # seconds

  class Config:
    env_file = ".env"


settings = Settings()