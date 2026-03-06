"""Visa knowledge-base search node."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState
from app.models.schemas import UserProfile
from app.prompts.visa_query_rewrite import build_visa_query_rewrite_prompt
from app.prompts.visa_result_eval import build_visa_result_eval_prompt
from app.services.container import services
from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_DEFAULT_NATIONALITY = "中国大陆"
_DEST_STOPWORDS = {"办理", "咨询", "申请", "需要", "材料", "流程", "怎么办", "如何", "签证"}
_DOMESTIC_CITIES = {
    "北京",
    "上海",
    "广州",
    "深圳",
    "成都",
    "重庆",
    "杭州",
    "南京",
    "武汉",
    "西安",
    "长沙",
    "青岛",
    "大理",
    "丽江",
    "三亚",
    "厦门",
    "桂林",
    "拉萨",
    "哈尔滨",
    "苏州",
    "黄山",
    "张家界",
    "九寨沟",
    "敦煌",
    "香格里拉",
}
_MAX_ATTEMPTS = 3
_VISA_EVAL_SCHEMA: dict[str, Any] = {
    "name": "visa_result_eval",
    "schema": {
        "type": "object",
        "properties": {
            "relevant": {"type": "boolean"},
            "reasoning": {"type": "string"},
        },
        "required": ["relevant", "reasoning"],
        "additionalProperties": True,
    },
}

_NATIONALITY_KEYWORDS = {
    "中国大陆": ("中国大陆", "大陆护照", "内地护照"),
    "中国香港": ("香港护照",),
    "中国澳门": ("澳门护照",),
    "中国台湾": ("台湾护照",),
    "美国": ("美国护照",),
    "加拿大": ("加拿大护照",),
    "新加坡": ("新加坡护照",),
    "日本": ("日本护照",),
}


async def visa_kb_search_node(state: GraphState) -> dict[str, Any]:
    """Run visa KB search with an agentic retry loop."""

    user_message = str(state.get("current_user_message") or "").strip()
    trace_id = str(state.get("trace_id") or "-")
    session_id = str(state.get("session_id") or "")
    profile = _ensure_profile(state.get("user_profile"))
    history = _normalize_history(state.get("context_turns"))

    country = _extract_destination_country(user_message, profile)
    nationality = _extract_nationality(user_message)
    stay_days = (profile.days_range or "").strip() or None
    depart_date = (profile.depart_date_range or "").strip() or None

    if not country:
        ask_text = "请先告诉我您要办理哪个国家或地区的签证，我再帮您查询具体要求。"
        return {
            "response_text": ask_text,
            "tool_results": {
                "answer": ask_text,
                "sources": [],
            },
        }

    workflow_service = _resolve_workflow_service()
    llm_client, should_close = _resolve_llm_client()
    previous_query: str | None = None
    previous_result_summary: str | None = None

    try:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            query = await _generate_visa_query(
                llm_client=llm_client,
                user_message=user_message,
                history=history,
                country=country,
                nationality=nationality,
                stay_days=stay_days,
                depart_date=depart_date,
                attempt=attempt,
                previous_query=previous_query,
                previous_result_summary=previous_result_summary,
            )
            if not query:
                query = _build_visa_query(
                    country=country,
                    nationality=nationality,
                    stay_days=stay_days,
                    depart_date=depart_date,
                )

            _LOGGER.info("visa_kb_search trace_id=%s attempt=%s query=%r", trace_id, attempt, query)
            try:
                result = await workflow_service.run_visa_search(query=query, trace_id=trace_id, session_id=session_id)
            except Exception as exc:
                _LOGGER.warning("visa kb search failed trace_id=%s attempt=%s country=%s: %s", trace_id, attempt, country, exc)
                previous_query = query
                previous_result_summary = None
                continue

            answer = str(getattr(result, "answer", "") or "")
            sources = getattr(result, "sources", [])
            if not isinstance(sources, list):
                sources = []

            if not answer.strip():
                _LOGGER.info("visa_kb_search trace_id=%s attempt=%s empty answer", trace_id, attempt)
                previous_query = query
                previous_result_summary = None
                continue

            previous_result_summary = answer[:300]
            relevant, reasoning = await _evaluate_visa_result(
                llm_client=llm_client,
                user_message=user_message,
                country=country,
                query=query,
                answer=answer,
                sources=sources,
            )
            _LOGGER.info(
                "visa_kb_search trace_id=%s attempt=%s relevant=%s reasoning=%s",
                trace_id,
                attempt,
                relevant,
                reasoning,
            )
            if relevant:
                return {"tool_results": {"answer": answer, "sources": sources}}

            previous_query = query

        fallback_text = "未找到相关签证信息，请确认国家名称后重试。"
        return {
            "response_text": fallback_text,
            "tool_results": {
                "answer": fallback_text,
                "sources": [],
            },
        }
    finally:
        if should_close:
            await llm_client.aclose()


def _resolve_workflow_service() -> Any:
    try:
        return services.workflow_service
    except Exception as exc:
        raise RuntimeError("service container is not initialized for visa kb search node") from exc


def _resolve_llm_client() -> tuple[LLMClient, bool]:
    try:
        return services.llm_client, False
    except Exception:
        return LLMClient(), True


def _ensure_profile(value: Any) -> UserProfile:
    if isinstance(value, UserProfile):
        return value
    if isinstance(value, dict):
        return UserProfile.model_validate(value)
    return UserProfile()


def _extract_destination_country(user_message: str, profile: UserProfile) -> str | None:
    match = re.search(r"([\u4e00-\u9fa5A-Za-z]{1,12})签证", user_message)
    if match:
        text = _clean_country_text(match.group(1))
        if _is_overseas_destination_candidate(text):
            return text

    match = re.search(r"去([\u4e00-\u9fa5A-Za-z]{1,12})", user_message)
    if match:
        text = _clean_country_text(match.group(1))
        if _is_overseas_destination_candidate(text):
            return text

    for destination in profile.destinations:
        cleaned = _clean_country_text(str(destination))
        if _is_overseas_destination_candidate(cleaned):
            return cleaned

    return None


def _is_overseas_destination_candidate(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text in _DOMESTIC_CITIES:
        return False
    return True


def _clean_country_text(value: str) -> str:
    text = value.strip(" ，。,.!?！？")
    if not text:
        return ""

    prefixes = ("想办理", "想办", "办理", "申请", "咨询", "关于", "去", "办", "想")
    changed = True
    while changed and text:
        changed = False
        for token in prefixes:
            if text.startswith(token):
                text = text[len(token) :].strip()
                changed = True
                break

    if not text or text in _DEST_STOPWORDS:
        return ""
    return text


def _extract_nationality(user_message: str) -> str:
    explicit_match = re.search(
        r"(?:国籍|我是|持有)[^，。,.!?！？]{0,8}(中国大陆|中国香港|中国澳门|中国台湾|美国|加拿大|新加坡|日本)",
        user_message,
    )
    if explicit_match:
        return explicit_match.group(1)

    for normalized, keywords in _NATIONALITY_KEYWORDS.items():
        if any(keyword in user_message for keyword in keywords):
            return normalized

    if "国籍" in user_message and _DEFAULT_NATIONALITY not in user_message:
        match = re.search(r"国籍[是为:： ]*([\u4e00-\u9fa5A-Za-z]{1,12})", user_message)
        if match:
            value = match.group(1).strip()
            if value:
                return value

    return _DEFAULT_NATIONALITY


async def _generate_visa_query(
    llm_client: LLMClient,
    user_message: str,
    history: list[dict[str, str]],
    country: str,
    nationality: str,
    stay_days: str | None,
    depart_date: str | None,
    attempt: int,
    previous_query: str | None,
    previous_result_summary: str | None,
) -> str | None:
    try:
        messages = build_visa_query_rewrite_prompt(
            user_message=user_message,
            history=history,
            attempt=attempt,
            previous_query=previous_query,
            previous_result_summary=previous_result_summary,
        )
        content = await llm_client.chat(messages=messages, temperature=0.1, max_tokens=64)
        query = _normalize_rewritten_query(content)
        if query:
            return query
    except Exception as exc:
        _LOGGER.warning("visa query rewrite failed attempt=%s: %s", attempt, exc)
    return _build_visa_query(
        country=country,
        nationality=nationality,
        stay_days=stay_days,
        depart_date=depart_date,
    )


async def _evaluate_visa_result(
    llm_client: LLMClient,
    user_message: str,
    country: str,
    query: str,
    answer: str,
    sources: list[str],
) -> tuple[bool, str]:
    try:
        messages = build_visa_result_eval_prompt(
            user_message=user_message,
            country=country,
            query=query,
            answer=answer,
            sources=sources,
        )
        result = await llm_client.chat_json(messages=messages, json_schema=_VISA_EVAL_SCHEMA, temperature=0.1)
        relevant = bool(result.get("relevant", False))
        reasoning = str(result.get("reasoning") or "").strip() or "llm_eval"
        return relevant, reasoning
    except Exception as exc:
        fallback_relevant = bool(answer.strip()) and (country in answer or not country)
        return fallback_relevant, f"fallback_eval:{exc}"


def _normalize_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        user = str(item.get("user") or "").strip()
        assistant = str(item.get("assistant") or "").strip()
        if not user and not assistant:
            continue
        normalized.append({"user": user, "assistant": assistant})
    return normalized


def _normalize_rewritten_query(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:text)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.replace("\r", "\n").strip()
    if "\n" in text:
        text = text.splitlines()[0].strip()
    text = text.strip("\"' ")
    return text or None


def _build_visa_query(
    country: str,
    nationality: str,
    stay_days: str | None,
    depart_date: str | None,
) -> str:
    parts = [
        f"目的地国家：{country}",
        f"国籍：{nationality}",
    ]
    if stay_days:
        parts.append(f"停留天数：{stay_days}")
    if depart_date:
        parts.append(f"出发日期：{depart_date}")
    parts.append("请给出签证材料、办理周期、注意事项。")
    return "；".join(parts)
