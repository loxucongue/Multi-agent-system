"""Session API endpoints for session creation and detail lookup."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models.schemas import RouteCard, SessionCreateResponse, SessionDetailResponse
from app.services.container import services

router = APIRouter()


@router.post("/create", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_session() -> SessionCreateResponse:
    """Create a new session and return the session id."""

    await services.initialize()
    session_id = await services.session_service.create_session()
    return SessionCreateResponse(session_id=session_id)


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(session_id: str) -> SessionDetailResponse:
    """Fetch session state and resolve related route cards for frontend."""

    await services.initialize()

    state = await services.session_service.get_session_state(session_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    candidate_ids = list(state.candidate_route_ids)
    candidate_cards: list[RouteCard] = []

    if candidate_ids:
        batch_items = await services.route_service.get_routes_batch(candidate_ids)
        item_by_id = {item.id: item for item in batch_items}

        for route_id in candidate_ids:
            item = item_by_id.get(route_id)
            if item is None:
                continue
            candidate_cards.append(
                RouteCard(
                    id=item.id,
                    name=item.name,
                    tags=item.tags,
                    summary=item.summary,
                    doc_url=item.doc_url,
                    sort_weight=item.sort_weight,
                    price_min=item.pricing.price_min if item.pricing else None,
                    price_max=item.pricing.price_max if item.pricing else None,
                )
            )

    active_card = None
    if state.active_route_id is not None:
        for card in candidate_cards:
            if card.id == state.active_route_id:
                active_card = card
                break

    return SessionDetailResponse(
        session_id=session_id,
        stage=state.stage,
        lead_status=state.lead_status,
        active_route_id=state.active_route_id,
        candidate_route_ids=candidate_ids,
        user_profile=state.user_profile,
        followup_count=state.followup_count,
        active_card=active_card,
        candidate_cards=candidate_cards,
    )
