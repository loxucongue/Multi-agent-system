"""Shared pytest fixtures for backend API e2e/admin tests."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api import chat as chat_api
from app.models.schemas import LeadResponse, RouteBatchItem, SessionState
from app.services.container import services


class FakeRedis:
    """In-memory subset of async Redis used by chat stream tests."""

    def __init__(self) -> None:
        self._kv: dict[str, tuple[Any, float | None]] = {}
        self._lists: dict[str, list[Any]] = {}
        self._cond = asyncio.Condition()

    def _now(self) -> float:
        return asyncio.get_running_loop().time()

    def _purge_if_expired(self, key: str) -> None:
        value = self._kv.get(key)
        if value is None:
            return
        _, expire_at = value
        if expire_at is not None and expire_at <= self._now():
            self._kv.pop(key, None)

    async def set(self, key: str, value: Any, ex: int | None = None, nx: bool = False) -> bool | None:
        self._purge_if_expired(key)
        if nx and key in self._kv:
            return None
        expire_at = self._now() + ex if ex else None
        self._kv[key] = (value, expire_at)
        return True

    async def get(self, key: str) -> Any | None:
        self._purge_if_expired(key)
        pair = self._kv.get(key)
        return None if pair is None else pair[0]

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._kv:
                self._kv.pop(key, None)
                deleted += 1
            if key in self._lists:
                self._lists.pop(key, None)
                deleted += 1
        return deleted

    async def exists(self, key: str) -> int:
        self._purge_if_expired(key)
        return int(key in self._kv or key in self._lists)

    async def expire(self, key: str, seconds: int) -> bool:
        self._purge_if_expired(key)
        if key not in self._kv:
            return False
        value, _ = self._kv[key]
        self._kv[key] = (value, self._now() + seconds)
        return True

    async def rpush(self, key: str, value: Any) -> int:
        async with self._cond:
            rows = self._lists.setdefault(key, [])
            rows.append(value)
            self._cond.notify_all()
            return len(rows)

    async def lrange(self, key: str, start: int, end: int) -> list[Any]:
        rows = list(self._lists.get(key, []))
        if end == -1:
            return rows[start:]
        return rows[start : end + 1]

    async def blpop(self, key: str, timeout: int = 0) -> tuple[str, Any] | None:
        end_at = self._now() + timeout if timeout else None
        async with self._cond:
            while True:
                rows = self._lists.get(key, [])
                if rows:
                    return key, rows.pop(0)

                if end_at is None:
                    await self._cond.wait()
                    continue

                remain = end_at - self._now()
                if remain <= 0:
                    return None
                try:
                    await asyncio.wait_for(self._cond.wait(), timeout=remain)
                except asyncio.TimeoutError:
                    return None

    async def aclose(self) -> None:
        return


class FakeRateLimiter:
    """Simple in-memory lock/rate limiter."""

    def __init__(self) -> None:
        self._locked: set[str] = set()
        self.allow_rate_limit = True

    async def acquire_session_lock(self, session_id: str, ttl: int = 90) -> bool:
        _ = ttl
        if session_id in self._locked:
            return False
        self._locked.add(session_id)
        return True

    async def release_session_lock(self, session_id: str) -> None:
        self._locked.discard(session_id)

    async def check_coze_rate_limit(self) -> bool:
        return self.allow_rate_limit


class _FakeScalarResult:
    """Minimal wrapper for SQLAlchemy-style scalar result."""

    def __init__(self, rows: list[Any] | None = None, scalar: Any | None = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def all(self) -> list[Any]:
        return list(self._rows)


class _FakeExecuteResult:
    """Minimal wrapper for SQLAlchemy-style execute result."""

    def __init__(self, rows: list[Any] | None = None, scalar: Any | None = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(rows=self._rows, scalar=self._scalar)

    def scalar_one_or_none(self) -> Any | None:
        return self._scalar

    def scalar_one(self) -> Any:
        return self._scalar


class FakeDbSession:
    """Minimal async DB session for admin endpoints."""

    async def __aenter__(self) -> "FakeDbSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return

    async def execute(self, stmt: Any) -> _FakeExecuteResult:
        _ = stmt
        return _FakeExecuteResult(rows=[], scalar=None)

    async def commit(self) -> None:
        return

    async def rollback(self) -> None:
        return

    async def refresh(self, row: Any) -> None:
        _ = row
        return

    def add(self, row: Any) -> None:
        _ = row
        return


class FakeSessionFactory:
    """Callable factory yielding FakeDbSession."""

    def __call__(self) -> FakeDbSession:
        return FakeDbSession()


class FakeSessionService:
    """In-memory session service used by API tests."""

    def __init__(self) -> None:
        self._store: dict[str, SessionState] = {}

    async def create_session(self) -> str:
        session_id = str(uuid4())
        self._store[session_id] = SessionState()
        return session_id

    async def get_session_state(self, session_id: str) -> SessionState | None:
        state = self._store.get(session_id)
        return state.model_copy(deep=True) if state else None

    async def is_session_valid(self, session_id: str) -> bool:
        return session_id in self._store

    async def update_session_state(self, session_id: str, state_patch: dict[str, Any]) -> SessionState:
        current = self._store.get(session_id)
        if current is None:
            raise ValueError("session not found")
        merged = current.model_dump(mode="python")
        merged = self._deep_merge(merged, state_patch)
        if "state_version" not in state_patch:
            merged["state_version"] = int(merged.get("state_version", 1)) + 1
        next_state = SessionState.model_validate(merged)
        self._store[session_id] = next_state
        return next_state.model_copy(deep=True)

    def _deep_merge(self, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        out = dict(base)
        for key, value in patch.items():
            if isinstance(out.get(key), dict) and isinstance(value, dict):
                out[key] = self._deep_merge(out[key], value)
            else:
                out[key] = value
        return out


class FakeRouteService:
    """In-memory route source for /session and /compare APIs."""

    def __init__(self) -> None:
        now = datetime.utcnow()
        self._routes: dict[int, RouteBatchItem] = {
            1: RouteBatchItem(
                id=1,
                name="日本东京亲子7日",
                supplier="Supplier A",
                tags=["亲子", "轻松"],
                summary="东京迪士尼与城市漫游，适合亲子家庭",
                highlights="迪士尼,亲子酒店,城市观光",
                base_info="7天6晚东京亲子线路",
                itinerary_json=[{"day": i} for i in range(1, 8)],
                notice="请准备有效护照和签证资料",
                included="机票、酒店、部分餐食与景点门票",
                doc_url="https://example.com/1.pdf",
                is_hot=True,
                sort_weight=100,
                created_at=now,
                updated_at=now,
                pricing={
                    "price_min": Decimal("12999"),
                    "price_max": Decimal("16999"),
                    "currency": "CNY",
                    "price_updated_at": now,
                },
                schedule={"schedules_json": [{"date": "2026-04-18"}], "schedule_updated_at": now},
            ),
            2: RouteBatchItem(
                id=2,
                name="日本关西深度6日",
                supplier="Supplier B",
                tags=["美食", "深度游"],
                summary="大阪京都奈良深度探索",
                highlights="京都古寺,奈良公园,大阪美食",
                base_info="6天5晚关西深度线路",
                itinerary_json=[{"day": i} for i in range(1, 7)],
                notice="旺季需提前锁定团位",
                included="酒店、交通、导游服务",
                doc_url="https://example.com/2.pdf",
                is_hot=True,
                sort_weight=90,
                created_at=now,
                updated_at=now,
                pricing={
                    "price_min": Decimal("10999"),
                    "price_max": Decimal("14999"),
                    "currency": "CNY",
                    "price_updated_at": now,
                },
                schedule={"schedules_json": [{"date": "2026-04-25"}], "schedule_updated_at": now},
            ),
            3: RouteBatchItem(
                id=3,
                name="泰国曼谷普吉6日",
                supplier="Supplier C",
                tags=["海岛", "休闲"],
                summary="曼谷城市体验+普吉海岛度假",
                highlights="海岛度假,夜市,SPA",
                base_info="6天5晚泰国度假线路",
                itinerary_json=[{"day": i} for i in range(1, 7)],
                notice="雨季请准备防雨用品",
                included="酒店、接送机、景点门票",
                doc_url="https://example.com/3.pdf",
                is_hot=True,
                sort_weight=80,
                created_at=now,
                updated_at=now,
                pricing={
                    "price_min": Decimal("7999"),
                    "price_max": Decimal("11999"),
                    "currency": "CNY",
                    "price_updated_at": now,
                },
                schedule={"schedules_json": [{"date": "2026-05-03"}], "schedule_updated_at": now},
            ),
        }

    async def get_routes_batch(self, route_ids: list[int]) -> list[RouteBatchItem]:
        return [self._routes[rid] for rid in route_ids if rid in self._routes]

    async def get_batch_details(self, route_ids: list[int]) -> list[RouteBatchItem]:
        return await self.get_routes_batch(route_ids)


class FakeLeadService:
    """In-memory lead service that syncs state lead_status."""

    def __init__(self, session_service: FakeSessionService) -> None:
        self._session_service = session_service

    async def create_lead(
        self,
        session_id: str,
        phone: str,
        active_route_id: int | None,
        user_profile: dict[str, Any],
        source: str = "chat",
    ) -> LeadResponse:
        _ = active_route_id, user_profile, source
        if not re.fullmatch(r"^1[3-9]\d{9}$", phone.strip()):
            raise ValueError("invalid phone")

        masked = f"{phone[:3]}****{phone[-4:]}"
        await self._session_service.update_session_state(
            session_id,
            {"lead_status": "captured", "lead_phone": masked},
        )
        return LeadResponse(success=True, message="ok", phone_masked=masked)


@dataclass
class FakeAuditLog:
    """Simple audit log record model used by fake audit service."""

    id: int
    trace_id: str
    run_id: str
    session_id: str
    intent: str
    search_query: str | None
    topk_results: Any
    route_id: int | None
    db_query_summary: str | None
    api_params: dict[str, Any] | None
    api_latency_ms: int | None
    final_answer_summary: str | None
    token_usage: dict[str, Any] | None
    error_stack: str | None
    coze_logid: str | None
    coze_debug_url: str | None
    created_at: datetime = field(default_factory=datetime.utcnow)


class FakeAuditService:
    """In-memory audit service with phone masking behavior."""

    _phone_pattern = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")

    def __init__(self) -> None:
        self._rows: list[FakeAuditLog] = []
        self._next_id = 1

    def _mask_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return self._phone_pattern.sub(lambda m: f"{m.group(1)[:3]}****{m.group(1)[-4:]}", value)
        if isinstance(value, list):
            return [self._mask_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._mask_value(v) for k, v in value.items()}
        return value

    async def log_request(
        self,
        trace_id: str,
        run_id: str,
        session_id: str,
        intent: str,
        search_query: str | None = None,
        topk_results: list[dict[str, Any]] | dict[str, Any] | None = None,
        route_id: int | None = None,
        db_query_summary: str | None = None,
        api_params: dict[str, Any] | None = None,
        api_latency_ms: int | None = None,
        final_answer_summary: str | None = None,
        token_usage: dict[str, Any] | None = None,
        error_stack: str | None = None,
        coze_logid: str | None = None,
        coze_debug_url: str | None = None,
    ) -> None:
        row = FakeAuditLog(
            id=self._next_id,
            trace_id=trace_id,
            run_id=run_id,
            session_id=session_id,
            intent=intent,
            search_query=self._mask_value(search_query),
            topk_results=self._mask_value(topk_results),
            route_id=route_id,
            db_query_summary=self._mask_value(db_query_summary),
            api_params=self._mask_value(api_params),
            api_latency_ms=api_latency_ms,
            final_answer_summary=self._mask_value((final_answer_summary or "")[:500]),
            token_usage=self._mask_value(token_usage),
            error_stack=self._mask_value(error_stack),
            coze_logid=coze_logid,
            coze_debug_url=self._mask_value(coze_debug_url),
        )
        self._rows.append(row)
        self._next_id += 1

    async def get_logs_by_trace_id(self, trace_id: str) -> list[FakeAuditLog]:
        return [row for row in self._rows if row.trace_id == trace_id]

    async def get_logs_by_session_id(self, session_id: str, page: int = 1, size: int = 20) -> dict[str, Any]:
        rows = [row for row in self._rows if row.session_id == session_id]
        offset = (max(1, page) - 1) * max(1, size)
        return {"logs": rows[offset : offset + size], "total": len(rows)}

    async def get_logs_by_time_range(
        self,
        start: datetime,
        end: datetime,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        rows = [row for row in self._rows if start <= row.created_at <= end]
        offset = (max(1, page) - 1) * max(1, size)
        return {"logs": rows[offset : offset + size], "total": len(rows)}


@dataclass
class MockServices:
    """Fixture bundle of mocked services used by tests."""

    session_service: FakeSessionService
    route_service: FakeRouteService
    lead_service: FakeLeadService
    audit_service: FakeAuditService
    rate_limiter: FakeRateLimiter
    redis: FakeRedis


async def _mock_run_graph_streaming(
    session_id: str,
    user_message: str,
    run_id: str,
    trace_id: str,
    redis_client: FakeRedis,
) -> None:
    """Deterministic graph mock to drive API tests."""

    state = await services.session_service.get_session_state(session_id)
    if state is None:
        await redis_client.rpush(
            f"events:{run_id}",
            json.dumps({"event": "error", "data": {"message": "session not found"}}, ensure_ascii=False),
        )
        return

    msg = user_message.strip()
    patch: dict[str, Any] = {}
    response = "好的，我来帮您看看。"
    cards: list[dict[str, Any]] = []
    ui_actions: list[dict[str, Any]] = []

    if "签证" in msg:
        patch["last_intent"] = "visa"
        response = "日本签证通常需要护照、照片和在职证明，以上信息仅供参考。"
    elif any(k in msg for k in ("价格", "团期", "多少钱")):
        patch["last_intent"] = "price_schedule"
        active = state.active_route_id or (state.candidate_route_ids[0] if state.candidate_route_ids else 1)
        patch["active_route_id"] = active
        response = "这条线路价格约 12999-16999 元，价格更新于2026-03-05。"
        ui_actions.append(
            {
                "action": "collect_phone",
                "payload": {
                    "reason": "您对该路线表现出较强兴趣，留下手机号顾问会为您确认最新信息",
                },
            }
        )
    elif any(k in msg for k in ("天气", "航班", "交通")):
        patch["last_intent"] = "external_info"
        response = "东京明日多云转晴，数据来自示例气象源，获取于2026-03-05。"
    elif any(k in msg for k in ("换", "重新推荐", "再来几条")):
        old_ids = [rid for rid in [state.active_route_id, *state.candidate_route_ids] if rid is not None]
        excluded = list(dict.fromkeys([*state.excluded_route_ids, *old_ids]))
        patch.update(
            {
                "last_intent": "rematch",
                "excluded_route_ids": excluded,
                "active_route_id": 3,
                "candidate_route_ids": [3],
                "stage": "recommended",
                "followup_count": 0,
            }
        )
        response = "已为您更换一批推荐，给您一条泰国方向方案。"
    elif any(k in msg for k in ("详细", "行程", "第")):
        patch["last_intent"] = "route_followup"
        patch["followup_count"] = int(state.followup_count) + 1
        response = "第一天抵达东京，第二天迪士尼，后续安排城市与亲子体验。"
    elif any(k in msg for k in ("你好", "心情", "天气真好")):
        patch["last_intent"] = "chitchat"
        response = "很高兴和您聊天，您想去哪里旅游呢？"
    else:
        patch.update(
            {
                "last_intent": "route_recommend",
                "stage": "recommended",
                "active_route_id": 1,
                "candidate_route_ids": [1, 2],
            }
        )
        cards = [
            {
                "id": 1,
                "name": "日本东京亲子7日",
                "summary": "东京迪士尼与城市漫游",
                "tags": ["亲子"],
                "doc_url": "https://example.com/1.pdf",
                "highlights": ["迪士尼"],
            },
            {
                "id": 2,
                "name": "日本关西深度6日",
                "summary": "大阪京都奈良深度探索",
                "tags": ["深度游"],
                "doc_url": "https://example.com/2.pdf",
                "highlights": ["京都古寺"],
            },
        ]
        response = "为您推荐两条日本线路，分别偏亲子和深度游。"

    updated = await services.session_service.update_session_state(session_id, patch)

    payloads: list[dict[str, Any]] = [{"event": "token", "data": {"text": response, "node": "response"}}]
    if cards:
        payloads.append({"event": "cards", "data": cards})
    for action in ui_actions:
        payloads.append({"event": "ui_action", "data": action})
    payloads.append(
        {
            "event": "state_patch",
            "data": {
                "stage": updated.stage,
                "lead_status": updated.lead_status,
                "active_route_id": updated.active_route_id,
                "candidate_route_ids": updated.candidate_route_ids,
                "excluded_route_ids": updated.excluded_route_ids,
                "followup_count": updated.followup_count,
            },
        }
    )
    payloads.append({"event": "done", "data": {"trace_id": trace_id, "run_id": run_id}})

    for event in payloads:
        await redis_client.rpush(f"events:{run_id}", json.dumps(event, ensure_ascii=False))
    await redis_client.set(f"done:{run_id}", "1", ex=300)

    await services.audit_service.log_request(
        trace_id=trace_id,
        run_id=run_id,
        session_id=session_id,
        intent=str(patch.get("last_intent", "route_recommend")),
        search_query=f"{msg} 联系方式13812345678",
        topk_results=cards if cards else [{"document_id": "mock-doc", "score": 0.9}],
        route_id=patch.get("active_route_id") or state.active_route_id or 1,
        db_query_summary="mock db summary",
        api_params={"query": msg, "phone": "13812345678"},
        api_latency_ms=123,
        final_answer_summary=f"{response} 联系电话 13812345678",
        token_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        error_stack=None,
        coze_logid="mock-logid",
        coze_debug_url="https://coze.example/debug",
    )


@pytest.fixture
def mock_services(monkeypatch: pytest.MonkeyPatch) -> MockServices:
    """Install mocked global services for API tests."""

    fake_session = FakeSessionService()
    fake_route = FakeRouteService()
    fake_lead = FakeLeadService(fake_session)
    fake_audit = FakeAuditService()
    fake_rate = FakeRateLimiter()
    fake_redis = FakeRedis()
    fake_session_factory = FakeSessionFactory()

    services._initialized = True
    services._session_service = fake_session
    services._route_service = fake_route
    services._lead_service = fake_lead
    services._rate_limiter = fake_rate
    services._audit_service = fake_audit
    services._redis = fake_redis
    services._session_factory = fake_session_factory

    async def _noop() -> None:
        return

    monkeypatch.setattr(services, "initialize", _noop)
    monkeypatch.setattr(chat_api, "run_graph_streaming", _mock_run_graph_streaming)

    return MockServices(
        session_service=fake_session,
        route_service=fake_route,
        lead_service=fake_lead,
        audit_service=fake_audit,
        rate_limiter=fake_rate,
        redis=fake_redis,
    )


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio tests on asyncio backend only."""

    return "asyncio"


@pytest.fixture
async def async_client(mock_services: MockServices) -> AsyncClient:
    """Create async test client bound to FastAPI app."""

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def test_session_id(mock_services: MockServices) -> str:
    """Create isolated session id for each test."""

    return await mock_services.session_service.create_session()
