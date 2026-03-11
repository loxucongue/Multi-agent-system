"""Collect requirement node: progressive guidance with template-first slot filling."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState, STAGE_COLLECTING, STAGE_REMATCH_COLLECTING
from app.graph.utils import ensure_profile as _ensure_profile_shared
from app.graph.utils import resolve_llm_client as _resolve_llm_client_shared
from app.models.schemas import UserProfile
from app.prompts.requirement_collection import build_collect_prompt
from app.services.circuit_breaker import degradation_policy
from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_SOFT_GUIDE = "如果您能告诉我大致的出行天数和预算，我可以为您推荐更匹配的线路哦~"

_GENERIC_REMATCH_PHRASES = {
    "换一批",
    "换一组",
    "换几个",
    "再来几条",
    "再来几个",
    "重新推荐",
    "重新匹配",
    "重匹配",
    "换个方案",
}

_STYLE_HINTS = (
    "亲子",
    "情侣",
    "蜜月",
    "轻松",
    "美食",
    "海岛",
    "摄影",
    "购物",
    "人文",
    "探险",
)

_SLOT_QUESTIONS: dict[str, str] = {
    "destination": "您想去哪里玩呢？比如日本、泰国、新加坡等~",
    "days_range": "大致玩几天呢？",
    "budget_range": "每人预算大概在什么范围？",
    "depart_date_range": "什么时候出发呢？",
    "people": "几个人出行？有小朋友或老人吗？",
    "style_prefs": "有偏好的旅行风格吗？比如亲子、蜜月、美食、购物等~",
    "origin_city": "您从哪个城市出发？",
}

_COLLECT_OUTPUT_SCHEMA: dict[str, Any] = {
    "name": "requirement_collection",
    "schema": {
        "type": "object",
        "properties": {
            "questions": {"type": "array", "items": {"type": "string"}},
            "suggested_state_patch": {"type": "object"},
            "slots_ready": {"type": "boolean"},
            "reasoning": {"type": "string"},
        },
        "required": ["questions", "suggested_state_patch", "slots_ready", "reasoning"],
        "additionalProperties": True,
    },
}


async def collect_requirements_node(state: GraphState) -> dict[str, Any]:
    """Collect destination and optional constraints with progressive guidance.

    Strategy: '宽进严筛' — only destination is required to start searching.
    Soft guides prompt for additional info without blocking the flow.
    """

    profile = _ensure_profile(state.get("user_profile"))
    user_message = str(state.get("current_user_message") or "").strip()
    last_intent = str(state.get("last_intent") or "")
    in_rematch_collecting = state.get("stage") == STAGE_REMATCH_COLLECTING

    # "宽进严筛": only need destination to start recommendation
    slots_ready = _has_minimum_inputs(profile)

    if in_rematch_collecting:
        if last_intent != "rematch":
            response_text = "好的，我基于刚才确认的条件继续为您匹配新的线路。"
            if slots_ready and _should_soft_guide(profile):
                response_text = f"{response_text}\n{_SOFT_GUIDE}"
            return {
                "user_profile": profile,
                "slots_ready": slots_ready,
                "response_text": response_text,
                "stage": STAGE_COLLECTING,
            }

        response_text = _build_rematch_confirmation_text(user_message=user_message, profile=profile)
        if slots_ready and _should_soft_guide(profile):
            response_text = f"{response_text}\n{_SOFT_GUIDE}"

        return {
            "user_profile": profile,
            "slots_ready": False,
            "response_text": response_text,
            "stage": STAGE_REMATCH_COLLECTING,
        }

    if slots_ready:
        response_text = "好的，已收到您的需求，我这就为您筛选匹配的线路。"
        if _should_soft_guide(profile):
            response_text = f"{response_text}\n{_SOFT_GUIDE}"

        return {
            "user_profile": profile,
            "slots_ready": True,
            "response_text": response_text,
        }

    # No destination yet — use template questions (no LLM needed for simple cases)
    missing_slots = _get_missing_slots(profile)

    if not _needs_llm_for_collection(user_message, missing_slots):
        response_text = _template_questions(missing_slots)
        return {
            "user_profile": profile,
            "slots_ready": False,
            "response_text": response_text,
            "stage": STAGE_COLLECTING,
        }

    # Complex case: user message is ambiguous or contradictory, use LLM
    if not degradation_policy.llm_available:
        response_text = _template_questions(missing_slots)
        return {
            "user_profile": profile,
            "slots_ready": False,
            "response_text": response_text,
            "stage": STAGE_COLLECTING,
        }

    llm_result = await _generate_collect_questions(
        user_message=user_message,
        profile=profile,
        missing_slots=missing_slots,
    )

    updated_profile = _apply_suggested_profile_patch(profile, llm_result.get("suggested_state_patch"))
    response_text = _format_questions(llm_result.get("questions"))

    return {
        "user_profile": updated_profile,
        "slots_ready": _has_minimum_inputs(updated_profile),
        "response_text": response_text,
        "stage": STAGE_COLLECTING,
    }


def _ensure_profile(value: Any) -> UserProfile:
    return _ensure_profile_shared(value)


def _get_missing_slots(profile: UserProfile) -> list[str]:
    missing: list[str] = []

    if len(profile.destinations) == 0:
        missing.append("destination")
    if not profile.days_range:
        missing.append("days_range")
    if not profile.budget_range:
        missing.append("budget_range")
    if not profile.depart_date_range:
        missing.append("depart_date_range")
    if not profile.people:
        missing.append("people")
    if len(profile.style_prefs) == 0:
        missing.append("style_prefs")
    if not profile.origin_city:
        missing.append("origin_city")

    return missing


def _has_minimum_inputs(profile: UserProfile) -> bool:
    """'宽进严筛': only destination is required to begin recommendation."""

    return len(profile.destinations) > 0


def _should_soft_guide(profile: UserProfile) -> bool:
    """Whether to append soft guidance for additional info."""

    return not profile.days_range and not profile.budget_range


def _has_ready_recommendation_inputs(profile: UserProfile) -> bool:
    """Legacy check: at least destination + one other dimension."""

    if len(profile.destinations) == 0:
        return False

    other_dimensions = (
        bool(str(profile.days_range or "").strip()),
        bool(str(profile.budget_range or "").strip()),
        bool(str(profile.depart_date_range or "").strip()),
        bool(str(profile.people or "").strip()),
        len(profile.style_prefs) > 0,
        bool(str(profile.origin_city or "").strip()),
    )
    return any(other_dimensions)


def _needs_llm_for_collection(user_message: str, missing_slots: list[str]) -> bool:
    """Determine if LLM is needed for understanding ambiguous user input."""

    if "destination" in missing_slots:
        return False

    ambiguity_signals = [
        "但" in user_message and ("不" in user_message or "别" in user_message),
        "或者" in user_message and "和" in user_message,
        user_message.count("？") >= 2 or user_message.count("?") >= 2,
        len(user_message) > 100,
    ]
    return any(ambiguity_signals)


def _template_questions(missing_slots: list[str]) -> str:
    """Build template-based follow-up using slot-specific questions."""

    if not missing_slots:
        return _SLOT_QUESTIONS["destination"]

    if "destination" in missing_slots:
        return _SLOT_QUESTIONS["destination"]

    questions = []
    priority_order = ["days_range", "budget_range", "depart_date_range", "people", "style_prefs", "origin_city"]
    for slot in priority_order:
        if slot in missing_slots and slot in _SLOT_QUESTIONS:
            questions.append(_SLOT_QUESTIONS[slot])
            if len(questions) >= 2:
                break

    if not questions:
        return _SLOT_QUESTIONS["destination"]

    return "为了推荐更精准，想再确认一下：\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))


async def _generate_collect_questions(
    user_message: str,
    profile: UserProfile,
    missing_slots: list[str],
) -> dict[str, Any]:
    llm_client, should_close = _resolve_llm_client()
    try:
        messages = await build_collect_prompt(
            user_message=user_message,
            user_profile=profile.model_dump(),
            missing_slots=missing_slots,
        )
        result = await llm_client.chat_json(
            messages=messages,
            json_schema=_COLLECT_OUTPUT_SCHEMA,
            temperature=0.3,
        )
        await degradation_policy.llm_breaker.record_success()
        if isinstance(result, dict):
            return result
    except Exception as exc:
        await degradation_policy.llm_breaker.record_failure()
        _LOGGER.warning(f"collect requirement llm failed, fallback to template questions: {exc}")
    finally:
        if should_close:
            await llm_client.aclose()

    return {
        "questions": [_template_questions(missing_slots)],
        "suggested_state_patch": {},
        "slots_ready": False,
        "reasoning": "fallback",
    }


def _resolve_llm_client() -> tuple[LLMClient, bool]:
    return _resolve_llm_client_shared()


def _format_questions(questions_value: Any) -> str:
    questions: list[str] = []
    if isinstance(questions_value, list):
        for item in questions_value:
            text = str(item).strip()
            if text:
                questions.append(text)

    if not questions:
        questions = ["您更想去哪里玩呢？比如日本、泰国、新加坡等。"]

    questions = questions[:3]
    lines = [f"{idx}. {question}" for idx, question in enumerate(questions, start=1)]
    return "为了给您推荐更合适的线路，想先确认几个信息：\n" + "\n".join(lines)


def _apply_suggested_profile_patch(profile: UserProfile, patch_payload: Any) -> UserProfile:
    if not isinstance(patch_payload, dict):
        return profile

    is_new_intent = bool(patch_payload.get("is_new_intent", False))
    user_profile_patch = patch_payload.get("user_profile")
    if not isinstance(user_profile_patch, dict):
        return profile

    merged = UserProfile().model_dump() if is_new_intent else profile.model_dump()
    for key in (
        "origin_city",
        "days_range",
        "budget_range",
        "depart_date_range",
        "people",
    ):
        value = user_profile_patch.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            merged[key] = text

    destinations = _normalize_text_list(user_profile_patch.get("destinations"))
    if destinations:
        merged["destinations"] = destinations

    style_prefs = _normalize_text_list(user_profile_patch.get("style_prefs"))
    if style_prefs:
        merged["style_prefs"] = style_prefs

    return UserProfile.model_validate(merged)


def _normalize_text_list(value: Any) -> list[str]:
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


def _build_rematch_confirmation_text(user_message: str, profile: UserProfile) -> str:
    has_new_conditions = _has_new_constraints(user_message)
    summary = _format_profile_summary(profile)

    if has_new_conditions:
        return f"已根据您刚才的新条件更新需求：{summary}。您还想再调整哪些条件吗？"
    return f"我先沿用您之前的需求：{summary}。这次需要我帮您调整哪些条件后再重新匹配？"


def _format_profile_summary(profile: UserProfile) -> str:
    parts: list[str] = []

    if profile.destinations:
        parts.append(f"目的地：{'/'.join(profile.destinations)}")
    if profile.days_range:
        parts.append(f"天数：{profile.days_range}")
    if profile.budget_range:
        parts.append(f"预算：{profile.budget_range}")
    if profile.depart_date_range:
        parts.append(f"出发时间：{profile.depart_date_range}")
    if profile.people:
        parts.append(f"人数：{profile.people}")
    if profile.style_prefs:
        parts.append(f"偏好：{'/'.join(profile.style_prefs)}")
    if profile.origin_city:
        parts.append(f"出发城市：{profile.origin_city}")

    if not parts:
        return "目前暂无明确条件"
    return "；".join(parts)


def _has_new_constraints(user_message: str) -> bool:
    text = user_message.strip()
    if not text:
        return False
    if text in _GENERIC_REMATCH_PHRASES:
        return False

    if re.search(r"\d+\s*(天|日|晚|人|万|w|k|元)", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\d{4}[-/.年]\d{1,2}", text):
        return True
    if re.search(r"\d{1,2}\s*月|\d{1,2}\s*号|下周|月底|五一|国庆|春节", text):
        return True
    if any(keyword in text for keyword in _STYLE_HINTS):
        return True
    if "去" in text or "到" in text or "从" in text:
        return True

    # If user says "换个..." and adds content, regard it as a condition change.
    generic_removed = text
    for phrase in _GENERIC_REMATCH_PHRASES:
        generic_removed = generic_removed.replace(phrase, "")
    return len(generic_removed.strip()) >= 2
