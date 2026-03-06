"""FastAPI application entrypoint."""

import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response

from app.api.admin.auth import router as admin_auth_router
from app.api.admin.coze_logs import router as admin_coze_logs_router
from app.api.admin.config import router as admin_config_router
from app.api.admin.kb import router as admin_kb_router
from app.api.admin.logs import router as admin_logs_router
from app.api.admin.prompts import router as admin_prompts_router
from app.api.chat import router as chat_router
from app.api.compare import router as compare_router
from app.api.lead import router as lead_router
from app.api.session import router as session_router
from app.config.settings import settings
from app.config.database import db_health_check
from app.config.redis import redis_health_check
from app.services.container import services
from app.utils.logger import configure_logging, get_logger, set_trace_id


configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup/shutdown lifecycle resources."""

    await services.initialize()
    logger.info("application startup complete")
    yield
    await services.shutdown()
    logger.info("application shutdown complete")


app = FastAPI(title="Travel Advisor Backend", lifespan=lifespan)

app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(session_router, prefix="/session", tags=["session"])
app.include_router(compare_router, prefix="/session", tags=["compare"])
app.include_router(lead_router, prefix="/session", tags=["lead"])
app.include_router(admin_auth_router, prefix="/admin", tags=["admin-auth"])
app.include_router(admin_prompts_router, prefix="/admin/prompts", tags=["admin-prompts"])
app.include_router(admin_kb_router, prefix="/admin/kb", tags=["admin-kb"])
app.include_router(admin_logs_router, prefix="/admin/logs", tags=["admin-logs"])
app.include_router(admin_coze_logs_router, prefix="/admin/coze-logs", tags=["admin-coze-logs"])
app.include_router(admin_config_router, prefix="/admin/config", tags=["admin-config"])

cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
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


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Return 422 for value errors."""

    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return 500 for unhandled exceptions."""

    logger.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


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
