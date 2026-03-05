"""Admin audit-log query APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.models.database import AuditLog
from app.services.container import services
from app.utils.security import get_current_admin

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get('/')
async def list_logs(
    trace_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1),
) -> dict[str, Any]:
    """Query audit logs by trace/session/time or return global paginated logs."""

    await services.initialize()
    audit_service = services.audit_service

    if trace_id:
        logs = await audit_service.get_logs_by_trace_id(trace_id)
        return {
            'logs': [_to_log_dict(log) for log in logs],
            'total': len(logs),
            'page': page,
            'size': size,
        }

    if session_id:
        result = await audit_service.get_logs_by_session_id(session_id=session_id, page=page, size=size)
        logs = result.get('logs', [])
        total = int(result.get('total', 0))
        return {
            'logs': [_to_log_dict(log) for log in logs],
            'total': total,
            'page': page,
            'size': size,
        }

    if start is not None or end is not None:
        if start is None or end is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='start and end must be provided together',
            )
        result = await audit_service.get_logs_by_time_range(start=start, end=end, page=page, size=size)
        logs = result.get('logs', [])
        total = int(result.get('total', 0))
        return {
            'logs': [_to_log_dict(log) for log in logs],
            'total': total,
            'page': page,
            'size': size,
        }

    offset = (page - 1) * size
    async with services.session_factory() as db:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(size)
        count_stmt = select(func.count()).select_from(AuditLog)

        logs_result = await db.execute(stmt)
        total_result = await db.execute(count_stmt)

        logs = logs_result.scalars().all()
        total = int(total_result.scalar_one() or 0)

    return {
        'logs': [_to_log_dict(log) for log in logs],
        'total': total,
        'page': page,
        'size': size,
    }


@router.get('/{trace_id}')
async def get_log_detail(trace_id: str) -> dict[str, Any]:
    """Get one trace detail record by trace id."""

    await services.initialize()
    logs = await services.audit_service.get_logs_by_trace_id(trace_id)
    if not logs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='log not found')
    return _to_log_dict(logs[0])


def _to_log_dict(log: AuditLog) -> dict[str, Any]:
    """Serialize one AuditLog row to plain JSON-safe dict."""

    return {
        'id': log.id,
        'trace_id': log.trace_id,
        'run_id': log.run_id,
        'session_id': log.session_id,
        'intent': log.intent,
        'search_query': log.search_query,
        'topk_results': log.topk_results,
        'route_id': log.route_id,
        'db_query_summary': log.db_query_summary,
        'api_params': log.api_params,
        'api_latency_ms': log.api_latency_ms,
        'final_answer_summary': log.final_answer_summary,
        'token_usage': log.token_usage,
        'error_stack': log.error_stack,
        'coze_logid': log.coze_logid,
        'coze_debug_url': log.coze_debug_url,
        'created_at': log.created_at.isoformat() if isinstance(log.created_at, datetime) else str(log.created_at),
    }
