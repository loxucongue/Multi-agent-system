"""Targeted tests for route admin parse updates and retry behavior."""

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


class _FakeConfigService:
    def __init__(self, value: int) -> None:
        self._value = value

    async def get_int(self, key: str, default: int) -> int:
        assert key == "route_parse_max_retries"
        return self._value


class _FakeWorkflow:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.calls = 0

    async def run_route_parse(self, doc_url: str, trace_id: str) -> RouteParseResult:
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise RuntimeError(f"transient-{self.calls}")
        return RouteParseResult(basic_info=f"parsed:{doc_url}:{trace_id}")


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
        basic_info="7-day family route",
        highlights="Disney + resort hotel",
        index_tags=[],
        itinerary_days=[],
        notices="Book early in peak season",
        cost_included="Flights and hotels",
        cost_excluded="Visa and personal expenses",
        age_limit="3+",
        certificate_limit="Passport valid for 6 months",
    )

    await service._apply_parse_result(1, result)

    assert session.commit_called is True
    assert session.last_stmt is not None

    params = session.last_stmt.compile().params
    assert params["base_info"] == "7-day family route"
    assert params["highlights"] == "Disney + resort hotel"
    assert params["notice"] == "Book early in peak season"
    assert params["included"] == "Flights and hotels"
    assert params["cost_excluded"] == "Visa and personal expenses"
    assert params["age_limit"] == "3+"
    assert params["certificate_limit"] == "Passport valid for 6 months"
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


@pytest.mark.anyio
async def test_route_parse_retry_limit_is_clamped_from_runtime_config() -> None:
    service = RouteAdminService(
        session_factory=_CapturedSessionFactory(_CapturedSession()),
        workflow_service=None,
        redis=None,
        settings=Settings(),
        config_service=_FakeConfigService(99),
    )

    assert await service._get_route_parse_max_retries() == 4


@pytest.mark.anyio
async def test_run_route_parse_with_retry_succeeds_after_transient_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = _FakeWorkflow(failures_before_success=2)
    service = RouteAdminService(
        session_factory=_CapturedSessionFactory(_CapturedSession()),
        workflow_service=workflow,
        redis=None,
        settings=Settings(),
        config_service=_FakeConfigService(3),
    )

    recorded_statuses: list[tuple[str, str]] = []

    async def _fake_set_parse_status(route_id: int, status: str, message: str) -> None:
        recorded_statuses.append((status, message))

    async def _fake_sleep(delay: float) -> None:
        return

    monkeypatch.setattr(service, "_set_parse_status", _fake_set_parse_status)
    monkeypatch.setattr("app.services.route_admin_service.asyncio.sleep", _fake_sleep)

    result = await service._run_route_parse_with_retry(route_id=9, doc_url="https://example.com/9.pdf")

    assert workflow.calls == 3
    assert result.basic_info.startswith("parsed:https://example.com/9.pdf:")
    assert [status for status, _ in recorded_statuses] == [
        "parsing",
        "retrying",
        "parsing",
        "retrying",
        "parsing",
    ]
