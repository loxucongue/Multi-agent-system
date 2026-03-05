"""Degradation and fallback behavior tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.container import services
from tests.conftest import MockServices


@pytest.mark.anyio
async def test_redis_unavailable_still_works(async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis unavailable should not break session create/get flows."""

    monkeypatch.setattr(services, "_redis", None, raising=False)

    create_resp = await async_client.post("/session/create")
    assert create_resp.status_code == 201, create_resp.text
    session_id = create_resp.json()["session_id"]

    detail_resp = await async_client.get(f"/session/{session_id}")
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["session_id"] == session_id


@pytest.mark.anyio
async def test_llm_timeout_fallback(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM timeout should still route by keyword fallback to visa flow."""

    class _FailingLLM:
        async def chat_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise TimeoutError("llm timeout")

    # In mocked graph path, keyword logic should still produce visa answer.
    monkeypatch.setattr(services, "_llm_client", _FailingLLM(), raising=False)

    send_resp = await async_client.post(
        "/chat/send",
        json={"session_id": test_session_id, "message": "日本签证"},
    )
    assert send_resp.status_code == 200, send_resp.text
    run_id = send_resp.json()["run_id"]

    # Read stream output and verify visa-oriented response exists.
    stream_resp = await async_client.get(f"/chat/stream?run_id={run_id}")
    assert stream_resp.status_code == 200, stream_resp.text
    body = stream_resp.text
    assert "签证" in body


@pytest.mark.anyio
async def test_coze_rate_limit_returns_503(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """When rate limit check fails, chat send should return 503."""

    mock_services.rate_limiter.allow_rate_limit = False
    resp = await async_client.post(
        "/chat/send",
        json={"session_id": test_session_id, "message": "test"},
    )
    assert resp.status_code == 503, resp.text


@pytest.mark.anyio
async def test_concurrent_session_lock(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second concurrent request for same session should return 429."""

    first = await async_client.post(
        "/chat/send",
        json={"session_id": test_session_id, "message": "first"},
    )
    assert first.status_code == 200, first.text

    async def _always_locked(session_id: str, ttl: int = 90) -> bool:  # noqa: ARG001
        return False

    monkeypatch.setattr(mock_services.rate_limiter, "acquire_session_lock", _always_locked)

    second = await async_client.post(
        "/chat/send",
        json={"session_id": test_session_id, "message": "second"},
    )
    assert second.status_code == 429, second.text


@pytest.mark.anyio
async def test_invalid_session_returns_404(async_client: AsyncClient) -> None:
    """Unknown session id should return 404 from chat send."""

    resp = await async_client.post(
        "/chat/send",
        json={"session_id": "nonexistent", "message": "test"},
    )
    assert resp.status_code == 404, resp.text
