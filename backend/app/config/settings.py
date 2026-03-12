"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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
    COZE_WF_ROUTE_PARSE_ID: str = ""
    COZE_PARSE_CONCURRENCY: int = 10
    COZE_SPACE_ID: str = ""
    COZE_ROUTE_DATASET_ID: str = ""
    COZE_VISA_DATASET_ID: str = ""

    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD_HASH: str = ""
    JWT_SECRET_KEY: str = ""
    SESSION_CONTEXT_TURNS: int = 6
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    CORS_ORIGIN_REGEX: str = (
        r"^https?://("
        r"localhost|127\.0\.0\.1|0\.0\.0\.0|"
        r"10\.\d+\.\d+\.\d+|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|"
        r"192\.168\.\d+\.\d+"
        r")(:\d+)?$"
    )

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
