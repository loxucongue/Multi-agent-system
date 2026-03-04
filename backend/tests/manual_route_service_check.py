"""Manual smoke test for RouteService with session factory."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.database import async_session_factory, engine
from app.config.redis import redis_client
from app.services.route_service import RouteService


async def main() -> None:
    try:
        service = RouteService(async_session_factory, redis_client)
        result = await service.get_route_detail(1)
        if result is None:
            print("route_detail: None")
            return
        print("route_detail:", result.model_dump())
    finally:
        await redis_client.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
