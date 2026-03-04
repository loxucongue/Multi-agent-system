"""Redis-based rate limiting and session lock helpers."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from redis import asyncio as aioredis

from app.config.redis import get_redis
from app.utils.logger import get_logger

_SESSION_LOCK_PREFIX = "lock:session:"
_COZE_MINUTE_KEY = "ratelimit:coze:minute"
_COZE_WINDOW_SECONDS = 60
_COZE_THRESHOLD_PER_MINUTE = 800


class RateLimiter:
    """Distributed lock and rate limiter service backed by Redis."""

    def __init__(self, redis: aioredis.Redis | None = None) -> None:
        self._redis = redis
        self._logger = get_logger(__name__)

    async def acquire_session_lock(self, session_id: str, ttl: int = 90) -> bool:
        """Acquire lock for a session via SET NX EX. Redis failures pass through."""

        if self._redis is None:
            return True

        key = self._session_lock_key(session_id)
        try:
            acquired = await self._redis.set(key, "1", nx=True, ex=ttl)
            return bool(acquired)
        except Exception:
            self._logger.warning(f"redis unavailable, skip session lock acquire session_id={session_id}")
            return True

    async def release_session_lock(self, session_id: str) -> None:
        """Release lock key. Redis failures are ignored."""

        if self._redis is None:
            return

        key = self._session_lock_key(session_id)
        try:
            await self._redis.delete(key)
        except Exception:
            self._logger.warning(f"redis unavailable, skip session lock release session_id={session_id}")

    async def check_coze_rate_limit(self) -> bool:
        """Sliding-window rate limiting for Coze calls. Redis failures pass through."""

        if self._redis is None:
            return True

        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - (_COZE_WINDOW_SECONDS * 1000)
        member = f"{now_ms}-{uuid.uuid4().hex}"

        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.zremrangebyscore(_COZE_MINUTE_KEY, 0, window_start_ms)
            pipe.zadd(_COZE_MINUTE_KEY, {member: now_ms})
            pipe.zcard(_COZE_MINUTE_KEY)
            pipe.expire(_COZE_MINUTE_KEY, _COZE_WINDOW_SECONDS)
            _, _, current_count, _ = await pipe.execute()
            return int(current_count) <= _COZE_THRESHOLD_PER_MINUTE
        except Exception:
            self._logger.warning("redis unavailable, skip coze rate limit check")
            return True

    def _session_lock_key(self, session_id: str) -> str:
        return f"{_SESSION_LOCK_PREFIX}{session_id}"


def get_rate_limiter(redis: aioredis.Redis = Depends(get_redis)) -> RateLimiter:
    """FastAPI dependency provider for RateLimiter."""

    return RateLimiter(redis=redis)


async def require_session_lock(
    session_id: str,
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> AsyncGenerator[None, None]:
    """Dependency: acquire session lock at start and release at request end."""

    acquired = await limiter.acquire_session_lock(session_id=session_id)
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="session is locked, please retry later",
        )
    try:
        yield
    finally:
        await limiter.release_session_lock(session_id=session_id)
