"""Trace completeness e2e test for audit log chain."""

from __future__ import annotations

import asyncio
import re

import pytest
from httpx import AsyncClient

from tests.conftest import FakeRedis, MockServices


async def _wait_run_done(redis: FakeRedis, run_id: str, timeout: float = 2.0) -> None:
    """Wait until mocked graph marks done for a run id."""

    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if await redis.get(f"done:{run_id}") == "1":
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"run not finished in time: {run_id}")


@pytest.mark.anyio
async def test_trace_complete(
    async_client: AsyncClient,
    mock_services: MockServices,
    test_session_id: str,
) -> None:
    """Run scenario-1 style chat and verify audit log completeness + masking."""

    send_resp = await async_client.post(
        "/chat/send",
        json={"session_id": test_session_id, "message": "推荐日本7天游，预算1.5万，电话13812345678"},
    )
    assert send_resp.status_code == 200, send_resp.text
    payload = send_resp.json()
    run_id = payload["run_id"]
    trace_id = payload["trace_id"]

    await _wait_run_done(mock_services.redis, run_id)

    logs = await mock_services.audit_service.get_logs_by_trace_id(trace_id)
    assert logs, f"no audit log found for trace_id={trace_id}"
    row = logs[-1]

    assert row.intent
    assert row.search_query is not None
    assert row.topk_results is not None
    assert row.route_id is not None
    assert row.final_answer_summary is not None
    assert isinstance(row.token_usage, dict)
    assert row.token_usage.get("total_tokens") is not None

    raw_phone_pattern = re.compile(r"(?<!\*)1[3-9]\d{9}(?!\*)")
    assert not raw_phone_pattern.search(row.search_query or "")
    assert not raw_phone_pattern.search(row.final_answer_summary or "")
    assert not raw_phone_pattern.search(str(row.api_params or ""))
    assert "138****5678" in (row.search_query or "")
