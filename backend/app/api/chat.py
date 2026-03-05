"""Chat gateway API endpoints for send and SSE stream."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from redis import asyncio as aioredis

from app.graph.graph import run_graph, run_graph_streaming
from app.models.schemas import ChatSendRequest, ChatSendResponse
from app.services.container import services
from app.utils.helpers import generate_run_id, generate_trace_id
from app.utils.logger import get_logger

router = APIRouter()
_LOGGER = get_logger(__name__)

_STREAM_TIMEOUT_SECONDS = 90
_BLPOP_TIMEOUT_SECONDS = 5


@router.post("/send", response_model=ChatSendResponse)
async def send_chat(req: ChatSendRequest) -> ChatSendResponse:
    """Accept one user message and trigger background graph execution."""

    await services.initialize()

    if not await services.session_service.is_session_valid(req.session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found or expired")

    lock_acquired = await services.rate_limiter.acquire_session_lock(req.session_id)
    if not lock_acquired:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="session is processing, please retry",
        )

    handoff_lock = False
    try:
        under_limit = await services.rate_limiter.check_coze_rate_limit()
        if not under_limit:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="service busy, please retry later",
            )

        run_id = generate_run_id()
        trace_id = generate_trace_id()
        redis = services.redis

        if redis is None:
            await run_graph(req.session_id, req.message)
            return ChatSendResponse(run_id=run_id, trace_id=trace_id)

        await redis.set(f"done:{run_id}", "0", ex=300)
        asyncio.create_task(
            _background_run(
                session_id=req.session_id,
                message=req.message,
                run_id=run_id,
                trace_id=trace_id,
                redis=redis,
            )
        )
        handoff_lock = True
        return ChatSendResponse(run_id=run_id, trace_id=trace_id)
    finally:
        if not handoff_lock:
            await services.rate_limiter.release_session_lock(req.session_id)


@router.get("/stream")
async def stream_chat(run_id: str = Query(..., min_length=1)) -> StreamingResponse:
    """Stream graph events via server-sent events."""

    await services.initialize()
    redis = services.redis
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stream unavailable",
        )

    events_key = f"events:{run_id}"
    done_key = f"done:{run_id}"
    events_exists = await redis.exists(events_key)
    done_exists = await redis.exists(done_key)
    if not events_exists and not done_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")

    return StreamingResponse(
        _event_generator(run_id=run_id, redis=redis),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _background_run(
    session_id: str,
    message: str,
    run_id: str,
    trace_id: str,
    redis: aioredis.Redis | None,
) -> None:
    """Execute graph in background and always release session lock."""

    try:
        if redis is None:
            await run_graph(session_id, message)
            return

        await run_graph_streaming(
            session_id=session_id,
            user_message=message,
            run_id=run_id,
            trace_id=trace_id,
            redis_client=redis,
        )
    except Exception as exc:
        _LOGGER.exception("background graph run failed run_id=%s", run_id)
        if redis is not None:
            error_payload = json.dumps(
                {"event": "error", "data": {"message": str(exc)}},
                ensure_ascii=False,
            )
            try:
                await redis.rpush(f"events:{run_id}", error_payload)
                await redis.expire(f"events:{run_id}", 300)
            except Exception:
                _LOGGER.exception("failed to write background error event run_id=%s", run_id)
    finally:
        await services.rate_limiter.release_session_lock(session_id)


async def _event_generator(run_id: str, redis: aioredis.Redis) -> AsyncGenerator[str, None]:
    """Yield SSE events from Redis list until done/error/timeout."""

    events_key = f"events:{run_id}"
    start_time = time.time()

    try:
        while True:
            result = await redis.blpop(events_key, timeout=_BLPOP_TIMEOUT_SECONDS)
            if result is None:
                if time.time() - start_time > _STREAM_TIMEOUT_SECONDS:
                    timeout_data = {"message": "stream timeout"}
                    yield f"event: error\ndata: {json.dumps(timeout_data, ensure_ascii=False)}\n\n"
                    break
                yield ": keepalive\n\n"
                continue

            _, raw_payload = result
            payload_text = raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else str(raw_payload)

            try:
                payload: dict[str, Any] = json.loads(payload_text)
            except json.JSONDecodeError:
                payload = {"event": "error", "data": {"message": "invalid stream payload"}}

            event_type = str(payload.get("event", "message"))
            event_data = payload.get("data", {})
            yield f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            if event_type in ("done", "error"):
                break
    finally:
        try:
            await redis.delete(events_key)
        except Exception:
            _LOGGER.warning("failed to cleanup events key run_id=%s", run_id)
