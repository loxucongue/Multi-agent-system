"""LangGraph state schema and factory helpers."""

from __future__ import annotations

from typing import Any, Literal, TypeVar, cast

from langchain_core.messages import AnyMessage, HumanMessage
from typing_extensions import Annotated, TypedDict

from app.models.schemas import SessionState, UserProfile

# Stage constants
STAGE_INIT = "init"
STAGE_COLLECTING = "collecting"
STAGE_RECOMMENDED = "recommended"
STAGE_COMPARING = "comparing"
STAGE_REMATCH_COLLECTING = "rematch_collecting"

StageType = Literal[
    "init",
    "collecting",
    "recommended",
    "comparing",
    "rematch_collecting",
]

LeadStatusType = Literal["none", "triggered", "captured"]

IntentType = Literal[
    "route_recommend",
    "route_followup",
    "visa",
    "price_schedule",
    "external_info",
    "rematch",
    "compare",
    "chitchat",
]

T = TypeVar("T")

_VALID_STAGES: set[str] = {
    STAGE_INIT,
    STAGE_COLLECTING,
    STAGE_RECOMMENDED,
    STAGE_COMPARING,
    STAGE_REMATCH_COLLECTING,
}

_VALID_LEAD_STATUS: set[str] = {"none", "triggered", "captured"}
_VALID_INTENTS: set[str] = {
    "route_recommend",
    "route_followup",
    "visa",
    "price_schedule",
    "external_info",
    "rematch",
    "compare",
    "chitchat",
}


def list_append_reducer(left: list[T] | None, right: list[T] | None) -> list[T]:
    """Reducer for append semantics on list fields."""

    return (left or []) + (right or [])


def int_list_append_reducer(left: list[int] | None, right: list[int] | None) -> list[int]:
    """Reducer for integer id lists with append semantics and duplicate guard."""

    result = list(left or [])
    for item in right or []:
        if item not in result:
            result.append(item)
    return result


def int_list_replace_reducer(left: list[int] | None, right: list[int] | None) -> list[int]:
    """Reducer with explicit replace semantics for id lists."""

    _ = left
    return list(right or [])


def dict_merge_reducer(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    """Reducer for shallow-merge semantics on dict fields."""

    merged = dict(left or {})
    if right:
        merged.update(right)
    return merged


class GraphState(TypedDict):
    """Shared LangGraph runtime state."""

    messages: Annotated[list[AnyMessage], list_append_reducer]
    session_id: str
    current_user_message: str

    stage: StageType
    lead_status: LeadStatusType
    lead_phone: str | None

    active_route_id: int | None
    target_route_id: int | None
    candidate_route_ids: Annotated[list[int], int_list_replace_reducer]
    excluded_route_ids: list[int]

    user_profile: UserProfile

    last_intent: IntentType | None
    secondary_intent: IntentType | None
    followup_count: int

    context_turns: list[dict[str, str]]
    state_version: int

    trace_id: str
    run_id: str

    tool_results: dict[str, Any] | None
    response_text: str | None
    response_tokens: list[str] | None
    response_streamed: bool | None
    token_emitter: Any | None

    ui_actions: Annotated[list[dict[str, Any]], list_append_reducer]
    cards: Annotated[list[dict[str, Any]], list_append_reducer]
    state_patches: dict[str, Any]

    slots_ready: bool
    request_human: bool
    error: str | None


def create_initial_state(
    session_state: SessionState,
    user_message: str,
    trace_id: str,
    run_id: str,
) -> GraphState:
    """Convert persisted SessionState to GraphState for one graph run."""

    profile = _parse_user_profile(session_state.user_profile)
    safe_message = user_message.strip()

    return GraphState(
        messages=[HumanMessage(content=safe_message)] if safe_message else [],
        session_id="",
        current_user_message=safe_message,
        stage=_normalize_stage(session_state.stage),
        lead_status=_normalize_lead_status(session_state.lead_status),
        lead_phone=session_state.lead_phone,
        active_route_id=_normalize_optional_int(session_state.active_route_id),
        target_route_id=None,
        candidate_route_ids=_normalize_int_list(session_state.candidate_route_ids),
        excluded_route_ids=_normalize_int_list(session_state.excluded_route_ids),
        user_profile=profile,
        last_intent=_normalize_intent(session_state.last_intent),
        secondary_intent=None,
        followup_count=max(0, int(session_state.followup_count)),
        context_turns=_normalize_context_turns(session_state.context_turns),
        state_version=max(1, int(session_state.state_version)),
        trace_id=trace_id,
        run_id=run_id,
        tool_results=None,
        response_text=None,
        response_tokens=None,
        response_streamed=None,
        token_emitter=None,
        ui_actions=[],
        cards=[],
        state_patches={},
        slots_ready=False,
        request_human=False,
        error=None,
    )


def _parse_user_profile(raw_profile: Any) -> UserProfile:
    if isinstance(raw_profile, UserProfile):
        return raw_profile
    if isinstance(raw_profile, dict):
        return UserProfile.model_validate(raw_profile)
    return UserProfile()


def _normalize_stage(value: str | None) -> StageType:
    if isinstance(value, str) and value in _VALID_STAGES:
        return cast(StageType, value)
    return STAGE_INIT


def _normalize_lead_status(value: str | None) -> LeadStatusType:
    if isinstance(value, str) and value in _VALID_LEAD_STATUS:
        return cast(LeadStatusType, value)
    return "none"


def _normalize_intent(value: str | None) -> IntentType | None:
    if isinstance(value, str) and value in _VALID_INTENTS:
        return cast(IntentType, value)
    return None


def _normalize_int_list(values: list[Any]) -> list[int]:
    normalized: list[int] = []
    for item in values:
        try:
            normalized.append(int(item))
        except (TypeError, ValueError):
            continue
    return normalized


def _normalize_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_context_turns(turns: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        normalized.append(
            {
                "user": str(turn.get("user", "")),
                "assistant": str(turn.get("assistant", "")),
            }
        )
    return normalized
