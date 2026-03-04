"""Prompt builder for intent classification."""

from __future__ import annotations

import json
from typing import Any


def build_intent_prompt(
    user_message: str,
    state: dict[str, Any],
    history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build messages for intent classification with structured extraction."""

    system_prompt = (
        "你是旅游意图分类器，仅输出JSON:{intent,secondary_intent,confidence,extracted_entities,reasoning}。"
        "intent枚举:route_recommend/route_followup/visa/price_schedule/external_info/rematch/compare/chitchat。"
        "多意图按优先级选主意图:price_schedule>compare>route_recommend>route_followup>visa>external_info>rematch>chitchat；"
        "secondary_intent填第二意图，无则null。"
        "extracted_entities schema:"
        "route_recommend/rematch={destinations,days_range,budget_range,depart_date_range,people,style_prefs,origin_city};"
        "route_followup={target_question_type[itinerary|fee|notice|included|general],target_route_index(1起|null)};"
        "visa={country,nationality|null,stay_days|null};"
        "price_schedule={target_route_index|null};"
        "external_info={info_type[weather|flight|transport],city,date,origin_city,dest_city};"
        "compare={route_indices|null};chitchat={}。缺失填null或空数组。"
    )

    state_payload = _state_for_prompt(state)
    user_prompt = (
        f"用户消息:\n{user_message}\n\n"
        "完整输出Schema(严格遵守):\n"
        "{\"intent\":\"route_recommend|route_followup|visa|price_schedule|external_info|rematch|compare|chitchat\","
        "\"secondary_intent\":\"同intent枚举或null\",\"confidence\":\"0~1\","
        "\"extracted_entities\":{"
        "\"route_recommend|rematch\":{\"destinations\":[\"str\"],\"days_range\":\"str|null\",\"budget_range\":\"str|null\","
        "\"depart_date_range\":\"str|null\",\"people\":\"str|null\",\"style_prefs\":[\"str\"],\"origin_city\":\"str|null\"},"
        "\"route_followup\":{\"target_question_type\":\"itinerary|fee|notice|included|general\",\"target_route_index\":\"int|null\"},"
        "\"visa\":{\"country\":\"str\",\"nationality\":\"str|null(默认中国大陆)\",\"stay_days\":\"str|null\"},"
        "\"price_schedule\":{\"target_route_index\":\"int|null\"},"
        "\"external_info\":{\"info_type\":\"weather|flight|transport\",\"city\":\"str|null\",\"date\":\"str|null\","
        "\"origin_city\":\"str|null\",\"dest_city\":\"str|null\"},"
        "\"compare\":{\"route_indices\":\"list[int]|null\"},\"chitchat\":{}},\"reasoning\":\"str\"}\n\n"
        f"会话状态:\n{json.dumps(state_payload, ensure_ascii=False)}\n\n"
        f"历史对话(最近):\n{json.dumps(history, ensure_ascii=False)}\n\n"
        "请仅返回一个JSON对象。"
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
