from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  app_name: str = "Users Service"
  env: str = "development"

  database_url: str = "sqlite+aiosqlite:///./users.db"

  jwt_secret_key: str
  jwt_algorithm: str = "HS256"
  access_token_expire_minutes: int = 30

  rabbitmq_host: str = "rabbitmq"
  rabbitmq_port: int = 5672
  rabbitmq_user: str = "guest"
  rabbitmq_password: str = "guest"

  consul_host: str = "consul"
  consul_port: int = 8500

  service_name: str = "users-service"
  service_port: int = 8001

  class Config:
    env_file = ".env"


settings = Settings()