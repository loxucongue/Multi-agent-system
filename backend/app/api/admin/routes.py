"""Admin route management API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload

from app.models.database import Route
from app.models.schemas import (
    BatchCreateRequest,
    BatchCreateResponse,
    BatchUploadPreviewResponse,
    ReparseRequest,
    ReparseResponse,
    RouteCreateRequest,
    RouteCreateResponse,
    RouteDetail,
)
from app.services.container import services
from app.utils.security import get_current_admin

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.post("/", response_model=RouteCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_route(req: RouteCreateRequest) -> RouteCreateResponse:
    """创建单条路线并异步触发文档解析。"""

    return await services.route_admin_service.create_route(req)


@router.post("/batch/preview", response_model=BatchUploadPreviewResponse)
async def batch_preview(file: UploadFile = File(...)) -> BatchUploadPreviewResponse:
    """上传 Excel 文件，返回批量导入预览。"""

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过 10MB")

    rows = await services.route_admin_service.parse_excel(content, file.filename)
    valid_count = sum(1 for r in rows if r.error is None)
    error_count = len(rows) - valid_count

    return BatchUploadPreviewResponse(rows=rows, valid_count=valid_count, error_count=error_count)


@router.post("/batch", response_model=BatchCreateResponse, status_code=status.HTTP_201_CREATED)
async def batch_create(req: BatchCreateRequest) -> BatchCreateResponse:
    """批量创建路线（前端确认预览后提交）。"""

    created, failed = await services.route_admin_service.batch_create_routes(req.rows)
    return BatchCreateResponse(created=created, failed=failed)


@router.post("/reparse", response_model=ReparseResponse)
async def reparse_routes(req: ReparseRequest) -> ReparseResponse:
    """对已有路线重新触发文档解析。"""

    accepted, skipped = await services.route_admin_service.reparse_routes(req.route_ids)
    return ReparseResponse(accepted=accepted, skipped=skipped)


@router.get("/")
async def list_routes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", max_length=100),
) -> dict[str, Any]:
    """分页查询路线列表（支持关键词搜索）。"""

    async with services.session_factory() as session:
        base_stmt = select(Route)
        if keyword.strip():
            pattern = f"%{keyword.strip()}%"
            base_stmt = base_stmt.where(Route.name.ilike(pattern) | Route.supplier.ilike(pattern))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        query_stmt = (
            base_stmt
            .order_by(Route.sort_weight.desc(), Route.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(query_stmt)
        routes = result.scalars().all()

    items = [RouteDetail.model_validate(r) for r in routes]
    return {"routes": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{route_id}", response_model=RouteDetail)
async def get_route(route_id: int) -> RouteDetail:
    """查询单条路线详情。"""

    detail = await services.route_service.get_route_detail(route_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="route not found")
    return detail


@router.put("/{route_id}", response_model=RouteDetail)
async def update_route(route_id: int, body: dict[str, Any]) -> RouteDetail:
    """更新路线可编辑字段。"""

    editable_fields = {
        "name", "supplier", "summary", "doc_url", "features",
        "is_hot", "sort_weight",
    }
    update_values = {k: v for k, v in body.items() if k in editable_fields}
    if not update_values:
        raise HTTPException(status_code=400, detail="no editable fields provided")

    async with services.session_factory() as session:
        stmt = update(Route).where(Route.id == route_id).values(**update_values)
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="route not found")
        await session.commit()

    detail = await services.route_service.get_route_detail(route_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="route not found after update")
    return detail


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_route(route_id: int) -> None:
    """删除单条路线。"""

    async with services.session_factory() as session:
        stmt = delete(Route).where(Route.id == route_id)
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="route not found")
        await session.commit()


@router.get("/{route_id}/parse-status")
async def get_parse_status(route_id: int) -> dict[str, Any]:
    """查询路线文档解析状态。"""

    return await services.route_admin_service.get_parse_status(route_id)
