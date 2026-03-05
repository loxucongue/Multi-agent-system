"""E2E scenario tests for chat/session/compare/lead APIs with mocks."""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import AsyncClient

from tests.conftest import FakeRedis, MockServices


async def _wait_run_done(redis: FakeRedis, run_id: str, timeout: float = 2.0) -> None:
    """Poll done key until mocked background run finishes."""

    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        done = await redis.get(f"done:{run_id}")
        if done == "1":
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"run not finished within timeout: {run_id}")


async def _run_send_and_wait(
    async_client: AsyncClient,
    mock_services: MockServices,
    session_id: str,
    message: str,
) -> str:
    """Call /chat/send and wait for done."""

    resp = await async_client.post("/chat/send", json={"session_id": session_id, "message": message})
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    await _wait_run_done(mock_services.redis, run_id)
    return run_id


async def _get_events(redis: FakeRedis, run_id: str) -> list[dict]:
    """Read raw event payloads from fake Redis list."""

    rows = await redis.lrange(f"events:{run_id}", 0, -1)
    events: list[dict] = []
    for row in rows:
        text = row.decode("utf-8") if isinstance(row, bytes) else str(row)
        events.append(json.loads(text))
    return events


@pytest.mark.anyio
async def test_recommendation_flow(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """Recommendation scene."""

    run_id = await _run_send_and_wait(async_client, mock_services, test_session_id, "推荐日本7天游")
    assert run_id.startswith("run_")

    state_resp = await async_client.get(f"/session/{test_session_id}")
    assert state_resp.status_code == 200
    state = state_resp.json()
    assert state["stage"] in ("recommended", "collecting")
    assert "candidate_route_ids" in state
    assert isinstance(state["candidate_route_ids"], list)


@pytest.mark.anyio
async def test_followup_flow(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """Followup scene increments followup_count."""

    await _run_send_and_wait(async_client, mock_services, test_session_id, "推荐日本亲子线路")
    await _run_send_and_wait(async_client, mock_services, test_session_id, "第一条线路的详细行程")

    state_resp = await async_client.get(f"/session/{test_session_id}")
    assert state_resp.status_code == 200
    state = state_resp.json()
    assert int(state["followup_count"]) >= 1


@pytest.mark.anyio
async def test_visa_flow(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """Visa scene should return visa-related token event."""

    run_id = await _run_send_and_wait(async_client, mock_services, test_session_id, "日本签证怎么办")
    events = await _get_events(mock_services.redis, run_id)
    token_events = [e for e in events if e.get("event") == "token"]
    assert token_events
    assert "\u7b7e\u8bc1" in token_events[0]["data"]["text"]


@pytest.mark.anyio
async def test_price_schedule_flow(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """Price scene should include price text and updated marker."""

    await _run_send_and_wait(async_client, mock_services, test_session_id, "推荐日本线路")
    run_id = await _run_send_and_wait(async_client, mock_services, test_session_id, "这条线路多少钱")
    events = await _get_events(mock_services.redis, run_id)
    token_text = next(e["data"]["text"] for e in events if e.get("event") == "token")
    assert "\u4ef7\u683c" in token_text
    assert "\u66f4\u65b0\u4e8e" in token_text


@pytest.mark.anyio
async def test_external_info_flow(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """External info scene should include weather text."""

    run_id = await _run_send_and_wait(async_client, mock_services, test_session_id, "东京明天天气怎么样")
    events = await _get_events(mock_services.redis, run_id)
    token_text = next(e["data"]["text"] for e in events if e.get("event") == "token")
    assert ("\u5929\u6c14" in token_text) or ("\u6c14\u8c61" in token_text)


@pytest.mark.anyio
async def test_rematch_flow(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """Rematch scene should push old routes to excluded list."""

    await _run_send_and_wait(async_client, mock_services, test_session_id, "推荐日本线路")
    before = await async_client.get(f"/session/{test_session_id}")
    assert before.status_code == 200
    before_state = before.json()

    await _run_send_and_wait(async_client, mock_services, test_session_id, "换几条其他的")
    after = await async_client.get(f"/session/{test_session_id}")
    assert after.status_code == 200
    after_state = after.json()

    old_ids = set(before_state.get("candidate_route_ids", []))
    assert old_ids
    assert old_ids != set(after_state.get("candidate_route_ids", []))

    state_obj = await mock_services.session_service.get_session_state(test_session_id)
    assert state_obj is not None
    assert old_ids.issubset(set(state_obj.excluded_route_ids))


@pytest.mark.anyio
async def test_compare_flow(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """Compare endpoint should return 2 routes."""

    resp = await async_client.post(f"/session/{test_session_id}/compare", json={"route_ids": [1, 2]})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "routes" in data
    assert len(data["routes"]) == 2


@pytest.mark.anyio
async def test_chitchat_flow(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """Chitchat scene should include travel guidance text."""

    run_id = await _run_send_and_wait(async_client, mock_services, test_session_id, "你好呀")
    events = await _get_events(mock_services.redis, run_id)
    token_text = next(e["data"]["text"] for e in events if e.get("event") == "token")
    assert "\u65c5\u6e38" in token_text


@pytest.mark.anyio
async def test_lead_flow(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """Lead flow: first success, second conflict, invalid phone returns 422."""

    resp = await async_client.post(f"/session/{test_session_id}/lead", json={"phone": "13812345678"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True

    resp2 = await async_client.post(f"/session/{test_session_id}/lead", json={"phone": "13812345678"})
    assert resp2.status_code == 409

    fresh_session = await mock_services.session_service.create_session()
    resp3 = await async_client.post(f"/session/{fresh_session}/lead", json={"phone": "abc"})
    assert resp3.status_code == 422
