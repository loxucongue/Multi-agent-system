"""Visa knowledge-base search node."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState
from app.models.schemas import UserProfile
from app.prompts.visa_query_rewrite import build_visa_query_rewrite_prompt
from app.services.container import services
from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_DEFAULT_NATIONALITY = "中国大陆"
_DEST_STOPWORDS = {"办理", "咨询", "申请", "需要", "材料", "流程", "怎么办", "如何", "签证"}

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
    """Run visa KB search and return normalized answer/sources payload."""

    user_message = str(state.get("current_user_message") or "").strip()
    trace_id = str(state.get("trace_id") or "-")
    session_id = str(state.get("session_id") or "")
    profile = _ensure_profile(state.get("user_profile"))

    country = _extract_destination_country(user_message, profile)
    nationality = _extract_nationality(user_message)
    stay_days = (profile.days_range or "").strip() or None
    depart_date = (profile.depart_date_range or "").strip() or None

    if not country:
        return {
            "tool_results": {
                "answer": "请先告诉我要办理哪个国家的签证，我再为您查询具体要求。",
                "sources": [],
            }
        }

    query = await _rewrite_visa_query(user_message, state) or _build_visa_query(
        country=country,
        nationality=nationality,
        stay_days=stay_days,
        depart_date=depart_date,
    )

    workflow_service = _resolve_workflow_service()
    try:
        result = await workflow_service.run_visa_search(query=query, trace_id=trace_id, session_id=session_id)
        answer = str(getattr(result, "answer", "") or "")
        sources = getattr(result, "sources", [])
        if not isinstance(sources, list):
            sources = []
        return {"tool_results": {"answer": answer, "sources": sources}}
    except Exception as exc:
        _LOGGER.warning(f"visa kb search failed trace_id={trace_id} country={country}: {exc}")
        return {
            "tool_results": {
                "answer": "签证信息查询暂时不可用，请稍后重试。",
                "sources": [],
            }
        }


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
    # 1) from user message: "日本签证" / "去日本签证"
    match = re.search(r"([\u4e00-\u9fa5A-Za-z]{1,12})签证", user_message)
    if match:
        text = _clean_country_text(match.group(1))
        if text:
            return text

    match = re.search(r"去([\u4e00-\u9fa5A-Za-z]{1,12})", user_message)
    if match:
        text = _clean_country_text(match.group(1))
        if text:
            return text

    # 2) from profile destinations
    for destination in profile.destinations:
        cleaned = _clean_country_text(str(destination))
        if cleaned:
            return cleaned

    return None


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
    text = text.strip()

    if not text or text in _DEST_STOPWORDS:
        return ""
    return text


def _extract_nationality(user_message: str) -> str:
    explicit_match = re.search(
        r"(?:国籍|我是|持|拿|用)[^，。,.!?]{0,8}(中国大陆|中国香港|中国澳门|中国台湾|美国|加拿大|新加坡|日本)",
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


async def _rewrite_visa_query(user_message: str, state: GraphState) -> str | None:
    history = _normalize_history(state.get("context_turns"))
    llm_client, should_close = _resolve_llm_client()
    try:
        messages = build_visa_query_rewrite_prompt(user_message=user_message, history=history)
        content = await llm_client.chat(messages=messages, temperature=0.1, max_tokens=64)
        query = _normalize_rewritten_query(content)
        if query:
            return query
    except Exception as exc:
        _LOGGER.warning(f"visa query rewrite failed: {exc}")
    finally:
        if should_close:
            await llm_client.aclose()
    return None


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
    text = text.strip("“”\"' ")
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
