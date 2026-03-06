"""Global service container for LangGraph and application-wide dependencies."""

from __future__ import annotations

from typing import TypeVar

from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.database import async_session_factory, engine
from app.config.redis import redis_client
from app.config.settings import settings
from app.services.audit_service import AuditService
from app.services.coze_client import CozeClient
from app.services.coze_log_service import CozeLogService
from app.services.kb_admin_service import KBAdminService
from app.services.lead_service import LeadService
from app.services.llm_client import LLMClient
from app.services.prompt_service import ensure_prompt_seeds
from app.services.rate_limiter import RateLimiter
from app.services.route_service import RouteService
from app.services.session_service import SessionService
from app.services.workflow_service import WorkflowService
from app.utils.logger import get_logger

T = TypeVar("T")


class ServiceContainer:
    """Singleton container that owns shared service instances/resources."""

    _instance: ServiceContainer | None = None

    def __new__(cls) -> ServiceContainer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_bootstrapped", False):
            return

        self._logger = get_logger(__name__)
        self._initialized = False
        self._bootstrapped = True

        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._redis: aioredis.Redis | None = None

        self._coze_client: CozeClient | None = None
        self._llm_client: LLMClient | None = None
        self._workflow_service: WorkflowService | None = None
        self._kb_admin_service: KBAdminService | None = None
        self._coze_log_service: CozeLogService | None = None
        self._route_service: RouteService | None = None
        self._session_service: SessionService | None = None
        self._lead_service: LeadService | None = None
        self._rate_limiter: RateLimiter | None = None
        self._audit_service: AuditService | None = None

    async def initialize(self) -> None:
        """Initialize all services and wire shared dependencies once."""

        if self._initialized:
            return

        try:
            self._session_factory = async_session_factory
            self._redis = redis_client

            if not settings.DEEPSEEK_API_KEY.strip():
                self._logger.warning("DEEPSEEK_API_KEY not set, LLM calls will fail")
            self._llm_client = LLMClient.from_settings()

            has_coze_credentials = all(
                [
                    settings.COZE_OAUTH_APP_ID.strip(),
                    settings.COZE_KID.strip(),
                    settings.COZE_PRIVATE_KEY_PATH.strip(),
                ]
            )
            if has_coze_credentials:
                self._coze_client = CozeClient.from_settings()
                self._workflow_service = WorkflowService(client=self._coze_client, settings=settings)
                self._kb_admin_service = KBAdminService(client=self._coze_client)
            else:
                self._logger.warning("Coze credentials not configured, skipping CozeClient init")
                self._coze_client = None
                self._workflow_service = None
                self._kb_admin_service = None

            self._coze_log_service = CozeLogService(session_factory=self._session_factory)
            self._route_service = RouteService(session_factory=self._session_factory, redis=self._redis)
            self._session_service = SessionService(session_factory=self._session_factory, redis=self._redis)
            self._lead_service = LeadService(
                session_factory=self._session_factory,
                redis=self._redis,
                session_service=self._session_service,
            )
            self._rate_limiter = RateLimiter(redis=self._redis)
            self._audit_service = AuditService(session_factory=self._session_factory)
            await ensure_prompt_seeds()

            self._initialized = True
            self._logger.info("service container initialized")
        except Exception:
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        """Release async resources owned by services/container."""

        if self._coze_client is not None:
            try:
                await self._coze_client.aclose()
            except Exception:
                self._logger.exception("failed to close coze client")

        if self._llm_client is not None:
            try:
                await self._llm_client.aclose()
            except Exception:
                self._logger.exception("failed to close llm client")

        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                self._logger.exception("failed to close redis client")

        try:
            await engine.dispose()
        except Exception:
            self._logger.exception("failed to dispose db engine")

        self._coze_client = None
        self._llm_client = None
        self._workflow_service = None
        self._kb_admin_service = None
        self._coze_log_service = None
        self._route_service = None
        self._session_service = None
        self._lead_service = None
        self._rate_limiter = None
        self._audit_service = None
        self._session_factory = None
        self._redis = None
        self._initialized = False

        self._logger.info("service container shutdown complete")

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._require_initialized("session_factory", self._session_factory)

    @property
    def redis(self) -> aioredis.Redis | None:
        return self._redis

    @property
    def coze_client(self) -> CozeClient:
        return self._require_initialized("coze_client", self._coze_client)

    @property
    def llm_client(self) -> LLMClient:
        return self._require_initialized("llm_client", self._llm_client)

    @property
    def workflow_service(self) -> WorkflowService:
        return self._require_initialized("workflow_service", self._workflow_service)

    @property
    def kb_admin_service(self) -> KBAdminService:
        return self._require_initialized("kb_admin_service", self._kb_admin_service)

    @property
    def coze_log_service(self) -> CozeLogService:
        return self._require_initialized("coze_log_service", self._coze_log_service)

    @property
    def route_service(self) -> RouteService:
        return self._require_initialized("route_service", self._route_service)

    @property
    def session_service(self) -> SessionService:
        return self._require_initialized("session_service", self._session_service)

    @property
    def lead_service(self) -> LeadService:
        return self._require_initialized("lead_service", self._lead_service)

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._require_initialized("rate_limiter", self._rate_limiter)

    @property
    def audit_service(self) -> AuditService:
        return self._require_initialized("audit_service", self._audit_service)

    def _require_initialized(self, name: str, value: T | None) -> T:
        if not self._initialized or value is None:
            raise RuntimeError(f"service container is not initialized: {name}")
        return value


services = ServiceContainer()
