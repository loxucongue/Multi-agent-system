"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings from .env and process environment."""

    DATABASE_URL: str = "mysql+aiomysql://root:root@127.0.0.1:3306/travel_db"
    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"

    COZE_OAUTH_APP_ID: str = ""
    COZE_KID: str = ""
    COZE_PRIVATE_KEY_PATH: str = ""
    COZE_WF_ROUTE_SEARCH_ID: str = ""
    COZE_WF_VISA_SEARCH_ID: str = ""
    COZE_WF_EXTERNAL_INFO_ID: str = ""
    COZE_SPACE_ID: str = ""
    COZE_ROUTE_DATASET_ID: str = ""
    COZE_VISA_DATASET_ID: str = ""

    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD_HASH: str = ""
    JWT_SECRET_KEY: str = ""
    SESSION_CONTEXT_TURNS: int = 6

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
