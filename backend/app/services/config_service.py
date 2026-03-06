"""System configuration service with optional Redis cache."""

from __future__ import annotations

from typing import Any

from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.database import SystemConfig
from app.utils.logger import get_logger

_CACHE_TTL_SECONDS = 60
_CACHE_PREFIX = "system_config:"


class ConfigService:
    """Read/write runtime configs from DB with short-lived Redis cache."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: aioredis.Redis | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._logger = get_logger(__name__)

    async def get_int(self, key: str, default: int) -> int:
        """Get integer config value by key, falling back to default on failures."""

        raw_value = await self._get_value(key)
        if raw_value is None:
            return default

        try:
            return int(str(raw_value).strip())
        except (TypeError, ValueError):
            self._logger.warning("invalid int config value key=%s value=%r", key, raw_value)
            return default

    async def set_value(self, key: str, value: str, description: str | None = None) -> None:
        """Create or update config value and evict related cache entries."""

        async with self._session_factory() as session:
            row = await session.get(SystemConfig, key)
            if row is None:
                row = SystemConfig(key=key, value=value, description=description)
                session.add(row)
            else:
                row.value = value
                row.description = description

            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        await self._delete_cache(key)
        if key.upper() != key:
            await self._delete_cache(key.upper())

    async def delete_key(self, key: str) -> bool:
        """Delete config by key. Returns False when key does not exist."""

        async with self._session_factory() as session:
            row = await session.get(SystemConfig, key)
            if row is None:
                return False

            await session.delete(row)
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        await self._delete_cache(key)
        if key.upper() != key:
            await self._delete_cache(key.upper())
        return True

    async def ensure_defaults(self, defaults: dict[str, tuple[str, str | None]]) -> None:
        """Insert default config entries if they do not exist."""

        async with self._session_factory() as session:
            changed = False
            for key, (value, description) in defaults.items():
                row = await session.get(SystemConfig, key)
                if row is not None:
                    continue
                session.add(SystemConfig(key=key, value=value, description=description))
                changed = True

            if not changed:
                return

            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _get_value(self, key: str) -> str | None:
        cached = await self._get_cache(key)
        if cached is not None:
            return cached

        db_value = await self._get_value_from_db(key)
        if db_value is None and key.upper() != key:
            db_value = await self._get_value_from_db(key.upper())
        if db_value is None:
            return None

        await self._set_cache(key, db_value)
        return db_value

    async def _get_value_from_db(self, key: str) -> str | None:
        async with self._session_factory() as session:
            stmt = select(SystemConfig.value).where(SystemConfig.key == key)
            result = await session.execute(stmt)
            value = result.scalar_one_or_none()
            if value is None:
                return None
            return str(value)

    def _cache_key(self, key: str) -> str:
        return f"{_CACHE_PREFIX}{key}"

    async def _get_cache(self, key: str) -> str | None:
        if self._redis is None:
            return None
        try:
            value = await self._redis.get(self._cache_key(key))
            if value is None:
                return None
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return str(value)
        except Exception:
            self._logger.debug("redis get config failed key=%s", key)
            return None

    async def _set_cache(self, key: str, value: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(self._cache_key(key), value, ex=_CACHE_TTL_SECONDS)
        except Exception:
            self._logger.debug("redis set config failed key=%s", key)

    async def _delete_cache(self, key: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(self._cache_key(key))
        except Exception:
            self._logger.debug("redis delete config failed key=%s", key)
