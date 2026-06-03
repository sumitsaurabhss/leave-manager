from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  app_name: str = "Leave Service"
  env: str = "development"

  database_url: str = "sqlite+aiosqlite:///./leave.db"

  rabbitmq_host: str = "rabbitmq"
  rabbitmq_port: int = 5672
  rabbitmq_user: str = "guest"
  rabbitmq_password: str = "guest"

  class Config:
    env_file = ".env"


settings = Settings()