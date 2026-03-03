"""Redis async client configuration and dependency helpers."""

from collections.abc import AsyncGenerator

from redis import asyncio as redis

from app.config.settings import settings


redis_client = redis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    max_connections=20,
)


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """Yield a shared Redis async client for FastAPI dependencies."""

    yield redis_client


async def redis_health_check() -> bool:
    """Check Redis connectivity by sending a ping command."""

    try:
        result = await redis_client.ping()
        return bool(result)
    except Exception:
        return False
