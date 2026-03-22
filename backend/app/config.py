from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://momentum:momentum@localhost:5432/momentum"
    database_url_sync: str = "postgresql://momentum:momentum@localhost:5432/momentum"
    fcm_credentials_path: str = ""
    cors_origins: list[str] = ["*"]
    scheduler_enabled: bool = True

    model_config = {"env_prefix": "APP_"}


settings = Settings()
