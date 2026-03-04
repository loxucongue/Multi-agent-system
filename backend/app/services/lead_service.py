"""Lead capture/query service."""

from __future__ import annotations

from typing import Any

from redis import asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.database import Lead, Session
from app.models.schemas import LeadInfo, LeadListResponse, LeadResponse
from app.utils.logger import get_logger
from app.utils.security import mask_phone, validate_phone

_LEAD_CAPTURED_STATUS = "captured"
_LEAD_DEFAULT_STATUS = "new"


class LeadService:
    """Lead persistence and admin query service."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: aioredis.Redis | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._logger = get_logger(__name__)

    async def create_lead(
        self,
        session_id: str,
        phone: str,
        active_route_id: int | None = None,
        user_profile: dict[str, Any] | None = None,
        source: str = "chat",
    ) -> LeadResponse:
        """Create lead and mark session lead_status as captured."""

        normalized_phone = phone.strip()
        if not validate_phone(normalized_phone):
            raise ValueError("手机号格式不正确")

        masked_phone = mask_phone(normalized_phone)

        async with self._session_factory() as session:
            session_row = await self._get_session_row(session, session_id)
            if session_row is None:
                raise ValueError(f"session not found: {session_id}")

            lead = Lead(
                session_id=session_id,
                phone=normalized_phone,
                phone_masked=masked_phone,
                source=source,
                active_route_id=active_route_id,
                user_profile_json=user_profile,
                status=_LEAD_DEFAULT_STATUS,
            )
            session.add(lead)

            state_payload = dict(session_row.state_json or {})
            state_payload["lead_status"] = _LEAD_CAPTURED_STATUS
            session_row.state_json = state_payload
            session_row.state_version = (session_row.state_version or 1) + 1

            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        await self._invalidate_session_cache(session_id)

        self._logger.info(f"lead created session_id={session_id} phone_masked={masked_phone}")
        return LeadResponse(
            success=True,
            message="提交成功，顾问将尽快联系您",
            phone_masked=masked_phone,
        )

    async def get_lead_by_session(self, session_id: str) -> LeadInfo | None:
        """Get latest lead record by session id."""

        async with self._session_factory() as session:
            stmt = (
                select(Lead)
                .where(Lead.session_id == session_id)
                .order_by(Lead.created_at.desc(), Lead.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if row is None:
            return None
        return LeadInfo.model_validate(row)

    async def get_leads_list(
        self,
        page: int = 1,
        size: int = 20,
        status: str | None = None,
    ) -> LeadListResponse:
        """Get paginated leads for admin usage."""

        page = 1 if page < 1 else page
        size = 20 if size < 1 else size
        offset = (page - 1) * size

        async with self._session_factory() as session:
            stmt = select(Lead)
            count_stmt = select(func.count()).select_from(Lead)

            if status:
                stmt = stmt.where(Lead.status == status)
                count_stmt = count_stmt.where(Lead.status == status)

            stmt = stmt.order_by(Lead.created_at.desc(), Lead.id.desc()).offset(offset).limit(size)

            rows_result = await session.execute(stmt)
            total_result = await session.execute(count_stmt)
            rows = rows_result.scalars().all()
            total = int(total_result.scalar_one() or 0)

        items = [LeadInfo.model_validate(item) for item in rows]
        return LeadListResponse(leads=items, total=total)

    async def _get_session_row(self, session: AsyncSession, session_id: str) -> Session | None:
        stmt = select(Session).where(Session.id == session_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _invalidate_session_cache(self, session_id: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(f"session:{session_id}")
        except Exception:
            self._logger.debug(f"redis delete failed for session:{session_id}")
