"""Prompt builder for intent classification with structured extraction."""

from __future__ import annotations

import json
from typing import Any

from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt

_ENTITY_SCHEMA_HINT = (
    "extracted_entities schema by intent:\n"
    "  route_recommend|rematch: {destinations:[str], days_range:str|null, budget_range:str|null, "
    "depart_date_range:str|null, people:str|null, style_prefs:[str], origin_city:str|null}\n"
    "  route_followup: {target_question_type:itinerary|fee|notice|included|general, target_route_index:int|null}\n"
    "  visa: {country:str, nationality:str|null, stay_days:str|null}\n"
    "  price_schedule: {target_route_index:int|null}\n"
    "  external_info: {info_type:weather|flight|transport, city:str|null, date:str|null, "
    "origin_city:str|null, dest_city:str|null}\n"
    "  compare: {route_indices:list[int]|null}\n"
    "  chitchat: {}"
)


async def build_intent_prompt(
    user_message: str,
    state: dict[str, Any],
    history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build messages for intent classification with structured extraction."""

    default_system_prompt = DEFAULT_PROMPTS["intent_classification"]
    system_prompt = (await get_active_prompt("intent_classification")) or default_system_prompt

    state_payload = _state_for_prompt(state)
    recent_history = history[-3:] if len(history) > 3 else history

    user_prompt = (
        f"## 用户消息\n{user_message}\n\n"
        f"## 会话状态\n{json.dumps(state_payload, ensure_ascii=False, default=str)}\n\n"
        f"## 历史对话（最近3轮）\n{json.dumps(recent_history, ensure_ascii=False, default=str)}\n\n"
        f"## Entity Schema\n{_ENTITY_SCHEMA_HINT}\n\n"
        "请严格按 JSON 格式返回，不要输出任何额外文本。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _state_for_prompt(state: dict[str, Any]) -> dict[str, Any]:
    """Keep intent classification state context compact and stable."""

    keep_keys = {
        "stage",
        "lead_status",
        "active_route_id",
        "candidate_route_ids",
        "excluded_route_ids",
        "user_profile",
        "last_intent",
        "followup_count",
    }
    return {k: v for k, v in state.items() if k in keep_keys}
