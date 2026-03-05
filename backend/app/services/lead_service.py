"""Lead capture/query service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from redis import asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.database import Lead
from app.models.schemas import LeadListItem, LeadResponse
from app.utils.logger import get_logger
from app.utils.security import mask_phone, validate_phone

if TYPE_CHECKING:
    from app.services.session_service import SessionService

_LEAD_CAPTURED_STATUS = "captured"
_LEAD_DEFAULT_STATUS = "new"


class LeadService:
    """Lead persistence and admin query service."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: aioredis.Redis | None,
        session_service: SessionService,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._logger = get_logger(__name__)
        self._session_service = session_service

    async def create_lead(
        self,
        session_id: str,
        phone: str,
        active_route_id: int | None,
        user_profile: dict[str, Any],
        source: str = "chat",
    ) -> LeadResponse:
        """Create lead and sync lead status to session state."""

        normalized_phone = phone.strip()
        if not validate_phone(normalized_phone):
            raise ValueError("手机号格式不正确")

        masked_phone = mask_phone(normalized_phone)

        async with self._session_factory() as session:
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

            try:
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        await self._session_service.update_session_state(
            session_id=session_id,
            state_patch={
                "lead_status": _LEAD_CAPTURED_STATUS,
                "lead_phone": masked_phone,
            },
        )

        self._logger.info(f"lead created session_id={session_id} phone_masked={masked_phone}")
        return LeadResponse(
            success=True,
            message="提交成功，顾问将尽快联系您",
            phone_masked=masked_phone,
        )

    async def get_lead_by_session(self, session_id: str) -> Lead | None:
        """Get latest lead record by session id."""

        async with self._session_factory() as session:
            stmt = (
                select(Lead)
                .where(Lead.session_id == session_id)
                .order_by(Lead.created_at.desc(), Lead.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_leads_list(
        self,
        page: int = 1,
        size: int = 20,
        status: str | None = None,
        *,
        include_raw_phone: bool = False,
    ) -> dict[str, Any]:
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

        leads: list[dict[str, Any]] = []
        for row in rows:
            phone_value = row.phone if include_raw_phone else row.phone_masked
            item = LeadListItem(
                id=row.id,
                session_id=row.session_id,
                phone=phone_value,
                source=row.source,
                active_route_id=row.active_route_id,
                status=row.status,
                created_at=row.created_at,
            )
            leads.append(item.model_dump())

        return {"leads": leads, "total": total}
