from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  app_name: str = "Leave Service"
  env: str = "development"

  database_url: str = "sqlite+aiosqlite:///./leave.db"

  rabbitmq_host: str = "rabbitmq"
  rabbitmq_port: int = 5672
  rabbitmq_user: str = "guest"
  rabbitmq_password: str = "guest"

  consul_host: str = "consul"
  consul_port: int = 8500

  service_name: str = "leave-service"
  service_port: int = 8002

  class Config:
    env_file = ".env"


settings = Settings()