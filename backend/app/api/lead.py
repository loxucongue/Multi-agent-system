"""Lead API endpoint for phone capture submission."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.models.schemas import LeadResponse
from app.services.container import services

router = APIRouter()


class LeadSubmitRequest(BaseModel):
    """Lead submit request payload with phone only."""

    phone: str = Field(..., min_length=1)


@router.post("/{session_id}/lead", response_model=LeadResponse)
async def submit_lead(session_id: str, req: LeadSubmitRequest) -> LeadResponse:
    """Submit lead phone and persist lead/session state."""

    await services.initialize()

    if not await services.session_service.is_session_valid(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    state = await services.session_service.get_session_state(session_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    if state.lead_status == "captured":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已提交过联系方式")

    try:
        return await services.lead_service.create_lead(
            session_id=session_id,
            phone=req.phone,
            active_route_id=state.active_route_id,
            user_profile=state.user_profile,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="手机号格式不正确")
