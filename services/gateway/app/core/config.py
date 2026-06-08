from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  app_name: str = "gateway"

  jwt_secret_key: str
  jwt_algorithm: str = "HS256"

  # Consul config
  consul_host: str = "consul"
  consul_port: int = 8500

  # Optional fallback URLs via env (Docker DNS names)if Consul not available)
  users_service_url_fallback: str | None = None  # e.g. http://users-service:8001
  leave_service_url_fallback: str | None = None  # e.g. http://leave-service:8002

  # Circuit breaker config
  cb_failure_threshold: int = 5
  cb_recovery_timeout: int = 30  # seconds

  class Config:
    env_file = ".env"


settings = Settings()