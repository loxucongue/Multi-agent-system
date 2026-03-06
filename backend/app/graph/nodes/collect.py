"""Collect requirement node for slot filling and follow-up questions."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState, STAGE_COLLECTING, STAGE_REMATCH_COLLECTING
from app.models.schemas import UserProfile
from app.prompts.requirement_collection import build_collect_prompt
from app.services.container import services
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
    """Collect destination and optional constraints, return GraphState patch."""

    profile = _ensure_profile(state.get("user_profile"))
    user_message = str(state.get("current_user_message") or "").strip()
    last_intent = str(state.get("last_intent") or "")
    slots_ready = len(profile.destinations) > 0
    in_rematch_collecting = state.get("stage") == STAGE_REMATCH_COLLECTING

    if in_rematch_collecting:
        if last_intent != "rematch":
            response_text = "好的，我基于刚才确认的条件继续为您匹配新的线路。"
            if slots_ready and not profile.days_range and not profile.budget_range:
                response_text = f"{response_text}\n{_SOFT_GUIDE}"
            return {
                "user_profile": profile,
                "slots_ready": slots_ready,
                "response_text": response_text,
                "stage": STAGE_COLLECTING,
            }

        response_text = _build_rematch_confirmation_text(user_message=user_message, profile=profile)
        if slots_ready and not profile.days_range and not profile.budget_range:
            response_text = f"{response_text}\n{_SOFT_GUIDE}"

        return {
            "user_profile": profile,
            "slots_ready": False,
            "response_text": response_text,
            "stage": STAGE_REMATCH_COLLECTING,
        }

    if slots_ready:
        response_text = "好的，已收到您的需求，我这就为您筛选更匹配的线路。"
        if not profile.days_range and not profile.budget_range:
            response_text = f"{response_text}\n{_SOFT_GUIDE}"

        return {
            "user_profile": profile,
            "slots_ready": True,
            "response_text": response_text,
        }

    missing_slots = _get_missing_slots(profile)
    llm_result = await _generate_collect_questions(
        user_message=user_message,
        profile=profile,
        missing_slots=missing_slots,
    )

    updated_profile = _apply_suggested_profile_patch(profile, llm_result.get("suggested_state_patch"))
    response_text = _format_questions(llm_result.get("questions"))

    return {
        "user_profile": updated_profile,
        "slots_ready": len(updated_profile.destinations) > 0,
        "response_text": response_text,
        "stage": STAGE_COLLECTING,
    }


def _ensure_profile(value: Any) -> UserProfile:
    if isinstance(value, UserProfile):
        return value
    if isinstance(value, dict):
        return UserProfile.model_validate(value)
    return UserProfile()


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
        if isinstance(result, dict):
            return result
    except Exception as exc:
        _LOGGER.warning(f"collect requirement llm failed, fallback to template questions: {exc}")
    finally:
        if should_close:
            await llm_client.aclose()

    return {
        "questions": ["您更想去哪里玩呢？比如日本、泰国、新加坡等。"],
        "suggested_state_patch": {},
        "slots_ready": False,
        "reasoning": "fallback",
    }


def _resolve_llm_client() -> tuple[LLMClient, bool]:
    try:
        return services.llm_client, False
    except Exception:
        return LLMClient(), True


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

    user_profile_patch = patch_payload.get("user_profile")
    if not isinstance(user_profile_patch, dict):
        return profile

    merged = profile.model_dump()
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
