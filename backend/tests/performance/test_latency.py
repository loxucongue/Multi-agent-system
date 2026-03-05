"""Latency benchmark tests for core chat/session flows."""

from __future__ import annotations

import asyncio
import statistics
import time

import pytest
from httpx import AsyncClient

from tests.conftest import FakeRedis, MockServices


async def _wait_done(redis: FakeRedis, run_id: str, timeout: float = 2.0) -> None:
    """Wait until mocked graph marks the run as done."""

    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        if await redis.get(f"done:{run_id}") == "1":
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"run timeout: {run_id}")


async def _measure_session_create_latency(async_client: AsyncClient) -> float:
    """Measure /session/create end-to-end latency in seconds."""

    start = time.perf_counter()
    resp = await async_client.post("/session/create")
    elapsed = time.perf_counter() - start
    assert resp.status_code == 201, resp.text
    return elapsed


async def _measure_recommend_latency(async_client: AsyncClient, redis: FakeRedis) -> float:
    """Measure scene-1 recommend latency from /chat/send to graph done."""

    session_resp = await async_client.post("/session/create")
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["session_id"]

    start = time.perf_counter()
    send_resp = await async_client.post(
        "/chat/send",
        json={"session_id": session_id, "message": "鎺ㄨ崘鏃ユ湰7澶╂父"},
    )
    assert send_resp.status_code == 200, send_resp.text
    run_id = send_resp.json()["run_id"]
    await _wait_done(redis, run_id)
    return time.perf_counter() - start


async def _measure_price_latency(async_client: AsyncClient, redis: FakeRedis) -> float:
    """Measure scene-4 price query latency after one recommend warm-up."""

    session_resp = await async_client.post("/session/create")
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["session_id"]

    warmup = await async_client.post(
        "/chat/send",
        json={"session_id": session_id, "message": "鎺ㄨ崘鏃ユ湰绾胯矾"},
    )
    assert warmup.status_code == 200, warmup.text
    await _wait_done(redis, warmup.json()["run_id"])

    start = time.perf_counter()
    send_resp = await async_client.post(
        "/chat/send",
        json={"session_id": session_id, "message": "price schedule"},
    )
    assert send_resp.status_code == 200, send_resp.text
    run_id = send_resp.json()["run_id"]
    await _wait_done(redis, run_id)
    return time.perf_counter() - start


async def _measure_first_token_latency(async_client: AsyncClient) -> float:
    """Measure stream first-token latency from /chat/stream request start."""

    session_resp = await async_client.post("/session/create")
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["session_id"]

    send_resp = await async_client.post(
        "/chat/send",
        json={"session_id": session_id, "message": "鎺ㄨ崘鏃ユ湰7澶╂父"},
    )
    assert send_resp.status_code == 200, send_resp.text
    run_id = send_resp.json()["run_id"]

    start = time.perf_counter()
    first_token_latency: float | None = None
    async with async_client.stream("GET", f"/chat/stream?run_id={run_id}") as stream_resp:
        assert stream_resp.status_code == 200, stream_resp.text
        async for line in stream_resp.aiter_lines():
            if line.startswith("event: token"):
                first_token_latency = time.perf_counter() - start
                break

    if first_token_latency is None:
        raise AssertionError("did not receive token event")
    return first_token_latency


@pytest.mark.anyio
async def test_latency_benchmark(async_client: AsyncClient, mock_services: MockServices) -> None:
    """Benchmark 4 latency metrics with 3 runs each and print averages."""

    runs = 3
    session_create = []
    recommend = []
    price_query = []
    first_token = []

    for _ in range(runs):
        session_create.append(await _measure_session_create_latency(async_client))
        recommend.append(await _measure_recommend_latency(async_client, mock_services.redis))
        price_query.append(await _measure_price_latency(async_client, mock_services.redis))
        first_token.append(await _measure_first_token_latency(async_client))

    avg_session_create_ms = statistics.mean(session_create) * 1000
    avg_recommend_ms = statistics.mean(recommend) * 1000
    avg_price_ms = statistics.mean(price_query) * 1000
    avg_first_token_ms = statistics.mean(first_token) * 1000

    print("\n=== Latency Benchmark (3 runs average) ===")
    print(f"session create latency: {avg_session_create_ms:.2f} ms")
    print(f"scene1 recommend e2e latency: {avg_recommend_ms:.2f} ms")
    print(f"scene4 price query latency: {avg_price_ms:.2f} ms")
    print(f"stream first token latency: {avg_first_token_ms:.2f} ms")

    assert all(v > 0 for v in session_create)
    assert all(v > 0 for v in recommend)
    assert all(v > 0 for v in price_query)
    assert all(v > 0 for v in first_token)
