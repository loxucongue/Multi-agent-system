"""Route administration service for CRUD and Coze workflow-based document parsing."""

from __future__ import annotations

import asyncio
import json
import uuid
from io import BytesIO
from typing import Any

from redis import asyncio as aioredis
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.models.database import Route
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
    """路线管理服务，包含创建、批量导入、文档解析等功能。"""

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

    # ─────────────────────────────────────────────
    #  Public methods
    # ─────────────────────────────────────────────

    async def create_route(self, req: RouteCreateRequest) -> RouteCreateResponse:
        """创建单条路线并异步触发文档解析。"""

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
            await session.commit()
            await session.refresh(route)
            route_id = int(route.id)

        # 异步触发文档解析
        if self._workflow and self._settings.COZE_WF_ROUTE_PARSE_ID:
            asyncio.create_task(
                self._call_parse_and_update(route_id, req.doc_url)
            )

        return RouteCreateResponse(route_id=route_id, name=req.name, parse_status="pending")

    async def parse_excel(self, file_bytes: bytes, filename: str) -> list[BatchRoutePreviewRow]:
        """解析 Excel 文件，返回预览行列表。"""

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

            def _cell(name: str) -> str:
                idx = header_map.get(name)
                if idx is None or idx - 1 >= len(row):
                    return ""
                val = row[idx - 1]
                return str(val).strip() if val is not None else ""

            name = _cell("name") or _cell("线路名称") or _cell("路线名称")
            supplier = _cell("supplier") or _cell("供应商")
            summary = _cell("summary") or _cell("简介") or _cell("概述")
            doc_url = _cell("doc_url") or _cell("文档链接") or _cell("文档url")
            features = _cell("features") or _cell("特色") or None
            is_hot_str = _cell("is_hot") or _cell("热门")
            sort_weight_str = _cell("sort_weight") or _cell("排序权重")

            is_hot = is_hot_str.lower() in ("1", "true", "yes", "是")
            try:
                sort_weight = int(sort_weight_str) if sort_weight_str else 0
            except ValueError:
                sort_weight = 0

            error: str | None = None
            if not name:
                error = "缺少线路名称"
            elif not supplier:
                error = "缺少供应商"
            elif not doc_url:
                error = "缺少文档链接"

            rows.append(
                BatchRoutePreviewRow(
                    row_num=row_idx,
                    name=name,
                    supplier=supplier,
                    summary=summary,
                    doc_url=doc_url,
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
        """批量创建路线，返回 (成功列表, 失败列表)。"""

        created: list[RouteCreateResponse] = []
        failed: list[dict[str, Any]] = []

        for idx, req in enumerate(requests):
            try:
                resp = await self.create_route(req)
                created.append(resp)
            except Exception as exc:
                self._logger.warning("batch create failed row=%d name=%s: %s", idx, req.name, exc)
                failed.append({"name": req.name, "doc_url": req.doc_url, "error": str(exc)})

        return created, failed

    async def reparse_routes(self, route_ids: list[int]) -> tuple[list[int], list[dict[str, Any]]]:
        """对已有路线重新触发文档解析，返回 (已接受列表, 跳过列表)。"""

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
        """查询路线解析状态 (从 Redis 读取)。"""

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

    # ─────────────────────────────────────────────
    #  Internal: parse and update
    # ─────────────────────────────────────────────

    async def _call_parse_and_update(self, route_id: int, doc_url: str) -> None:
        """调用 Coze 解析工作流并将结果回写到 DB。"""

        trace_id = str(uuid.uuid4())
        await self._set_parse_status(route_id, "parsing", "工作流执行中")

        try:
            async with self._semaphore:
                result = await self._workflow.run_route_parse(doc_url, trace_id=trace_id)

            await self._apply_parse_result(route_id, result)
            await self._set_parse_status(route_id, "done", "解析完成")
            self._logger.info("route parse done route_id=%d trace_id=%s", route_id, trace_id)

        except Exception as exc:
            self._logger.exception("route parse failed route_id=%d trace_id=%s", route_id, trace_id)
            await self._set_parse_status(route_id, "failed", str(exc)[:500])

    async def _apply_parse_result(self, route_id: int, result: RouteParseResult) -> None:
        """将解析结果的 9 个字段回写到 routes 表（仅覆盖工作流字段）。"""

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
