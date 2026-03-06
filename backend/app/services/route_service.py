"""Route data query service with Redis caching for price/schedule lookups."""

from __future__ import annotations

from redis import asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models.database import Route, RoutePricing, RouteSchedule
from app.models.schemas import (
    PricingInfo,
    RouteBatchItem,
    RouteCard,
    RouteDetail,
    RoutePriceSchedule,
    ScheduleInfo,
)
from app.utils.logger import get_logger

_CACHE_TTL = 300  # seconds


class RouteService:
    """路线数据查询服务。

    使用 async SQLAlchemy session 查询路线表，价格/排期查询支持
    Redis 短缓存（TTL=300s），Redis 不可用时自动 fallback 到 DB。
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: aioredis.Redis | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._logger = get_logger(__name__)

    # ─────────────────────────────────────────────
    #  Public methods
    # ─────────────────────────────────────────────

    async def get_route_detail(self, route_id: int) -> RouteDetail | None:
        """查询单条路线全部字段。查不到返回 None。"""

        async with self._session_factory() as session:
            stmt = select(Route).where(Route.id == route_id)
            result = await session.execute(stmt)
            route = result.scalar_one_or_none()

        if route is None:
            return None

        return RouteDetail.model_validate(route)

    async def get_route_price_schedule(self, route_id: int) -> RoutePriceSchedule | None:
        """查询路线价格+排期。优先从 Redis 缓存读取，miss 时查 DB 并回填缓存。"""

        # ── 尝试 Redis 缓存 ──
        cached = await self._get_cache(route_id)
        if cached is not None:
            return cached

        async with self._session_factory() as session:
            # ── DB 查询 ──
            pricing_stmt = select(RoutePricing).where(RoutePricing.route_id == route_id)
            schedule_stmt = select(RouteSchedule).where(RouteSchedule.route_id == route_id)

            pricing_result = await session.execute(pricing_stmt)
            schedule_result = await session.execute(schedule_stmt)

            pricing_row = pricing_result.scalar_one_or_none()
            schedule_row = schedule_result.scalar_one_or_none()

        if pricing_row is None and schedule_row is None:
            return None

        pricing_info = PricingInfo.model_validate(pricing_row) if pricing_row else None
        schedule_info = ScheduleInfo.model_validate(schedule_row) if schedule_row else None

        result = RoutePriceSchedule(
            route_id=route_id,
            pricing=pricing_info,
            schedule=schedule_info,
        )

        # ── 回填缓存 ──
        await self._set_cache(route_id, result)

        return result

    async def get_routes_batch(self, route_ids: list[int]) -> list[RouteBatchItem]:
        """批量查询路线（静态信息+pricing+schedule），一次 JOIN 查出。"""

        if not route_ids:
            return []

        stmt = (
            select(Route)
            .where(Route.id.in_(route_ids))
            .options(selectinload(Route.pricing), selectinload(Route.schedule))
        )
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            routes = result.scalars().all()

        items: list[RouteBatchItem] = []
        for route in routes:
            pricing_info = PricingInfo.model_validate(route.pricing) if route.pricing else None
            schedule_info = ScheduleInfo.model_validate(route.schedule) if route.schedule else None

            items.append(
                RouteBatchItem(
                    id=route.id,
                    name=route.name,
                    supplier=route.supplier,
                    tags=route.tags,
                    summary=route.summary,
                    highlights=route.highlights,
                    base_info=route.base_info,
                    itinerary_json=route.itinerary_json,
                    notice=route.notice,
                    included=route.included,
                    doc_url=route.doc_url,
                    is_hot=route.is_hot,
                    sort_weight=route.sort_weight,
                    created_at=route.created_at,
                    updated_at=route.updated_at,
                    pricing=pricing_info,
                    schedule=schedule_info,
                )
            )

        return items

    async def get_hot_routes(self, limit: int = 5) -> list[RouteCard]:
        """查询热门路线，按 sort_weight 降序排列。"""

        stmt = (
            select(Route)
            .where(Route.is_hot == True)  # noqa: E712
            .options(selectinload(Route.pricing))
            .order_by(Route.sort_weight.desc())
            .limit(limit)
        )
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            routes = result.scalars().all()

        cards: list[RouteCard] = []
        for route in routes:
            price_min = route.pricing.price_min if route.pricing else None
            price_max = route.pricing.price_max if route.pricing else None

            cards.append(
                RouteCard(
                    id=route.id,
                    name=route.name,
                    tags=route.tags,
                    summary=route.summary,
                    doc_url=route.doc_url,
                    sort_weight=route.sort_weight,
                    price_min=price_min,
                    price_max=price_max,
                )
            )

        return cards

    async def resolve_route_ids_by_doc_urls(self, doc_urls: list[str]) -> dict[str, int]:
        """Resolve route ids by doc_url list.

        Matching is normalized with trim + lower to tolerate trailing spaces
        and case differences in stored/received urls.
        Returned mapping keeps the original input url string as key.
        """

        if not doc_urls:
            return {}

        normalized_to_originals: dict[str, list[str]] = {}
        for raw in doc_urls:
            if not isinstance(raw, str):
                continue
            normalized = raw.strip().lower()
            if not normalized:
                continue
            normalized_to_originals.setdefault(normalized, []).append(raw)

        if not normalized_to_originals:
            return {}

        normalized_values = list(normalized_to_originals.keys())
        normalized_doc_url = func.lower(func.trim(Route.doc_url))

        async with self._session_factory() as session:
            stmt = (
                select(Route.id, Route.doc_url, normalized_doc_url.label("normalized_doc_url"))
                .where(normalized_doc_url.in_(normalized_values))
            )
            result = await session.execute(stmt)
            rows = result.all()

        normalized_to_route_id: dict[str, int] = {}
        for row in rows:
            normalized = str(row.normalized_doc_url or "").strip().lower()
            if not normalized:
                continue
            # Keep first hit if duplicate normalized doc_url rows exist.
            if normalized not in normalized_to_route_id:
                normalized_to_route_id[normalized] = int(row.id)

        resolved: dict[str, int] = {}
        for normalized, originals in normalized_to_originals.items():
            route_id = normalized_to_route_id.get(normalized)
            if route_id is None:
                continue
            for original in originals:
                resolved[original] = route_id

        return resolved

    # ─────────────────────────────────────────────
    #  Redis cache helpers
    # ─────────────────────────────────────────────

    def _cache_key(self, route_id: int) -> str:
        return f"route_price:{route_id}"

    async def _get_cache(self, route_id: int) -> RoutePriceSchedule | None:
        """Try reading from Redis. Returns None on miss or Redis failure."""

        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(self._cache_key(route_id))
            if raw is None:
                return None
            return RoutePriceSchedule.model_validate_json(raw)
        except Exception:
            self._logger.debug(f"redis cache get failed for route_price:{route_id}, fallback to db")
            return None

    async def _set_cache(self, route_id: int, data: RoutePriceSchedule) -> None:
        """Write to Redis with TTL. Silently ignores failures."""

        if self._redis is None:
            return
        try:
            await self._redis.set(
                self._cache_key(route_id),
                data.model_dump_json(),
                ex=_CACHE_TTL,
            )
        except Exception:
            self._logger.debug(f"redis cache set failed for route_price:{route_id}")
