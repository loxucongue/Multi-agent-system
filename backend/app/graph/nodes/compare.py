"""Route comparison node."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any

from app.graph.state import GraphState
from app.graph.utils import normalize_int_list as _normalize_int_list_shared
from app.models.schemas import (
    CompareData,
    CompareNextSchedule,
    ComparePriceRange,
    CompareRouteItem,
)
from app.services.container import services
from app.services.llm_client import LLMClient
from app.services.prompt_defaults import DEFAULT_PROMPTS
from app.services.prompt_service import get_active_prompt
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)

_CROWD_TAGS = {
    "亲子",
    "老人",
    "老年",
    "蜜月",
    "情侣",
    "家庭",
    "学生",
    "闺蜜",
    "朋友",
    "商务",
}

_COMPACT_TAGS = {"深度", "紧凑"}
_RELAXED_TAGS = {"轻松", "休闲"}
_DEFAULT_ITINERARY_STYLE = "自由时间充裕"

_STYLE_OUTPUT_SCHEMA: dict[str, Any] = {
    "name": "itinerary_style",
    "schema": {
        "type": "object",
        "properties": {
            "itinerary_style": {
                "type": "string",
                "enum": ["紧凑", "轻松", "自由时间充裕"],
            }
        },
        "required": ["itinerary_style"],
        "additionalProperties": False,
    },
}


async def compare_node(state: GraphState) -> dict[str, Any]:
    """Build compare payload and trigger compare drawer UI action."""

    route_ids = _resolve_route_ids(state)
    if len(route_ids) < 2:
        return {
            "tool_results": {
                "error": "compare_requires_at_least_two_routes",
                "route_ids": route_ids,
            },
            "response_text": "至少需要两条线路才能进行对比，请先选择两条及以上线路。",
        }

    route_service, llm_client = _resolve_services()
    rows = await route_service.get_routes_batch(route_ids)
    if not rows:
        return {
            "tool_results": {"error": "compare_routes_not_found", "route_ids": route_ids},
            "response_text": "暂未查询到可对比的线路数据，请稍后重试。",
        }

    rows_by_id: dict[int, Any] = {int(row.id): row for row in rows if getattr(row, "id", None) is not None}
    ordered_rows = [rows_by_id[rid] for rid in route_ids if rid in rows_by_id]

    compare_items = list(
        await asyncio.gather(*[_build_compare_item(row, llm_client) for row in ordered_rows])
    )

    compare_data = CompareData(routes=compare_items)
    payload = compare_data.model_dump(mode="json")
    return {
        "tool_results": {"compare_data": payload},
        "ui_actions": [{"action": "show_compare", "payload": payload}],
    }


def _resolve_route_ids(state: GraphState) -> list[int]:
    candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))

    explicit_route_ids = _normalize_int_list(state.get("route_ids"))
    if not explicit_route_ids:
        tool_results = state.get("tool_results")
        if isinstance(tool_results, dict):
            explicit_route_ids = _normalize_int_list(tool_results.get("route_ids"))
    if explicit_route_ids:
        return _dedupe_keep_order(explicit_route_ids)

    extracted_entities = state.get("extracted_entities")
    route_indices: list[int] = []
    if isinstance(extracted_entities, dict):
        route_indices = _normalize_int_list(extracted_entities.get("route_indices"))
        if not route_indices and isinstance(extracted_entities.get("compare"), dict):
            route_indices = _normalize_int_list(extracted_entities["compare"].get("route_indices"))

    if route_indices and candidate_route_ids:
        mapped: list[int] = []
        for idx in route_indices:
            if 1 <= idx <= len(candidate_route_ids):
                mapped.append(candidate_route_ids[idx - 1])
        mapped = _dedupe_keep_order(mapped)
        if mapped:
            return mapped

    return _dedupe_keep_order(candidate_route_ids)


def _resolve_services() -> tuple[Any, LLMClient]:
    try:
        return services.route_service, services.llm_client
    except Exception as exc:
        raise RuntimeError("service container is not initialized for compare node") from exc


async def _build_compare_item(row: Any, llm_client: LLMClient) -> CompareRouteItem:
    tags = _as_text_list(getattr(row, "tags", []))
    itinerary_json = getattr(row, "itinerary_json", None)
    highlights = _split_highlights(str(getattr(row, "highlights", "") or ""))

    itinerary_style = _derive_itinerary_style(tags=tags, itinerary_json=itinerary_json)
    if itinerary_style is None:
        itinerary_style = await _infer_itinerary_style_with_llm(
            llm_client=llm_client,
            summary=str(getattr(row, "summary", "") or ""),
            highlights=highlights,
        )

    days = _infer_days(itinerary_json=itinerary_json, base_info=str(getattr(row, "base_info", "") or ""))
    included_summary = _summarize_text(str(getattr(row, "included", "") or ""), 100)
    notice_summary = _summarize_text(str(getattr(row, "notice", "") or ""), 100)

    pricing = getattr(row, "pricing", None)
    schedule = getattr(row, "schedule", None)

    return CompareRouteItem(
        route_id=int(getattr(row, "id")),
        name=str(getattr(row, "name", "") or ""),
        days=days,
        highlights=highlights[:3],
        itinerary_style=itinerary_style,
        included_summary=included_summary,
        notice_summary=notice_summary,
        price_range=ComparePriceRange(
            min=_to_float(getattr(pricing, "price_min", None)),
            max=_to_float(getattr(pricing, "price_max", None)),
            currency=str(getattr(pricing, "currency", "CNY") or "CNY"),
            updated_at=_to_iso_str(getattr(pricing, "price_updated_at", None)),
        ),
        next_schedule=CompareNextSchedule(
            date=_extract_next_schedule_date(getattr(schedule, "schedules_json", None)),
            updated_at=_to_iso_str(getattr(schedule, "schedule_updated_at", None)),
        ),
        suitable_for=_extract_suitable_for(tags),
    )


def _derive_itinerary_style(tags: list[str], itinerary_json: Any) -> str | None:
    tags_text = " ".join(tags)
    if any(token in tags_text for token in _RELAXED_TAGS):
        return "轻松"
    if any(token in tags_text for token in _COMPACT_TAGS):
        return "紧凑"

    avg_spots = _avg_spots_per_day(itinerary_json)
    if avg_spots is None:
        return None
    if avg_spots <= 2:
        return "轻松"
    if avg_spots >= 4:
        return "紧凑"
    return _DEFAULT_ITINERARY_STYLE


def _avg_spots_per_day(itinerary_json: Any) -> float | None:
    if not isinstance(itinerary_json, dict):
        return None
    days = itinerary_json.get("days")
    if not isinstance(days, list) or not days:
        return None

    counts: list[int] = []
    for day in days:
        if not isinstance(day, dict):
            continue
        count = _count_spots_in_day(day)
        if count is not None:
            counts.append(count)
    if not counts:
        return None
    return sum(counts) / len(counts)


def _count_spots_in_day(day: dict[str, Any]) -> int | None:
    for key in ("spots", "attractions", "activities", "schedule", "items", "poi"):
        value = day.get(key)
        if isinstance(value, list):
            return len(value)

    text_blocks: list[str] = []
    for key in ("title", "desc", "description", "content"):
        value = day.get(key)
        if isinstance(value, str):
            text_blocks.append(value)
    if not text_blocks:
        return None
    merged = " ".join(text_blocks)
    chunks = [part for part in re.split(r"[，、；;。]", merged) if part.strip()]
    return len(chunks) if chunks else None


async def _infer_itinerary_style_with_llm(llm_client: LLMClient, summary: str, highlights: list[str]) -> str:
    prompt = (await get_active_prompt("compare_style")) or DEFAULT_PROMPTS["compare_style"]
    user_text = f"摘要：{summary}\n亮点：{'；'.join(highlights)}"
    try:
        result = await llm_client.chat_json(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_text},
            ],
            json_schema=_STYLE_OUTPUT_SCHEMA,
            temperature=0.1,
        )
        style = str(result.get("itinerary_style", "")).strip()
        if style in {"紧凑", "轻松", "自由时间充裕"}:
            return style
    except Exception as exc:
        _LOGGER.warning("compare itinerary style llm fallback failed: %s", exc)
    return _DEFAULT_ITINERARY_STYLE


def _infer_days(itinerary_json: Any, base_info: str) -> int:
    if isinstance(itinerary_json, dict):
        days = itinerary_json.get("days")
        if isinstance(days, list) and days:
            return len(days)
    match = re.search(r"(\d+)\s*天", base_info)
    if match:
        return int(match.group(1))
    return 0


def _split_highlights(raw: str) -> list[str]:
    if not raw.strip():
        return []
    parts = [part.strip() for part in re.split(r"[，、；;\n。]", raw) if part.strip()]
    return parts[:3]


def _summarize_text(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit]


def _extract_suitable_for(tags: list[str]) -> list[str]:
    result: list[str] = []
    for tag in tags:
        for crowd in _CROWD_TAGS:
            if crowd in tag and crowd not in result:
                result.append(crowd)
    return result


def _extract_next_schedule_date(schedules_json: Any) -> str | None:
    candidates: list[str] = []

    def collect_dates(value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, (dict, list)):
                    collect_dates(v)
                elif isinstance(v, str):
                    if k.lower() in {"date", "start_date", "departure_date"} and _is_date_str(v):
                        candidates.append(v[:10])
                    elif _is_date_str(v):
                        candidates.append(v[:10])
        elif isinstance(value, list):
            for item in value:
                collect_dates(item)

    collect_dates(schedules_json)
    if not candidates:
        return None
    return sorted(set(candidates))[0]


def _is_date_str(value: str) -> bool:
    return bool(re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value))


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_iso_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _normalize_int_list(values: Any) -> list[int]:
    return _normalize_int_list_shared(values)


def _dedupe_keep_order(values: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
