"""Manual smoke test for RateLimiter lock behavior."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.redis import redis_client
from app.services.rate_limiter import RateLimiter


async def main() -> None:
    limiter = RateLimiter(redis_client)
    session_id = "manual-rate-limit-session"

    first = await limiter.acquire_session_lock(session_id)
    second = await limiter.acquire_session_lock(session_id)
    await limiter.release_session_lock(session_id)
    third = await limiter.acquire_session_lock(session_id)
    await limiter.release_session_lock(session_id)

    print({"first": first, "second": second, "third": third})

    assert first is True
    assert second is False
    assert third is True
    print("manual rate limiter lock check passed")

    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
