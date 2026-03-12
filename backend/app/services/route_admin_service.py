"""Route administration service for CRUD and Coze workflow-based document parsing."""

from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal
from io import BytesIO
from typing import Any

from redis import asyncio as aioredis
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.models.database import Route, RoutePricing, RouteSchedule
from app.models.schemas import (
    BatchRoutePreviewRow,
    RouteCreateRequest,
    RouteCreateResponse,
    RouteParseResult,
)
from app.services.workflow_service import WorkflowService
from app.utils.logger import get_logger

_PARSE_KEY_PREFIX = "route_parse:"
_PARSE_TTL = 3600


class RouteAdminService:
    """Route admin service including create, batch import, and document parse."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        workflow_service: WorkflowService | None,
        redis: aioredis.Redis | None,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._workflow = workflow_service
        self._redis = redis
        self._settings = settings
        self._logger = get_logger(__name__)
        self._semaphore = asyncio.Semaphore(settings.COZE_PARSE_CONCURRENCY)

    # ---------------------------------------------
    # Public methods
    # ---------------------------------------------

    async def create_route(self, req: RouteCreateRequest) -> RouteCreateResponse:
        """Create a single route and asynchronously trigger document parsing."""

        route = Route(
            name=req.name,
            supplier=req.supplier,
            summary=req.summary,
            doc_url=req.doc_url,
            features=req.features,
            is_hot=req.is_hot,
            sort_weight=req.sort_weight,
            tags=[],
            highlights="",
            base_info="",
            itinerary_json=[],
            notice="",
            included="",
        )

        async with self._session_factory() as session:
            session.add(route)
            try:
                await session.flush()
                route_id = int(route.id)

                if req.price_min is not None and req.price_max is not None:
                    session.add(
                        RoutePricing(
                            route_id=route_id,
                            price_min=req.price_min,
                            price_max=req.price_max,
                            currency=req.currency or "CNY",
                        )
                    )

                if req.schedules_json is not None:
                    schedules_payload = req.schedules_json
                    if isinstance(schedules_payload, str):
                        raw_value = schedules_payload.strip()
                        if raw_value:
                            try:
                                schedules_payload = json.loads(raw_value)
                            except json.JSONDecodeError:
                                schedules_payload = [{"raw": schedules_payload}]
                        else:
                            schedules_payload = None

                    if schedules_payload not in (None, "", [], {}):
                        session.add(
                            RouteSchedule(
                                route_id=route_id,
                                schedules_json=schedules_payload,
                            )
                        )

                await session.commit()
            except IntegrityError as exc:
                message = str(exc)
                message_lower = message.lower()
                if (
                    "duplicate entry" in message_lower
                    or "uq_routes_doc_url" in message_lower
                    or "doc_url" in message_lower
                ):
                    await session.rollback()
                    raise ValueError(f"文档链接已存在: {req.doc_url}") from exc
                raise
            await session.refresh(route)

        # Trigger async document parsing
        if self._workflow and self._settings.COZE_WF_ROUTE_PARSE_ID:
            asyncio.create_task(self._call_parse_and_update(route_id, req.doc_url))

        return RouteCreateResponse(route_id=route_id, name=req.name, parse_status="pending")

    async def parse_excel(self, file_bytes: bytes, filename: str) -> list[BatchRoutePreviewRow]:
        """Parse Excel file and return preview rows."""

        import openpyxl

        wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return []

        rows: list[BatchRoutePreviewRow] = []
        header_map: dict[str, int] = {}
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if row_idx == 1:
                for col_idx, cell in enumerate(row):
                    if cell is not None:
                        header_map[str(cell).strip().lower()] = col_idx
                continue

            def _cell_raw(name: str) -> Any:
                idx = header_map.get(name)
                if idx is None or idx >= len(row):
                    return None
                return row[idx]

            def _cell(name: str) -> str:
                val = _cell_raw(name)
                if val is None:
                    return ""
                return str(val).strip()

            def _first_non_empty(*names: str) -> str:
                for name in names:
                    value = _cell(name)
                    if value:
                        return value
                return ""

            def _parse_decimal(*names: str) -> Decimal | None:
                for name in names:
                    raw_value = _cell_raw(name)
                    if raw_value is None:
                        continue
                    text = str(raw_value).strip()
                    if not text:
                        continue
                    try:
                        return Decimal(text)
                    except Exception:
                        continue
                return None

            name = _first_non_empty("name", "\u7ebf\u8def\u540d\u79f0", "\u8def\u7ebf\u540d\u79f0")
            supplier = _first_non_empty("supplier", "\u4f9b\u5e94\u5546")
            summary = _first_non_empty("summary", "\u7b80\u4ecb", "\u6982\u8ff0")
            doc_url = _first_non_empty("doc_url", "\u6587\u6863\u94fe\u63a5", "\u6587\u6863url")
            features = _first_non_empty("features", "\u7279\u8272") or None
            is_hot_str = _first_non_empty("is_hot", "\u70ed\u95e8")
            sort_weight_str = _first_non_empty("sort_weight", "\u6392\u5e8f\u6743\u91cd")
            price_min = _parse_decimal("price_min", "\u6700\u4f4e\u4ef7", "\u4ef7\u683c\u4e0b\u9650")
            price_max = _parse_decimal("price_max", "\u6700\u9ad8\u4ef7", "\u4ef7\u683c\u4e0a\u9650")
            currency = _first_non_empty("currency", "\u5e01\u79cd") or "CNY"
            schedules_json = _first_non_empty("schedules_json", "\u56e2\u671f", "\u6392\u671f") or None

            is_hot = is_hot_str.lower() in ("1", "true", "yes", "\u662f")
            try:
                sort_weight = int(sort_weight_str) if sort_weight_str else 0
            except ValueError:
                sort_weight = 0

            error: str | None = None
            if not name:
                error = "\u7f3a\u5c11\u7ebf\u8def\u540d\u79f0"
            elif not supplier:
                error = "\u7f3a\u5c11\u4f9b\u5e94\u5546"
            elif not doc_url:
                error = "\u7f3a\u5c11\u6587\u6863\u94fe\u63a5"

            rows.append(
                BatchRoutePreviewRow(
                    row_num=row_idx,
                    name=name,
                    supplier=supplier,
                    summary=summary,
                    doc_url=doc_url,
                    price_min=price_min,
                    price_max=price_max,
                    currency=currency,
                    schedules_json=schedules_json,
                    features=features if features else None,
                    is_hot=is_hot,
                    sort_weight=sort_weight,
                    error=error,
                )
            )

        wb.close()
        return rows

    async def batch_create_routes(
        self, requests: list[RouteCreateRequest]
    ) -> tuple[list[RouteCreateResponse], list[dict[str, Any]]]:
        """Batch create routes and return (created list, failed list)."""

        created: list[RouteCreateResponse] = []
        failed: list[dict[str, Any]] = []

        for idx, req in enumerate(requests):
            try:
                resp = await self.create_route(req)
                created.append(resp)
            except Exception as exc:
                self._logger.warning("batch create failed row=%d name=%s: %s", idx, req.name, exc)
                error_message = str(exc)
                if isinstance(exc, ValueError) and "文档链接已存在" in error_message:
                    failed.append({"name": req.name, "doc_url": req.doc_url, "error": error_message})
                else:
                    failed.append({"name": req.name, "doc_url": req.doc_url, "error": str(exc)})

        return created, failed

    async def reparse_routes(self, route_ids: list[int]) -> tuple[list[int], list[dict[str, Any]]]:
        """Trigger reparse for existing routes and return (accepted, skipped)."""

        accepted: list[int] = []
        skipped: list[dict[str, Any]] = []

        async with self._session_factory() as session:
            stmt = select(Route.id, Route.doc_url).where(Route.id.in_(route_ids))
            result = await session.execute(stmt)
            rows = result.all()

        route_map = {int(r.id): str(r.doc_url) for r in rows}

        for rid in route_ids:
            doc_url = route_map.get(rid)
            if not doc_url:
                skipped.append({"route_id": rid, "reason": "route not found"})
                continue
            if not self._workflow or not self._settings.COZE_WF_ROUTE_PARSE_ID:
                skipped.append({"route_id": rid, "reason": "workflow not configured"})
                continue

            asyncio.create_task(self._call_parse_and_update(rid, doc_url))
            accepted.append(rid)

        return accepted, skipped

    async def get_parse_status(self, route_id: int) -> dict[str, Any]:
        """Read route parse status from Redis."""

        if self._redis is None:
            return {"route_id": route_id, "status": "unknown", "message": "redis unavailable"}

        key = f"{_PARSE_KEY_PREFIX}{route_id}"
        try:
            raw = await self._redis.get(key)
        except Exception:
            return {"route_id": route_id, "status": "unknown", "message": "redis error"}

        if raw is None:
            return {"route_id": route_id, "status": "no_record"}

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"route_id": route_id, "status": "unknown", "message": "invalid data"}

    # ---------------------------------------------
    # Internal: parse and update
    # ---------------------------------------------

    async def _call_parse_and_update(self, route_id: int, doc_url: str) -> None:
        """Call Coze parse workflow and write result back to database."""

        trace_id = str(uuid.uuid4())
        await self._set_parse_status(route_id, "parsing", "\u5de5\u4f5c\u6d41\u6267\u884c\u4e2d")

        try:
            async with self._semaphore:
                result = await self._workflow.run_route_parse(doc_url, trace_id=trace_id)

            await self._apply_parse_result(route_id, result)
            await self._set_parse_status(route_id, "done", "\u89e3\u6790\u5b8c\u6210")
            self._logger.info("route parse done route_id=%d trace_id=%s", route_id, trace_id)

        except Exception as exc:
            self._logger.exception("route parse failed route_id=%d trace_id=%s", route_id, trace_id)
            await self._set_parse_status(route_id, "failed", str(exc)[:500])

    async def _apply_parse_result(self, route_id: int, result: RouteParseResult) -> None:
        """Apply parse result fields to routes table."""

        values: dict[str, Any] = {
            "base_info": result.basic_info,
            "highlights": result.highlights,
            "tags": result.index_tags,
            "itinerary_json": result.itinerary_days if result.itinerary_days else [],
            "notice": result.notices,
            "included": result.cost_included,
            "cost_excluded": result.cost_excluded,
            "age_limit": result.age_limit,
            "certificate_limit": result.certificate_limit,
        }

        async with self._session_factory() as session:
            stmt = update(Route).where(Route.id == route_id).values(**values)
            await session.execute(stmt)
            await session.commit()

    async def _set_parse_status(self, route_id: int, status: str, message: str) -> None:
        """Set parse status in Redis with TTL."""

        if self._redis is None:
            return
        key = f"{_PARSE_KEY_PREFIX}{route_id}"
        data = json.dumps({"route_id": route_id, "status": status, "message": message})
        try:
            await self._redis.set(key, data, ex=_PARSE_TTL)
        except Exception:
            self._logger.debug("failed to set parse status for route_id=%d", route_id)
