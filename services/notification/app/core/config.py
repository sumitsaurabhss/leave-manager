from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  app_name: str = "Notification Service"

  rabbitmq_host: str = "rabbitmq"
  rabbitmq_port: int = 5672
  rabbitmq_user: str = "guest"
  rabbitmq_password: str = "guest"

  # log level: DEBUG/INFO/WARN/ERROR
  log_level: str = "INFO"

  class Config:
    env_file = ".env"


settings = Settings()