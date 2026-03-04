"""FastAPI application entrypoint."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.config.database import db_health_check
from app.config.redis import redis_health_check
from app.utils.logger import configure_logging, get_logger, set_trace_id


configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Travel Advisor Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach trace id to request context and response headers."""

    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    set_trace_id(trace_id)

    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    """Return backend health status."""

    redis_ok = await redis_health_check()
    mysql_ok = await db_health_check()

    overall_status = "ok" if (redis_ok and mysql_ok) else "degraded"
    redis_status = "ok" if redis_ok else "error"
    mysql_status = "ok" if mysql_ok else "error"

    logger.info(f"health check redis={redis_status} mysql={mysql_status}")
    return {"status": overall_status, "redis": redis_status, "mysql": mysql_status}
