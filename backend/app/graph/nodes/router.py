"""Router node: three-stage waterfall intent classifier with rule-first optimization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.graph.state import GraphState, STAGE_REMATCH_COLLECTING
from app.graph.utils import ensure_profile as _ensure_profile_shared
from app.graph.utils import normalize_history as _normalize_history_shared
from app.graph.utils import normalize_int_list as _normalize_int_list_shared
from app.graph.utils import resolve_llm_client as _resolve_llm_client_shared
from app.graph.utils import to_int_or_none as _to_int_or_none_shared
from app.models.schemas import UserProfile
from app.prompts.intent_classification import build_intent_prompt
from app.services.circuit_breaker import degradation_policy
from app.services.container import services
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
_OVERSEAS_COUNTRY_KEYWORDS = (
    "日本",
    "泰国",
    "新加坡",
    "马来西亚",
    "越南",
    "韩国",
    "美国",
    "英国",
    "法国",
    "德国",
    "意大利",
    "西班牙",
    "葡萄牙",
    "希腊",
    "土耳其",
    "埃及",
    "迪拜",
    "阿联酋",
    "澳大利亚",
    "新西兰",
    "加拿大",
    "巴西",
    "俄罗斯",
    "印度",
    "印度尼西亚",
    "菲律宾",
    "柬埔寨",
    "老挝",
    "缅甸",
    "尼泊尔",
    "斯里兰卡",
    "马尔代夫",
    "毛里求斯",
    "塞班",
    "帕劳",
)

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

# ─────────────────────────────────────────────
#  Stage 1: High-confidence fast rules
# ─────────────────────────────────────────────

_FAST_RULES: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"第\s*[0-9一二三四五六七八九十]+\s*条"), "route_followup", 0.95),
    (re.compile(r"(多少钱|价格|报价|团期)"), "price_schedule", 0.92),
    (re.compile(r"(签证|出签|拒签)"), "visa", 0.93),
    (re.compile(r"(换一批|重新推荐|再来几条)"), "rematch", 0.95),
    (re.compile(r"(对比|比较|哪个好|哪条好)"), "compare", 0.93),
    (re.compile(r"^(你好|嗨|hi|hello|谢谢|再见|拜拜|早上好|晚上好|下午好)"), "chitchat", 0.90),
    (re.compile(r"(天气|航班|机票|高铁)"), "external_info", 0.91),
]

_FAST_CONFIDENCE_THRESHOLD = 0.90


def _stage1_fast_rules(user_message: str) -> tuple[str | None, float, str | None]:
    """Stage 1: pattern-match high-confidence rules. Returns (intent, confidence, matched_pattern)."""

    for pattern, intent, confidence in _FAST_RULES:
        if pattern.search(user_message):
            return intent, confidence, pattern.pattern
    return None, 0.0, None


# ─────────────────────────────────────────────
#  Stage 2: Context-aware rule inference
# ─────────────────────────────────────────────

_DESTINATION_PATTERN = re.compile(
    r"(想去|去|到|飞|玩)\s*([\u4e00-\u9fa5A-Za-z]{2,12})"
)
_DAYS_PATTERN = re.compile(r"\d+\s*(天|日|晚)")
_BUDGET_PATTERN = re.compile(r"\d+\s*(万|w|k|元|块|千)", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"(\d{1,2}\s*月|\d{4}年|五一|国庆|春节|元旦|暑假|寒假|清明|端午)")
_PEOPLE_PATTERN = re.compile(r"(\d+\s*(个人|人|位|口)|一家|夫妻|情侣|闺蜜|朋友)")
_QUESTION_STARTERS = re.compile(r"^(怎么|什么|哪|几|多少|多久|有没有|能不能|可以)")


def _stage2_context_rules(
    user_message: str,
    stage: str,
    user_profile: UserProfile,
    candidate_route_ids: list[int],
    active_route_id: int | None,
) -> tuple[str | None, float, str]:
    """Stage 2: context + state-aware inference. Returns (intent, confidence, reasoning)."""

    has_destination = bool(_DESTINATION_PATTERN.search(user_message))
    has_days = bool(_DAYS_PATTERN.search(user_message))
    has_budget = bool(_BUDGET_PATTERN.search(user_message))
    has_date = bool(_DATE_PATTERN.search(user_message))
    has_people = bool(_PEOPLE_PATTERN.search(user_message))
    dimension_count = sum([has_destination, has_days, has_budget, has_date, has_people])

    if stage == "collecting" and dimension_count >= 1:
        if has_destination or dimension_count >= 2:
            return "route_recommend", 0.88, "collecting_stage_with_dimensions"

    if stage == "recommended":
        if _QUESTION_STARTERS.search(user_message) and (active_route_id is not None or candidate_route_ids):
            if not has_destination:
                return "route_followup", 0.85, "recommended_stage_question"

        if _contains_any(user_message, _FOLLOWUP_DETAIL_KEYWORDS) and active_route_id is not None:
            return "route_followup", 0.87, "recommended_stage_detail_keyword"

    if has_destination and not has_days and not has_budget and stage == "init":
        return "route_recommend", 0.82, "init_with_destination"

    return None, 0.0, ""


@dataclass
class _FallbackDecision:
    intent: str
    request_human: bool = False


@dataclass
class _RouterResult:
    intent: str
    secondary_intent: str | None
    extracted_entities: dict[str, Any]
    reasoning: str
    source: str
    confidence: float


async def router_intent_node(state: GraphState) -> dict[str, Any]:
    """Three-stage waterfall: fast rules → context rules → LLM classify."""

    user_message = str(state.get("current_user_message") or "").strip()
    history = await _build_history(state.get("context_turns", []))
    current_profile = _ensure_user_profile(state.get("user_profile"))
    candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))
    active_route_id = _to_int_or_none(state.get("active_route_id"))
    current_stage = str(state.get("stage") or "init")

    request_human = _contains_any(user_message, _HUMAN_KEYWORDS)

    # ── Stage 1: Fast rules ──
    s1_intent, s1_confidence, s1_pattern = _stage1_fast_rules(user_message)
    if s1_intent and s1_confidence >= _FAST_CONFIDENCE_THRESHOLD:
        result = _RouterResult(
            intent=s1_intent,
            secondary_intent=None,
            extracted_entities={},
            reasoning=f"fast_rule: {s1_pattern}",
            source="stage1_fast_rule",
            confidence=s1_confidence,
        )
        _detect_multi_intent_signal(user_message, result)
        return _finalize_router_output(result, state, current_profile, candidate_route_ids, active_route_id, request_human)

    # ── Stage 2: Context-aware rules ──
    s2_intent, s2_confidence, s2_reasoning = _stage2_context_rules(
        user_message, current_stage, current_profile, candidate_route_ids, active_route_id,
    )
    if s2_intent and s2_confidence >= 0.80:
        result = _RouterResult(
            intent=s2_intent,
            secondary_intent=None,
            extracted_entities={},
            reasoning=f"context_rule: {s2_reasoning}",
            source="stage2_context_rule",
            confidence=s2_confidence,
        )
        _detect_multi_intent_signal(user_message, result)
        return _finalize_router_output(result, state, current_profile, candidate_route_ids, active_route_id, request_human)

    # ── Stage 3: LLM classification (with circuit breaker) ──
    if not degradation_policy.llm_available:
        fallback = _fallback_intent_by_keywords(user_message)
        result = _RouterResult(
            intent=fallback.intent,
            secondary_intent=None,
            extracted_entities={},
            reasoning="llm_circuit_open_fallback",
            source="degraded_keyword_fallback",
            confidence=0.6,
        )
        request_human = request_human or fallback.request_human
        return _finalize_router_output(result, state, current_profile, candidate_route_ids, active_route_id, request_human)

    llm_client, should_close = _resolve_llm_client()
    llm_call_record: dict[str, Any] | None = None
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
        await degradation_policy.llm_breaker.record_success()

        intent = _normalize_intent(llm_result.get("intent")) or "route_recommend"
        secondary_intent = _normalize_intent(llm_result.get("secondary_intent"))
        extracted_entities_raw = llm_result.get("extracted_entities") or {}
        reasoning = str(llm_result.get("reasoning") or "")

        result = _RouterResult(
            intent=intent,
            secondary_intent=secondary_intent,
            extracted_entities=extracted_entities_raw,
            reasoning=reasoning,
            source="stage3_llm",
            confidence=float(llm_result.get("confidence") or 0.8),
        )

        llm_call_record = {
            "node": "router",
            "status": "success",
            "input": _truncate_messages(prompt_messages),
            "output": _truncate_obj(llm_result),
        }
    except Exception as exc:
        await degradation_policy.llm_breaker.record_failure()
        fallback = _fallback_intent_by_keywords(user_message)
        result = _RouterResult(
            intent=fallback.intent,
            secondary_intent=None,
            extracted_entities={},
            reasoning="llm_failed_fallback",
            source="stage3_llm_fallback",
            confidence=0.5,
        )
        request_human = request_human or fallback.request_human
        _LOGGER.warning("router llm classify failed, use keyword fallback: %s", exc)
        llm_call_record = {
            "node": "router",
            "status": "fallback",
            "error": str(exc),
            "output": {"intent": result.intent, "reasoning": result.reasoning},
        }
    finally:
        if should_close:
            await llm_client.aclose()

    # Check for multi-intent from LLM reasoning
    reasoning_intents = _extract_intents_from_text(result.reasoning)
    if len(reasoning_intents) >= 2:
        primary, secondary = _resolve_multi_intents(reasoning_intents)
        if primary:
            result.intent = primary
            result.secondary_intent = secondary

    output = _finalize_router_output(result, state, current_profile, candidate_route_ids, active_route_id, request_human)
    if llm_call_record:
        output["llm_calls"] = [llm_call_record]
    return output


def _detect_multi_intent_signal(user_message: str, result: _RouterResult) -> None:
    """Check if a rule-classified message also contains secondary intent signals."""

    found_intents: set[str] = set()
    if _contains_any(user_message, _PRICE_KEYWORDS):
        found_intents.add("price_schedule")
    if _contains_any(user_message, _VISA_KEYWORDS):
        found_intents.add("visa")
    if _contains_any(user_message, _COMPARE_KEYWORDS):
        found_intents.add("compare")
    if _contains_any(user_message, _EXTERNAL_KEYWORDS):
        found_intents.add("external_info")
    if _DESTINATION_PATTERN.search(user_message):
        found_intents.add("route_recommend")

    found_intents.discard(result.intent)
    if found_intents:
        ordered = [i for i in _MULTI_INTENT_PRIORITY if i in found_intents]
        if ordered:
            result.secondary_intent = ordered[0]


def _finalize_router_output(
    result: _RouterResult,
    state: GraphState,
    current_profile: UserProfile,
    candidate_route_ids: list[int],
    active_route_id: int | None,
    request_human: bool,
) -> dict[str, Any]:
    """Apply entity extraction, profile merge, intent validation, and build output."""

    user_message = str(state.get("current_user_message") or "").strip()

    entity_bucket = _select_entities_for_intent(result.intent, result.extracted_entities)

    # Rule-based entity pre-extraction (works even without LLM)
    rule_entities = _extract_entities_by_rules(user_message)
    if rule_entities:
        for key, value in rule_entities.items():
            if key not in entity_bucket or not entity_bucket[key]:
                entity_bucket[key] = value

    profile_patch = _build_user_profile_patch(entity_bucket)

    if _contains_any(user_message, _REMATCH_KEYWORDS):
        rematch_entities = _select_entities_for_intent("rematch", result.extracted_entities)
        rematch_patch = _build_user_profile_patch(rematch_entities)
        if rematch_patch:
            profile_patch.update(rematch_patch)

    updated_profile = _merge_user_profile_non_empty(current_profile, profile_patch)

    intent = result.intent

    if _contains_any(user_message, _REMATCH_KEYWORDS):
        patch_dimension_count = _count_profile_patch_dimensions(profile_patch)
        if patch_dimension_count >= 2:
            intent = "route_recommend"
        else:
            intent = "rematch"

    target_route_index = _extract_target_route_index(entity_bucket, user_message)
    target_route_id = _resolve_target_route_id(target_route_index, candidate_route_ids)

    if intent == "route_followup" and active_route_id is None and not candidate_route_ids:
        intent = "route_recommend"
    if intent == "price_schedule" and active_route_id is None:
        intent = "route_followup"
    if intent == "compare" and len(candidate_route_ids) < 2:
        intent = "route_recommend"
    if intent == "visa":
        has_overseas_country = _has_overseas_country_in_message(user_message)
        if not has_overseas_country:
            if candidate_route_ids or active_route_id is not None:
                intent = "route_followup"
            else:
                intent = "chitchat"
    if state.get("stage") == STAGE_REMATCH_COLLECTING:
        intent = "route_recommend"

    secondary_intent = result.secondary_intent
    if secondary_intent == intent:
        secondary_intent = None

    is_multi = secondary_intent is not None

    payload: dict[str, Any] = {
        "last_intent": intent,
        "secondary_intent": secondary_intent,
        "user_profile": updated_profile,
        "target_route_id": target_route_id,
        "request_human": request_human,
        "is_multi_intent": is_multi,
    }
    return payload


def _extract_entities_by_rules(user_message: str) -> dict[str, Any]:
    """Rule-based entity pre-extraction to reduce LLM dependency."""

    entities: dict[str, Any] = {}

    dest_matches = _DESTINATION_PATTERN.findall(user_message)
    if dest_matches:
        destinations = list(dict.fromkeys(m[1].strip() for m in dest_matches if m[1].strip()))
        if destinations:
            entities["destinations"] = destinations

    days_match = _DAYS_PATTERN.search(user_message)
    if days_match:
        entities["days_range"] = days_match.group(0)

    budget_match = _BUDGET_PATTERN.search(user_message)
    if budget_match:
        entities["budget_range"] = budget_match.group(0)

    date_match = _DATE_PATTERN.search(user_message)
    if date_match:
        entities["depart_date_range"] = date_match.group(0)

    people_match = _PEOPLE_PATTERN.search(user_message)
    if people_match:
        entities["people"] = people_match.group(0)

    return entities


def _resolve_llm_client() -> tuple[object, bool]:
    return _resolve_llm_client_shared()


def _state_for_prompt(state: GraphState) -> dict[str, Any]:
    payload: dict[str, Any] = dict(state)
    profile = payload.get("user_profile")
    if isinstance(profile, UserProfile):
        payload["user_profile"] = profile.model_dump()
    return payload


async def _build_history(context_turns: list[dict[str, str]]) -> list[dict[str, str]]:
    limit = 5
    try:
        limit = await services.config_service.get_int("session_context_turns", 5)
    except Exception:
        limit = 5
    limit = max(1, limit)
    turns = context_turns[-limit:]
    return _normalize_history_shared(turns)


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
    request_human = _contains_any(user_message, _HUMAN_KEYWORDS)
    matched_intents: set[str] = set()

    if _parse_route_index_from_message(user_message) is not None:
        matched_intents.add("route_followup")
    if _contains_any(user_message, _PRICE_KEYWORDS):
        matched_intents.add("price_schedule")
    if _contains_any(user_message, _COMPARE_KEYWORDS):
        matched_intents.add("compare")
    if _contains_any(user_message, _VISA_KEYWORDS):
        matched_intents.add("visa")
    if _contains_any(user_message, _EXTERNAL_KEYWORDS):
        matched_intents.add("external_info")
    if _contains_any(user_message, _REMATCH_KEYWORDS):
        matched_intents.add("rematch")
    if _contains_any(user_message, _FOLLOWUP_DETAIL_KEYWORDS):
        matched_intents.add("route_followup")
    if request_human:
        matched_intents.add("chitchat")

    primary, _ = _resolve_multi_intents(matched_intents)
    return _FallbackDecision(intent=primary or "route_recommend", request_human=request_human)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(kw in text for kw in keywords)


def _has_overseas_country_in_message(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return any(keyword in text for keyword in _OVERSEAS_COUNTRY_KEYWORDS)


def _normalize_int_list(values: Any) -> list[int]:
    return _normalize_int_list_shared(values)


def _to_int_or_none(value: Any) -> int | None:
    return _to_int_or_none_shared(value)


def _ensure_user_profile(value: Any) -> UserProfile:
    return _ensure_profile_shared(value)


def _truncate_messages(messages: list[dict[str, Any]], max_chars: int = 600) -> list[dict[str, str]]:
    truncated: list[dict[str, str]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if len(content) > max_chars:
            content = f"{content[:max_chars]}..."
        truncated.append({"role": role, "content": content})
    return truncated


def _truncate_obj(value: Any, max_chars: int = 1200) -> Any:
    text = str(value)
    if len(text) <= max_chars:
        return value
    return f"{text[:max_chars]}..."
