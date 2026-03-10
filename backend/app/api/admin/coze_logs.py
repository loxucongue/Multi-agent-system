"""Admin Coze call log query APIs."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.models.database import CozeCallLog
from app.services.container import services
from app.utils.security import get_current_admin

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/")
async def list_coze_logs(
    trace_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    call_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Query Coze call logs by filters."""

    await services.initialize()
    offset = (page - 1) * size

    async with services.session_factory() as db:
        stmt = select(CozeCallLog)
        count_stmt = select(func.count()).select_from(CozeCallLog)

        if trace_id and trace_id.strip():
            stmt = stmt.where(CozeCallLog.trace_id == trace_id.strip())
            count_stmt = count_stmt.where(CozeCallLog.trace_id == trace_id.strip())
        if session_id and session_id.strip():
            stmt = stmt.where(CozeCallLog.session_id == session_id.strip())
            count_stmt = count_stmt.where(CozeCallLog.session_id == session_id.strip())
        if call_type and call_type.strip():
            stmt = stmt.where(CozeCallLog.call_type == call_type.strip())
            count_stmt = count_stmt.where(CozeCallLog.call_type == call_type.strip())
        if status_filter and status_filter.strip():
            stmt = stmt.where(CozeCallLog.status == status_filter.strip())
            count_stmt = count_stmt.where(CozeCallLog.status == status_filter.strip())
        if start is not None:
            stmt = stmt.where(CozeCallLog.created_at >= start)
            count_stmt = count_stmt.where(CozeCallLog.created_at >= start)
        if end is not None:
            stmt = stmt.where(CozeCallLog.created_at <= end)
            count_stmt = count_stmt.where(CozeCallLog.created_at <= end)

        stmt = stmt.order_by(CozeCallLog.created_at.desc(), CozeCallLog.id.desc()).offset(offset).limit(size)

        logs_result = await db.execute(stmt)
        total_result = await db.execute(count_stmt)
        logs = logs_result.scalars().all()
        total = int(total_result.scalar_one() or 0)

    return {"logs": [_to_dict(log) for log in logs], "total": total, "page": page, "size": size}


@router.get("/stats")
async def coze_call_stats() -> dict[str, Any]:
    """Return Coze call statistics overview."""

    await services.initialize()
    async with services.session_factory() as db:
        total = int((await db.execute(select(func.count()).select_from(CozeCallLog))).scalar_one() or 0)
        success_count = int(
            (await db.execute(select(func.count()).select_from(CozeCallLog).where(CozeCallLog.status == "success")))
            .scalar_one()
            or 0
        )
        avg_latency = (await db.execute(select(func.avg(CozeCallLog.latency_ms)).select_from(CozeCallLog))).scalar_one()
        total_tokens = int(
            (await db.execute(select(func.sum(CozeCallLog.token_count)).select_from(CozeCallLog))).scalar_one() or 0
        )
        type_stats_result = await db.execute(
            select(CozeCallLog.call_type, func.count(), func.avg(CozeCallLog.latency_ms)).group_by(CozeCallLog.call_type)
        )
        by_type = [
            {"call_type": row[0], "count": row[1], "avg_latency_ms": round(float(row[2] or 0), 1)}
            for row in type_stats_result.all()
        ]

    return {
        "total_calls": total,
        "success_count": success_count,
        "error_count": total - success_count,
        "success_rate": round(success_count / total * 100, 1) if total > 0 else 0,
        "avg_latency_ms": round(float(avg_latency or 0), 1),
        "total_tokens": total_tokens,
        "by_type": by_type,
    }


def _to_dict(log: CozeCallLog) -> dict[str, Any]:
    request_params = log.request_params if isinstance(log.request_params, dict) else None
    response_data = log.response_data if isinstance(log.response_data, dict) else None

    return {
        "id": log.id,
        "trace_id": log.trace_id,
        "session_id": log.session_id,
        "call_type": log.call_type,
        "tool_type": _infer_tool_type(log),
        "workflow_id": log.workflow_id,
        "endpoint": log.endpoint,
        "request_params": request_params,
        "input_payload": _extract_input_payload(request_params),
        "response_code": log.response_code,
        "response_data": response_data,
        "output_payload": _extract_output_payload(response_data),
        "coze_logid": log.coze_logid,
        "debug_url": log.debug_url,
        "token_count": log.token_count,
        "latency_ms": log.latency_ms,
        "status": log.status,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat() if isinstance(log.created_at, datetime) else str(log.created_at),
    }


def _infer_tool_type(log: CozeCallLog) -> str:
    if log.workflow_id:
        return "workflow"
    if "/bots/" in log.endpoint or log.call_type.startswith("bot_"):
        return "agent"
    return "api"


def _extract_input_payload(request_params: dict[str, Any] | None) -> Any:
    if not isinstance(request_params, dict):
        return None

    body = request_params.get("body")
    params = request_params.get("params")

    if isinstance(body, dict):
        parameters = body.get("parameters")
        if isinstance(parameters, dict):
            return parameters
        return body

    if isinstance(params, dict):
        return params

    return request_params


def _extract_output_payload(response_data: dict[str, Any] | None) -> Any:
    if not isinstance(response_data, dict):
        return None

    if "data" in response_data:
        return _maybe_json(response_data.get("data"))
    if "output" in response_data:
        return _maybe_json(response_data.get("output"))
    return response_data


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if not ((text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]"))):
        return value
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value
