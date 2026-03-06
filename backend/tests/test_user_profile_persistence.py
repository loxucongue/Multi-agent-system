"""Tests for user_profile persistence across multi-turn graph pipeline."""

from __future__ import annotations

import pytest

from app.graph.nodes import collect as collect_node
from app.graph.nodes import response as response_node
from app.graph.nodes import router as router_node
from app.graph.nodes import state_update as state_update_node
from app.graph.state import create_initial_state
from tests.conftest import MockServices


class _FakeRouterLLM:
    """Deterministic LLM for router intent/entity extraction."""

    def __init__(self) -> None:
        self._calls = 0

    async def chat_json(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        self._calls += 1
        if self._calls == 1:
            return {
                "intent": "route_recommend",
                "secondary_intent": None,
                "confidence": 0.95,
                "extracted_entities": {"destinations": ["北京"]},
                "reasoning": "turn1",
            }
        return {
            "intent": "route_recommend",
            "secondary_intent": None,
            "confidence": 0.92,
            "extracted_entities": {"days_range": "5天", "budget_range": "没有预算"},
            "reasoning": "turn2",
        }

    async def aclose(self) -> None:
        return


@pytest.mark.anyio
async def test_user_profile_persistence_across_turns(
    mock_services: MockServices,
    test_session_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """router->collect->response->state_update should persist and recover user_profile."""

    fake_llm = _FakeRouterLLM()

    def _fake_resolve_router_llm():
        return fake_llm, False

    async def _fake_collect_questions(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return {
            "questions": ["请问您计划玩几天？"],
            "suggested_state_patch": {"user_profile": {}, "is_new_intent": False},
            "slots_ready": False,
            "reasoning": "test",
        }

    monkeypatch.setattr(router_node, "_resolve_llm_client", _fake_resolve_router_llm)
    monkeypatch.setattr(collect_node, "_generate_collect_questions", _fake_collect_questions)

    async def _run_one_turn(user_message: str, trace_id: str, run_id: str):
        session_state = await mock_services.session_service.get_session_state(test_session_id)
        assert session_state is not None

        state = create_initial_state(session_state, user_message, trace_id, run_id)
        state["session_id"] = test_session_id

        router_patch = await router_node.router_intent_node(state)
        state.update(router_patch)

        collect_patch = await collect_node.collect_requirements_node(state)
        state.update(collect_patch)

        response_patch = await response_node.response_generation_node(state)
        state.update(response_patch)
        assert "user_profile" in (state.get("state_patches") or {})

        persist_patch = await state_update_node.state_update_node(state)
        state.update(persist_patch)
        return state

    # Turn 1: destination only
    turn1_state = await _run_one_turn("我想去北京", trace_id="tr_turn1", run_id="run_turn1")
    assert turn1_state.get("slots_ready") is False

    persisted1 = await mock_services.session_service.get_session_state(test_session_id)
    assert persisted1 is not None
    assert persisted1.user_profile.get("destinations") == ["北京"]
    assert persisted1.user_profile.get("days_range") in (None, "")

    # Turn 2: add days/budget, destination should be preserved from previous turn
    turn2_state = await _run_one_turn("5天 没有预算", trace_id="tr_turn2", run_id="run_turn2")
    assert turn2_state.get("slots_ready") is True

    persisted2 = await mock_services.session_service.get_session_state(test_session_id)
    assert persisted2 is not None
    profile = persisted2.user_profile
    assert profile.get("destinations") == ["北京"]
    assert profile.get("days_range") == "5天"
    assert profile.get("budget_range") == "没有预算"

    # Turn 3 (restore): create_initial_state should recover full profile from persisted session_state
    restored = create_initial_state(
        persisted2,
        user_message="还有什么推荐吗",
        trace_id="tr_turn3",
        run_id="run_turn3",
    )
    assert restored["user_profile"].destinations == ["北京"]
    assert restored["user_profile"].days_range == "5天"
    assert restored["user_profile"].budget_range == "没有预算"

