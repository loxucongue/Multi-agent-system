"""External information node (weather / flight / transport)."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState
from app.models.schemas import UserProfile
from app.services.container import services
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_WEATHER_KEYWORDS = ("天气", "气温", "温度", "下雨", "降雨", "台风")
_FLIGHT_KEYWORDS = ("航班", "机票", "起飞", "降落", "航司", "飞往")
_TRANSPORT_KEYWORDS = (
    "交通",
    "怎么去",
    "怎么走",
    "多远",
    "距离",
    "多久",
    "需要多久",
    "高铁",
    "动车",
    "火车",
    "大巴",
    "巴士",
    "地铁",
    "打车",
    "自驾",
)

_CITY_PAIR_PATTERNS = [
    re.compile(r"从\s*([\u4e00-\u9fa5A-Za-z]{1,12})\s*到\s*([\u4e00-\u9fa5A-Za-z]{1,12})"),
    re.compile(r"([\u4e00-\u9fa5A-Za-z]{1,12})\s*到\s*([\u4e00-\u9fa5A-Za-z]{1,12})"),
]

_WEATHER_CITY_PATTERN = re.compile(
    r"([\u4e00-\u9fa5A-Za-z]{1,12}?)(?:今天|明天|后天|本周末|周末|下周)?(?:的)?天气"
)
_DATE_PATTERN = re.compile(
    r"(\d{4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?|\d{1,2}月\d{1,2}日|今天|明天|后天|本周末|周末|下周)"
)


async def external_api_node(state: GraphState) -> dict[str, Any]:
    """Extract external-info params and call external workflow via input string."""

    user_message = str(state.get("current_user_message") or "").strip()
    trace_id = str(state.get("trace_id") or "-")
    session_id = str(state.get("session_id") or "")
    profile = _ensure_profile(state.get("user_profile"))

    info_type = _infer_info_type(user_message)
    params = _extract_params(user_message, profile, info_type)
    query = _build_external_query(info_type=info_type, params=params, user_message=user_message)

    workflow_service = _resolve_workflow_service()
    try:
        result = await workflow_service.run_external_info(
            query=query,
            trace_id=trace_id,
            session_id=session_id,
            info_type=info_type,
        )
        return {
            "tool_results": {
                "info_type": getattr(result, "info_type", info_type),
                "params": params,
                "query": query,
                "output": str(getattr(result, "output", "") or ""),
                "debug_url": getattr(result, "debug_url", None),
            }
        }
    except Exception as exc:
        _LOGGER.warning("external info call failed trace_id=%s info_type=%s query=%r error=%s", trace_id, info_type, query, exc)
        return {
            "tool_results": {
                "info_type": info_type,
                "params": params,
                "query": query,
                "output": "暂时无法获取该信息，请稍后再试。",
            }
        }


def _resolve_workflow_service() -> Any:
    try:
        return services.workflow_service
    except Exception as exc:
        raise RuntimeError("service container is not initialized for external api node") from exc


def _ensure_profile(value: Any) -> UserProfile:
    if isinstance(value, UserProfile):
        return value
    if isinstance(value, dict):
        return UserProfile.model_validate(value)
    return UserProfile()


def _infer_info_type(message: str) -> str:
    if _contains_any(message, _WEATHER_KEYWORDS):
        return "weather"
    # transport first for "从A到B多久/怎么去/多远"
    if _contains_any(message, _TRANSPORT_KEYWORDS) or any(p.search(message) for p in _CITY_PAIR_PATTERNS):
        return "transport"
    if _contains_any(message, _FLIGHT_KEYWORDS):
        return "flight"
    return "weather"


def _extract_params(message: str, profile: UserProfile, info_type: str) -> dict[str, Any]:
    date_value = _extract_date(message)
    origin_city, dest_city = _extract_city_pair(message)
    city = _extract_city_for_weather(message)

    if info_type in {"transport", "flight"}:
        if not origin_city and profile.origin_city:
            origin_city = profile.origin_city
        if not dest_city:
            dest_city = profile.destinations[0] if profile.destinations else None
        return {
            "origin_city": origin_city,
            "dest_city": dest_city,
            "date": date_value,
        }

    if not city:
        if dest_city:
            city = dest_city
        elif profile.destinations:
            city = profile.destinations[0]
        elif profile.origin_city:
            city = profile.origin_city
    return {"city": city, "date": date_value}


def _build_external_query(info_type: str, params: dict[str, Any], user_message: str) -> str:
    """Build workflow input string according to Coze external workflow convention."""

    date_value = str(params.get("date") or "").strip()

    if info_type == "weather":
        city = str(params.get("city") or "").strip()
        parts = [city, date_value, "天气"]
        query = " ".join([part for part in parts if part])
        return query or user_message

    if info_type == "flight":
        origin = str(params.get("origin_city") or "").strip()
        dest = str(params.get("dest_city") or "").strip()
        if origin and dest:
            parts = [f"{origin}到{dest}", date_value, "航班"]
            query = " ".join([part for part in parts if part])
            return query or user_message
        if dest:
            parts = [dest, date_value, "航班"]
            query = " ".join([part for part in parts if part])
            return query or user_message

    if info_type == "transport":
        origin = str(params.get("origin_city") or "").strip()
        dest = str(params.get("dest_city") or "").strip()
        if origin and dest:
            parts = [f"{origin}到{dest}", date_value, "交通"]
            query = " ".join([part for part in parts if part])
            return query or user_message
        if dest:
            parts = [dest, date_value, "交通"]
            query = " ".join([part for part in parts if part])
            return query or user_message

    return user_message


def _extract_city_pair(message: str) -> tuple[str | None, str | None]:
    for pattern in _CITY_PAIR_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        origin = _clean_city(match.group(1))
        dest = _clean_city(match.group(2))
        if origin or dest:
            return origin, dest
    return None, None


def _extract_city_for_weather(message: str) -> str | None:
    match = _WEATHER_CITY_PATTERN.search(message)
    if match:
        city = _clean_city(match.group(1))
        if city:
            return city
    token_match = re.search(r"([\u4e00-\u9fa5A-Za-z]{2,12})(?:今天|明天|后天|天气)", message)
    if token_match:
        city = _clean_city(token_match.group(1))
        if city:
            return city
    return None


def _extract_date(message: str) -> str | None:
    match = _DATE_PATTERN.search(message)
    if not match:
        return None
    return match.group(1).strip()


def _clean_city(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip(" ，。,.!?！？")
    if not text:
        return None
    for prefix in ("从", "去", "到", "在"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    for suffix in (
        "今天",
        "明天",
        "后天",
        "本周末",
        "周末",
        "下周",
        "天气",
        "航班",
        "机票",
        "交通",
        "距离",
        "多远",
        "多久",
        "怎么去",
    ):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    text = text.strip()
    return text or None


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)
