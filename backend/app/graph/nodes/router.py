"""Router node: classify user intent and update routing-related state fields."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.config.settings import settings
from app.graph.state import GraphState, STAGE_REMATCH_COLLECTING
from app.models.schemas import UserProfile
from app.prompts.intent_classification import build_intent_prompt
from app.services.container import services
from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_INTENT_SET = {
    "route_recommend",
    "route_followup",
    "visa",
    "price_schedule",
    "external_info",
    "rematch",
    "compare",
    "chitchat",
}

_MULTI_INTENT_PRIORITY = [
    "price_schedule",
    "compare",
    "route_recommend",
    "route_followup",
    "visa",
    "external_info",
    "rematch",
    "chitchat",
]

_REMATCH_KEYWORDS = ("换", "重新推荐", "再来几条", "重匹配", "重新匹配")
_HUMAN_KEYWORDS = ("人工", "客服", "真人", "转人工")
_VISA_KEYWORDS = ("签证", "出签", "拒签", "材料")
_PRICE_KEYWORDS = ("价格", "多少钱", "团期", "报价")
_COMPARE_KEYWORDS = ("对比", "比较", "哪个好", "区别")
_EXTERNAL_KEYWORDS = ("天气", "航班", "机票", "交通", "高铁", "距离", "多久")
_FOLLOWUP_DETAIL_KEYWORDS = ("行程", "费用", "包含", "不含", "注意事项", "亮点", "细节")

_ROUTE_INDEX_PATTERNS = [
    re.compile(r"第\s*([0-9一二两三四五六七八九十]+)\s*条"),
    re.compile(r"([A-Za-z])\s*(?:号)?(?:线路|方案)"),
    re.compile(r"(?:第\s*)?([0-9一二两三四五六七八九十]+)\s*(?:号)?(?:线路|方案)"),
]

_INTENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "name": "intent_classification",
    "schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "secondary_intent": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "extracted_entities": {"type": "object"},
            "reasoning": {"type": "string"},
        },
        "required": ["intent", "secondary_intent", "confidence", "extracted_entities", "reasoning"],
        "additionalProperties": False,
    },
}


@dataclass
class _FallbackDecision:
    intent: str
    request_human: bool = False


async def router_intent_node(state: GraphState) -> dict[str, Any]:
    """Classify intent and return GraphState patch for downstream nodes."""

    user_message = str(state.get("current_user_message") or "").strip()
    history = _build_history(state.get("context_turns", []))
    current_profile = _ensure_user_profile(state.get("user_profile"))
    candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))
    active_route_id = _to_int_or_none(state.get("active_route_id"))

    request_human = _contains_any(user_message, _HUMAN_KEYWORDS)
    intent = "route_recommend"
    secondary_intent: str | None = None
    extracted_entities_raw: Any = {}
    reasoning = ""

    llm_client, should_close = _resolve_llm_client()
    try:
        prompt_messages = await build_intent_prompt(
            user_message=user_message,
            state=_state_for_prompt(state),
            history=history,
        )
        llm_result = await llm_client.chat_json(
            messages=prompt_messages,
            json_schema=_INTENT_OUTPUT_SCHEMA,
            temperature=0.2,
        )
        intent = _normalize_intent(llm_result.get("intent")) or "route_recommend"
        secondary_intent = _normalize_intent(llm_result.get("secondary_intent"))
        extracted_entities_raw = llm_result.get("extracted_entities") or {}
        reasoning = str(llm_result.get("reasoning") or "")
    except Exception as exc:
        fallback = _fallback_intent_by_keywords(user_message)
        intent = fallback.intent
        request_human = request_human or fallback.request_human
        secondary_intent = None
        extracted_entities_raw = {}
        reasoning = "llm_failed_fallback"
        _LOGGER.warning(f"router llm classify failed, use keyword fallback: {exc}")
    finally:
        if should_close:
            await llm_client.aclose()

    # If reasoning indicates multiple intents, enforce priority.
    reasoning_intents = _extract_intents_from_text(reasoning)
    if len(reasoning_intents) >= 2:
        primary, secondary = _resolve_multi_intents(reasoning_intents)
        if primary:
            intent = primary
            secondary_intent = secondary

    entity_bucket = _select_entities_for_intent(intent, extracted_entities_raw)
    profile_patch = _build_user_profile_patch(entity_bucket)

    # rematch keywords may carry fresh conditions even when primary intent is not rematch
    if _contains_any(user_message, _REMATCH_KEYWORDS):
        rematch_entities = _select_entities_for_intent("rematch", extracted_entities_raw)
        rematch_patch = _build_user_profile_patch(rematch_entities)
        if rematch_patch:
            profile_patch.update(rematch_patch)

    updated_profile = _merge_user_profile_non_empty(current_profile, profile_patch)

    # "换一个" 只有在条件不足时才视作 rematch；
    # 如果已经给出 2 个及以上有效维度，则按新的推荐请求处理。
    if _contains_any(user_message, _REMATCH_KEYWORDS):
        patch_dimension_count = _count_profile_patch_dimensions(profile_patch)
        if patch_dimension_count >= 2:
            intent = "route_recommend"
        else:
            intent = "rematch"

    target_route_index = _extract_target_route_index(entity_bucket, user_message)
    target_route_id = _resolve_target_route_id(target_route_index, candidate_route_ids)

    # Rule fallback/override
    if intent == "route_followup" and active_route_id is None and not candidate_route_ids:
        intent = "route_recommend"
    if intent == "price_schedule" and active_route_id is None:
        intent = "route_followup"
    if intent == "compare" and len(candidate_route_ids) < 2:
        intent = "route_recommend"
    if state.get("stage") == STAGE_REMATCH_COLLECTING:
        intent = "route_recommend"

    if secondary_intent == intent:
        secondary_intent = None

    return {
        "last_intent": intent,
        "secondary_intent": secondary_intent,
        "user_profile": updated_profile,
        "target_route_id": target_route_id,
        "request_human": request_human,
    }


def _resolve_llm_client() -> tuple[LLMClient, bool]:
    """Prefer shared container client; fallback to ad-hoc client for robustness."""

    try:
        return services.llm_client, False
    except Exception:
        return LLMClient(), True


def _state_for_prompt(state: GraphState) -> dict[str, Any]:
    payload: dict[str, Any] = dict(state)
    profile = payload.get("user_profile")
    if isinstance(profile, UserProfile):
        payload["user_profile"] = profile.model_dump()
    return payload


def _build_history(context_turns: list[dict[str, str]]) -> list[dict[str, str]]:
    limit = max(1, settings.SESSION_CONTEXT_TURNS)
    turns = context_turns[-limit:]
    history: list[dict[str, str]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        history.append(
            {
                "user": str(turn.get("user", "")),
                "assistant": str(turn.get("assistant", "")),
            }
        )
    return history


def _normalize_intent(value: Any) -> str | None:
    if isinstance(value, str) and value in _INTENT_SET:
        return value
    return None


def _select_entities_for_intent(intent: str, extracted_entities: Any) -> dict[str, Any]:
    if not isinstance(extracted_entities, dict):
        return {}

    if intent in extracted_entities and isinstance(extracted_entities[intent], dict):
        return extracted_entities[intent]
    if intent in {"route_recommend", "rematch"}:
        rr_key = "route_recommend|rematch"
        if rr_key in extracted_entities and isinstance(extracted_entities[rr_key], dict):
            return extracted_entities[rr_key]

    direct_keys = {
        "destinations",
        "days_range",
        "budget_range",
        "depart_date_range",
        "people",
        "style_prefs",
        "origin_city",
        "target_route_index",
    }
    if direct_keys.intersection(extracted_entities.keys()):
        return extracted_entities
    return {}


def _build_user_profile_patch(entities: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}

    destinations = entities.get("destinations")
    if destinations is None and isinstance(entities.get("destination"), str):
        destinations = [entities["destination"]]
    normalized_destinations = _normalize_text_list(destinations)
    if normalized_destinations:
        patch["destinations"] = normalized_destinations

    style_prefs = _normalize_text_list(entities.get("style_prefs"))
    if style_prefs:
        patch["style_prefs"] = style_prefs

    _set_if_non_empty_string(patch, "origin_city", entities.get("origin_city"))
    _set_if_non_empty_string(patch, "days_range", entities.get("days_range") or entities.get("days"))
    _set_if_non_empty_string(
        patch,
        "budget_range",
        entities.get("budget_range") or entities.get("budget"),
    )
    _set_if_non_empty_string(
        patch,
        "depart_date_range",
        entities.get("depart_date_range") or entities.get("depart_date"),
    )
    _set_if_non_empty_string(patch, "people", entities.get("people"))
    return patch


def _count_profile_patch_dimensions(profile_patch: dict[str, Any]) -> int:
    meaningful_keys = {
        "destinations",
        "days_range",
        "budget_range",
        "depart_date_range",
        "people",
        "style_prefs",
        "origin_city",
    }
    count = 0
    for key in meaningful_keys:
        value = profile_patch.get(key)
        if isinstance(value, list):
            if value:
                count += 1
            continue
        if value:
            count += 1
    return count


def _set_if_non_empty_string(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        target[key] = text


def _normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []

    normalized: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _merge_user_profile_non_empty(current: UserProfile, patch: dict[str, Any]) -> UserProfile:
    merged = current.model_dump()
    for key, value in patch.items():
        merged[key] = value
    return UserProfile.model_validate(merged)


def _extract_target_route_index(entities: dict[str, Any], user_message: str) -> int | None:
    raw_index = entities.get("target_route_index")
    parsed = _parse_index_value(raw_index)
    if parsed is not None:
        return parsed
    return _parse_route_index_from_message(user_message)


def _parse_index_value(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        parsed = int(text)
        return parsed if parsed > 0 else None
    return _zh_num_to_int(text)


def _parse_route_index_from_message(message: str) -> int | None:
    for pattern in _ROUTE_INDEX_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        token = match.group(1)

        if len(token) == 1 and token.isalpha():
            idx = ord(token.upper()) - ord("A") + 1
            return idx if idx > 0 else None

        parsed = _parse_index_value(token)
        if parsed is not None:
            return parsed

    return None


def _resolve_target_route_id(target_route_index: int | None, candidate_route_ids: list[int]) -> int | None:
    if target_route_index is None:
        return None
    if target_route_index < 1 or target_route_index > len(candidate_route_ids):
        return None
    return candidate_route_ids[target_route_index - 1]


def _zh_num_to_int(token: str) -> int | None:
    token = token.strip()
    if not token:
        return None

    mapping = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    if token in mapping:
        value = mapping[token]
        return value if value > 0 else None

    if "十" not in token:
        return None

    if token.startswith("十"):
        ones = mapping.get(token[1:], 0)
        return 10 + ones
    if token.endswith("十"):
        tens = mapping.get(token[0], 1)
        return tens * 10

    tens_text, ones_text = token.split("十", 1)
    tens = mapping.get(tens_text, 1)
    ones = mapping.get(ones_text, 0)
    return tens * 10 + ones


def _extract_intents_from_text(text: str) -> set[str]:
    found: set[str] = set()
    if not text:
        return found

    lowered = text.lower()
    for intent in _INTENT_SET:
        if intent in lowered:
            found.add(intent)

    if _contains_any(text, _PRICE_KEYWORDS):
        found.add("price_schedule")
    if _contains_any(text, _VISA_KEYWORDS):
        found.add("visa")
    if _contains_any(text, _COMPARE_KEYWORDS):
        found.add("compare")
    if _contains_any(text, _EXTERNAL_KEYWORDS):
        found.add("external_info")
    if _contains_any(text, _REMATCH_KEYWORDS):
        found.add("rematch")
    return found


def _resolve_multi_intents(found: set[str]) -> tuple[str | None, str | None]:
    ordered = [intent for intent in _MULTI_INTENT_PRIORITY if intent in found]
    if not ordered:
        return None, None
    primary = ordered[0]
    secondary = ordered[1] if len(ordered) >= 2 else None
    return primary, secondary


def _fallback_intent_by_keywords(user_message: str) -> _FallbackDecision:
    if _contains_any(user_message, _HUMAN_KEYWORDS):
        return _FallbackDecision(intent="chitchat", request_human=True)
    if _parse_route_index_from_message(user_message) is not None:
        return _FallbackDecision(intent="route_followup")
    if _contains_any(user_message, _PRICE_KEYWORDS):
        return _FallbackDecision(intent="price_schedule")
    if _contains_any(user_message, _COMPARE_KEYWORDS):
        return _FallbackDecision(intent="compare")
    if _contains_any(user_message, _VISA_KEYWORDS):
        return _FallbackDecision(intent="visa")
    if _contains_any(user_message, _EXTERNAL_KEYWORDS):
        return _FallbackDecision(intent="external_info")
    if _contains_any(user_message, _REMATCH_KEYWORDS):
        return _FallbackDecision(intent="rematch")
    if _contains_any(user_message, _FOLLOWUP_DETAIL_KEYWORDS):
        return _FallbackDecision(intent="route_followup")
    return _FallbackDecision(intent="route_recommend")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(kw in text for kw in keywords)


def _normalize_int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []

    result: list[int] = []
    for value in values:
        parsed = _to_int_or_none(value)
        if parsed is not None:
            result.append(parsed)
    return result


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ensure_user_profile(value: Any) -> UserProfile:
    if isinstance(value, UserProfile):
        return value
    if isinstance(value, dict):
        return UserProfile.model_validate(value)
    return UserProfile()
