"""Shared pytest fixtures for backend API e2e-style tests."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from decimal import Decimal
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
    """Very small in-memory async Redis subset for chat stream tests."""

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
        if pair is None:
            return None
        return pair[0]

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
            items = self._lists.setdefault(key, [])
            items.append(value)
            self._cond.notify_all()
            return len(items)

    async def lrange(self, key: str, start: int, end: int) -> list[Any]:
        items = list(self._lists.get(key, []))
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    async def blpop(self, key: str, timeout: int = 0) -> tuple[str, Any] | None:
        end_at = self._now() + timeout if timeout else None

        async with self._cond:
            while True:
                items = self._lists.get(key, [])
                if items:
                    value = items.pop(0)
                    return key, value

                if end_at is not None:
                    remain = end_at - self._now()
                    if remain <= 0:
                        return None
                    try:
                        await asyncio.wait_for(self._cond.wait(), timeout=remain)
                    except asyncio.TimeoutError:
                        return None
                else:
                    await self._cond.wait()

    async def aclose(self) -> None:
        return


class FakeRateLimiter:
    """Simplified rate limiter for tests."""

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


class FakeSessionService:
    """In-memory session service contract used by APIs."""

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
        result = dict(base)
        for key, value in patch.items():
            if isinstance(result.get(key), dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result


class FakeRouteService:
    """In-memory route repository for /session and /compare endpoints."""

    def __init__(self) -> None:
        now = datetime.utcnow()
        self._routes: dict[int, RouteBatchItem] = {
            1: RouteBatchItem(
                id=1,
                name="日本东京亲子7日",
                supplier="测试供应商A",
                tags=["亲子", "轻松"],
                summary="东京迪士尼与城市漫游，适合亲子家庭",
                highlights="迪士尼,亲子酒店,城市观光",
                base_info="7天6晚东京亲子线路",
                itinerary_json=[{"day": 1}, {"day": 2}, {"day": 3}, {"day": 4}, {"day": 5}, {"day": 6}, {"day": 7}],
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
                supplier="测试供应商B",
                tags=["美食", "深度游"],
                summary="大阪京都奈良深度探索",
                highlights="京都古寺,奈良公园,大阪美食",
                base_info="6天5晚关西深度线路",
                itinerary_json=[{"day": 1}, {"day": 2}, {"day": 3}, {"day": 4}, {"day": 5}, {"day": 6}],
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
                supplier="测试供应商C",
                tags=["海岛", "休闲"],
                summary="曼谷城市体验+普吉海岛度假",
                highlights="海岛度假,夜市,SPA",
                base_info="6天5晚泰国度假线路",
                itinerary_json=[{"day": 1}, {"day": 2}, {"day": 3}, {"day": 4}, {"day": 5}, {"day": 6}],
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
    """In-memory lead service that updates fake session state."""

    def __init__(self, session_service: FakeSessionService) -> None:
        self._session_service = session_service
        self._submitted: set[str] = set()

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
            raise ValueError("手机号格式不正确")
        self._submitted.add(session_id)
        masked = f"{phone[:3]}****{phone[-4:]}"
        await self._session_service.update_session_state(
            session_id,
            {"lead_status": "captured", "lead_phone": masked},
        )
        return LeadResponse(success=True, message="提交成功，顾问将尽快联系您", phone_masked=masked)


@dataclass
class MockServices:
    """Fixture bundle of mocked services used by tests."""

    session_service: FakeSessionService
    route_service: FakeRouteService
    lead_service: FakeLeadService
    rate_limiter: FakeRateLimiter
    redis: FakeRedis


async def _mock_run_graph_streaming(
    session_id: str,
    user_message: str,
    run_id: str,
    trace_id: str,
    redis_client: FakeRedis,
) -> None:
    """Deterministic graph mock to drive API e2e tests."""

    state = await services.session_service.get_session_state(session_id)
    if state is None:
        await redis_client.rpush(f"events:{run_id}", json.dumps({"event": "error", "data": {"message": "session not found"}}))
        return

    message = user_message.strip()
    patch: dict[str, Any] = {}
    response = "好的，我来帮您看看。"
    cards: list[dict[str, Any]] = []
    ui_actions: list[dict[str, Any]] = []

    if "签证" in message:
        patch["last_intent"] = "visa"
        response = "日本签证通常需要护照、照片和在职证明，以上信息仅供参考。"
    elif any(k in message for k in ("价格", "团期", "多少钱")):
        patch["last_intent"] = "price_schedule"
        active = state.active_route_id or (state.candidate_route_ids[0] if state.candidate_route_ids else 1)
        patch["active_route_id"] = active
        response = "这条线路价格约 12999-16999 元，价格更新于2026-03-05。"
        ui_actions.append({"action": "collect_phone", "payload": {"reason": "您对该路线表现出较强兴趣，留下手机号顾问会为您确认最新信息"}})
    elif any(k in message for k in ("天气", "航班", "交通")):
        patch["last_intent"] = "external_info"
        response = "东京明日多云转晴，数据来自示例气象源，获取于2026-03-05。"
    elif any(k in message for k in ("换", "重新推荐", "再来几条")):
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
    elif any(k in message for k in ("详细", "行程", "第")):
        patch["last_intent"] = "route_followup"
        patch["followup_count"] = int(state.followup_count) + 1
        response = "第一天抵达东京，第二天迪士尼，后续安排城市与亲子体验。"
    elif any(k in message for k in ("你好", "心情", "天气真好")):
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
            {"id": 1, "name": "日本东京亲子7日", "summary": "东京迪士尼与城市漫游", "tags": ["亲子"], "doc_url": "https://example.com/1.pdf", "highlights": ["迪士尼"]},
            {"id": 2, "name": "日本关西深度6日", "summary": "大阪京都奈良深度探索", "tags": ["深度游"], "doc_url": "https://example.com/2.pdf", "highlights": ["京都古寺"]},
        ]
        response = "为您推荐两条日本线路，分别偏亲子和深度游。"

    updated = await services.session_service.update_session_state(session_id, patch)
    payloads = [
        {"event": "token", "data": {"text": response, "node": "response"}},
    ]
    if cards:
        payloads.append({"event": "cards", "data": cards})
    if ui_actions:
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


@pytest.fixture
def mock_services(monkeypatch: pytest.MonkeyPatch) -> MockServices:
    """Install mocked service container dependencies for API tests."""

    fake_session = FakeSessionService()
    fake_route = FakeRouteService()
    fake_lead = FakeLeadService(fake_session)
    fake_rate = FakeRateLimiter()
    fake_redis = FakeRedis()

    services._initialized = True
    services._session_service = fake_session
    services._route_service = fake_route
    services._lead_service = fake_lead
    services._rate_limiter = fake_rate
    services._redis = fake_redis

    async def _noop() -> None:
        return

    monkeypatch.setattr(services, "initialize", _noop)
    monkeypatch.setattr(chat_api, "run_graph_streaming", _mock_run_graph_streaming)

    return MockServices(
        session_service=fake_session,
        route_service=fake_route,
        lead_service=fake_lead,
        rate_limiter=fake_rate,
        redis=fake_redis,
    )


@pytest.fixture
def anyio_backend() -> str:
    """Force anyio tests to run with asyncio only (no trio dependency)."""

    return "asyncio"


@pytest.fixture
async def async_client(mock_services: MockServices) -> AsyncClient:
    """Create async test client bound to FastAPI app with mocked services."""

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def test_session_id(mock_services: MockServices) -> str:
    """Create isolated session id for each test."""

    return await mock_services.session_service.create_session()
