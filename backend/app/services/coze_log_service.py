"""Coze API call logging service."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.database import CozeCallLog
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)


class CozeLogService:
    """Persist one row per Coze API call."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def log_call(
        self,
        *,
        trace_id: str,
        session_id: str = "",
        call_type: str,
        workflow_id: str | None = None,
        endpoint: str,
        request_params: dict[str, Any] | None = None,
        response_code: int | None = None,
        response_data: dict[str, Any] | None = None,
        coze_logid: str | None = None,
        debug_url: str | None = None,
        token_count: int | None = None,
        latency_ms: int = 0,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        """Write one Coze call log row."""

        try:
            row = CozeCallLog(
                trace_id=trace_id,
                session_id=session_id or "",
                call_type=call_type,
                workflow_id=workflow_id,
                endpoint=endpoint,
                request_params=request_params,
                response_code=response_code,
                response_data=self._truncate_response(response_data),
                coze_logid=coze_logid,
                debug_url=debug_url,
                token_count=token_count,
                latency_ms=max(0, int(latency_ms)),
                status=status,
                error_message=(error_message[:2000] if error_message else None),
            )
            async with self._session_factory() as session:
                session.add(row)
                await session.commit()
        except Exception as exc:
            _LOGGER.warning(f"failed to persist coze call log: {exc}")

    def _truncate_response(
        self,
        data: dict[str, Any] | None,
        max_len: int = 5000,
    ) -> dict[str, Any] | None:
        if data is None:
            return None
        text = json.dumps(data, ensure_ascii=False, default=str)
        if len(text) <= max_len:
            return data
        return {"_truncated": True, "_preview": text[:max_len]}
