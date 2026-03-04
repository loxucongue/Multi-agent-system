"""Lead capture service."""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Lead
from app.services.session_service import SessionService
from app.utils.logger import get_logger

_DEFAULT_SOURCE = "chat"
_DEFAULT_STATUS = "new"


class LeadService:
    """Service for persisting lead records."""

    def __init__(self, session: AsyncSession, session_service: SessionService | None = None) -> None:
        self._session = session
        self._session_service = session_service or SessionService(session=session)
        self._logger = get_logger(__name__)

    async def create_lead(self, session_id: str, phone: str, active_route_id: int) -> int:
        """Create a lead record and return lead id."""

        normalized_phone = self._normalize_phone(phone)

        if not await self._session_service.is_session_valid(session_id):
            raise ValueError(f"invalid or expired session: {session_id}")

        session_state = await self._session_service.get_session_state(session_id)
        user_profile = session_state.user_profile if session_state is not None else None

        lead = Lead(
            session_id=session_id,
            phone=normalized_phone,
            phone_masked=self._mask_phone(normalized_phone),
            source=_DEFAULT_SOURCE,
            active_route_id=active_route_id,
            user_profile_json=user_profile or None,
            status=_DEFAULT_STATUS,
        )
        self._session.add(lead)

        try:
            await self._session_service.update_session_state(
                session_id,
                {
                    "lead_status": _DEFAULT_STATUS,
                    "active_route_id": active_route_id,
                },
            )
            await self._session.refresh(lead)
        except Exception:
            await self._session.rollback()
            raise

        self._logger.info(
            f"lead created session_id={session_id} lead_id={lead.id} active_route_id={active_route_id}"
        )
        return lead.id

    def _mask_phone(self, phone: str) -> str:
        """Mask middle digits of phone for privacy."""

        value = phone.strip()
        if len(value) <= 7:
            return "*" * len(value)
        return f"{value[:3]}****{value[-4:]}"

    def _normalize_phone(self, phone: str) -> str:
        """Normalize and validate phone number before persistence."""

        value = phone.strip().replace(" ", "").replace("-", "")
        if not re.fullmatch(r"\+?\d{7,20}", value):
            raise ValueError("invalid phone format")
        return value
