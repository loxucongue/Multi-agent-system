"""Manual smoke test for LeadService create flow."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.database import async_session_factory, engine
from app.config.redis import redis_client
from app.services.lead_service import LeadService
from app.services.session_service import SessionService


async def main() -> None:
    session_service = SessionService(async_session_factory, redis_client)
    lead_service = LeadService(async_session_factory, redis_client)

    session_id = await session_service.create_session()
    lead_resp = await lead_service.create_lead(
        session_id=session_id,
        phone="13800138000",
        active_route_id=None,
        user_profile={"origin_city": "厦门"},
        source="chat",
    )

    lead_row = await lead_service.get_lead_by_session(session_id)
    state = await session_service.get_session_state(session_id)

    assert lead_resp.success is True
    assert lead_row is not None
    assert lead_row.phone == "13800138000"
    assert lead_row.phone_masked == "138****8000"
    assert state is not None
    assert state.lead_status == "captured"

    print("manual lead check passed")
    print(
        {
            "session_id": session_id,
            "lead_phone_masked": lead_resp.phone_masked,
            "lead_status": state.lead_status,
        }
    )

    await redis_client.aclose()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
