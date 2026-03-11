"""Audit log persistence and query service."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.database import AuditLog
from app.utils.logger import get_logger
from app.utils.security import mask_phone, validate_phone

_FINAL_SUMMARY_MAX_LEN = 500
_PHONE_IN_TEXT_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")


class AuditService:
    """Service for writing and querying audit logs."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._logger = get_logger(__name__)

    async def log_request(
        self,
        trace_id: str,
        run_id: str,
        session_id: str,
        intent: str,
        search_query: str | None = None,
        topk_results: list[dict[str, Any]] | dict[str, Any] | None = None,
        route_id: int | None = None,
        db_query_summary: str | None = None,
        api_params: dict[str, Any] | None = None,
        api_latency_ms: int | None = None,
        final_answer_summary: str | None = None,
        token_usage: dict[str, Any] | None = None,
        error_stack: str | None = None,
        coze_logid: str | None = None,
        coze_debug_url: str | None = None,
    ) -> None:
        """Write one audit log record with masking and truncation."""

        masked_search_query = self._mask_sensitive(search_query)
        masked_topk_results = self._mask_sensitive(topk_results)
        masked_db_query_summary = self._mask_sensitive(db_query_summary)
        masked_api_params = self._mask_sensitive(api_params)
        masked_final_answer_summary = self._mask_sensitive(final_answer_summary)
        masked_token_usage = self._mask_sensitive(token_usage)
        masked_error_stack = self._mask_sensitive(error_stack)
        masked_coze_debug_url = self._mask_sensitive(coze_debug_url)

        safe_topk_results = self._to_json_compatible(masked_topk_results)
        safe_api_params = self._to_json_compatible(masked_api_params)
        safe_token_usage = self._to_json_compatible(masked_token_usage)

        if isinstance(masked_final_answer_summary, str):
            masked_final_answer_summary = masked_final_answer_summary[:_FINAL_SUMMARY_MAX_LEN]
        else:
            masked_final_answer_summary = None

        row = AuditLog(
            trace_id=trace_id,
            run_id=run_id,
            session_id=session_id,
            intent=intent,
            search_query=masked_search_query,
            topk_results=safe_topk_results,
            route_id=route_id,
            db_query_summary=masked_db_query_summary,
            api_params=safe_api_params,
            api_latency_ms=api_latency_ms,
            final_answer_summary=masked_final_answer_summary,
            token_usage=safe_token_usage,
            error_stack=masked_error_stack,
            coze_logid=coze_logid,
            coze_debug_url=masked_coze_debug_url,
        )

        async with self._session_factory() as session:
            session.add(row)
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                self._logger.exception(
                    f"audit log write failed trace_id={trace_id} run_id={run_id} session_id={session_id}"
                )
                raise

    async def get_logs_by_trace_id(self, trace_id: str) -> list[AuditLog]:
        """Query all logs by trace id."""

        async with self._session_factory() as session:
            stmt = (
                select(AuditLog)
                .where(AuditLog.trace_id == trace_id)
                .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_logs_by_session_id(
        self,
        session_id: str,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """Query paginated logs by session id."""

        page = max(1, page)
        size = max(1, size)
        offset = (page - 1) * size

        async with self._session_factory() as session:
            stmt = (
                select(AuditLog)
                .where(AuditLog.session_id == session_id)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .offset(offset)
                .limit(size)
            )
            count_stmt = select(func.count()).select_from(AuditLog).where(AuditLog.session_id == session_id)

            logs_result = await session.execute(stmt)
            total_result = await session.execute(count_stmt)

            logs = logs_result.scalars().all()
            total = int(total_result.scalar_one() or 0)

        return {"logs": logs, "total": total}

    async def get_logs_by_time_range(
        self,
        start: datetime,
        end: datetime,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """Query paginated logs by created_at time range [start, end]."""

        page = max(1, page)
        size = max(1, size)
        offset = (page - 1) * size

        async with self._session_factory() as session:
            stmt = (
                select(AuditLog)
                .where(AuditLog.created_at >= start, AuditLog.created_at <= end)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .offset(offset)
                .limit(size)
            )
            count_stmt = (
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.created_at >= start, AuditLog.created_at <= end)
            )

            logs_result = await session.execute(stmt)
            total_result = await session.execute(count_stmt)

            logs = logs_result.scalars().all()
            total = int(total_result.scalar_one() or 0)

        return {"logs": logs, "total": total}

    def _mask_sensitive(self, data: Any) -> Any:
        """Recursively mask phone-like values in payload."""

        if data is None:
            return None

        if isinstance(data, str):
            value = data.strip()
            if validate_phone(value):
                return mask_phone(value)
            return _PHONE_IN_TEXT_PATTERN.sub(lambda m: mask_phone(m.group(1)), data)

        if isinstance(data, list):
            return [self._mask_sensitive(item) for item in data]

        if isinstance(data, dict):
            return {key: self._mask_sensitive(value) for key, value in data.items()}

        return data

    def _to_json_compatible(self, data: Any) -> Any:
        """Convert complex Python objects into JSON-serializable structures."""
        if data is None:
            return None

        if isinstance(data, (str, int, float, bool)):
            return data

        if isinstance(data, (datetime, date, time)):
            return data.isoformat()

        if isinstance(data, Decimal):
            return str(data)

        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")

        if isinstance(data, dict):
            return {str(key): self._to_json_compatible(value) for key, value in data.items()}

        if isinstance(data, (list, tuple, set)):
            return [self._to_json_compatible(item) for item in data]

        return str(data)
