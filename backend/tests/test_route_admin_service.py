"""Targeted tests for route admin parsing updates."""

from __future__ import annotations

from typing import Any

import pytest

from app.config.settings import Settings
from app.models.schemas import RouteParseResult
from app.services.route_admin_service import RouteAdminService


class _CapturedExecuteResult:
    def __init__(self, rowcount: int = 1) -> None:
        self.rowcount = rowcount


class _CapturedSession:
    def __init__(self) -> None:
        self.last_stmt: Any | None = None
        self.commit_called = False

    async def __aenter__(self) -> "_CapturedSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return

    async def execute(self, stmt: Any) -> _CapturedExecuteResult:
        self.last_stmt = stmt
        return _CapturedExecuteResult()

    async def commit(self) -> None:
        self.commit_called = True


class _CapturedSessionFactory:
    def __init__(self, session: _CapturedSession) -> None:
        self._session = session

    def __call__(self) -> _CapturedSession:
        return self._session


@pytest.mark.anyio
async def test_apply_parse_result_skips_empty_fields() -> None:
    session = _CapturedSession()
    service = RouteAdminService(
        session_factory=_CapturedSessionFactory(session),
        workflow_service=None,
        redis=None,
        settings=Settings(),
    )

    result = RouteParseResult(
        basic_info="7天6晚东京亲子线路",
        highlights="迪士尼,亲子酒店",
        index_tags=[],
        itinerary_days=[],
        notices="旺季请提前锁位",
        cost_included="机票、酒店",
        cost_excluded="签证与个人消费",
        age_limit="3岁以上",
        certificate_limit="护照有效期 6 个月以上",
    )

    await service._apply_parse_result(1, result)

    assert session.commit_called is True
    assert session.last_stmt is not None

    params = session.last_stmt.compile().params
    assert params["base_info"] == "7天6晚东京亲子线路"
    assert params["highlights"] == "迪士尼,亲子酒店"
    assert params["notice"] == "旺季请提前锁位"
    assert params["included"] == "机票、酒店"
    assert params["cost_excluded"] == "签证与个人消费"
    assert params["age_limit"] == "3岁以上"
    assert params["certificate_limit"] == "护照有效期 6 个月以上"
    assert "tags" not in params
    assert "itinerary_json" not in params


@pytest.mark.anyio
async def test_apply_parse_result_skips_update_when_all_fields_empty() -> None:
    session = _CapturedSession()
    service = RouteAdminService(
        session_factory=_CapturedSessionFactory(session),
        workflow_service=None,
        redis=None,
        settings=Settings(),
    )

    await service._apply_parse_result(1, RouteParseResult())

    assert session.last_stmt is None
    assert session.commit_called is False
