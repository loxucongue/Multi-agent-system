"""Compare API endpoints for route comparison payload generation."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status

from app.models.schemas import (
    CompareAIAnalysisResponse,
    CompareData,
    CompareNextSchedule,
    ComparePriceRange,
    CompareRequest,
    CompareRouteItem,
    RouteBatchItem,
)
from app.services.container import services

router = APIRouter()

_MAX_COMPARE_ROUTES = 5
_CROWD_KEYWORDS = ("亲子", "老人", "老年", "蜜月", "情侣", "家庭", "学生", "闺蜜", "朋友", "商务")


@router.post("/{session_id}/compare", response_model=CompareData)
async def compare_routes(
    session_id: str,
    req: CompareRequest | None = Body(default=None),
) -> CompareData:
    """Build route comparison payload from explicit ids or session candidates."""

    await services.initialize()

    if not await services.session_service.is_session_valid(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    route_ids = _normalize_route_ids(req.route_ids if req else None)
    if not route_ids:
        state = await services.session_service.get_session_state(session_id)
        if state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        route_ids = _normalize_route_ids(state.candidate_route_ids)

    if len(route_ids) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少需要2条线路进行对比")
    if len(route_ids) > _MAX_COMPARE_ROUTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="最多支持5条线路对比")

    batch_items = await _get_batch_items(route_ids)
    items_by_id = {item.id: item for item in batch_items}

    compare_items: list[CompareRouteItem] = []
    for route_id in route_ids:
        item = items_by_id.get(route_id)
        if item is None:
            continue
        compare_items.append(_to_compare_item(item))

    if len(compare_items) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少需要2条线路进行对比")

    # Keep persisted session state aligned with compare action for next-turn routing.
    try:
        await services.session_service.update_session_state(
            session_id,
            {
                "stage": "comparing",
                "last_intent": "compare",
            },
        )
    except Exception:
        # Do not fail compare payload response when state sync fails.
        pass

    return CompareData(routes=compare_items)


@router.post("/{session_id}/compare/ai-analysis", response_model=CompareAIAnalysisResponse)
async def compare_routes_ai_analysis(
    session_id: str,
    req: CompareRequest | None = Body(default=None),
) -> CompareAIAnalysisResponse:
    """Generate AI analysis using two full route contents."""

    await services.initialize()

    if not await services.session_service.is_session_valid(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    route_ids = _normalize_route_ids(req.route_ids if req else None)
    if not route_ids:
        state = await services.session_service.get_session_state(session_id)
        if state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        route_ids = _normalize_route_ids(state.candidate_route_ids)

    if len(route_ids) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少需要2条线路进行 AI 对比分析")

    selected_two = route_ids[:2]
    batch_items = await _get_batch_items(selected_two)
    item_by_id = {item.id: item for item in batch_items}
    ordered_items = [item_by_id.get(route_id) for route_id in selected_two]
    route_items = [item for item in ordered_items if item is not None]

    if len(route_items) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅找到1条有效线路，无法进行 AI 对比分析")

    prompt = _build_ai_compare_route_prompt(route_items[0], route_items[1])
    fallback_text = _build_ai_compare_route_fallback(route_items[0], route_items[1])

    try:
        llm_client = services.llm_client
    except Exception:
        return CompareAIAnalysisResponse(analysis=fallback_text)

    try:
        analysis = await llm_client.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是资深旅游顾问。请仅基于给定的两条路线内容做对比分析，输出中文结论："
                        "1) 核心差异（行程节奏/亮点/费用风险）；"
                        "2) 各自优缺点；"
                        "3) 分人群推荐建议（亲子/老人/首次出境/预算敏感）。"
                        "不要编造不存在的数据。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=900,
        )
        normalized = str(analysis or "").strip()
        return CompareAIAnalysisResponse(analysis=normalized or fallback_text)
    except Exception:
        return CompareAIAnalysisResponse(analysis=fallback_text)


async def _get_batch_items(route_ids: list[int]) -> list[RouteBatchItem]:
    """Fetch route batch details from route service."""

    return await services.route_service.get_routes_batch(route_ids)


def _to_compare_item(item: RouteBatchItem) -> CompareRouteItem:
    """Map RouteBatchItem to CompareRouteItem expected by frontend."""

    tags = _to_text_list(item.tags)
    days = _infer_days(item.itinerary_json, item.base_info)
    highlights = _infer_highlights(item.highlights, tags)
    itinerary_style = _infer_itinerary_style(tags)
    included_summary = _truncate_text(item.included, 100)
    notice_summary = _truncate_text(item.notice, 100)
    next_date = _extract_next_schedule_date(item.schedule.schedules_json if item.schedule else None)

    return CompareRouteItem(
        route_id=item.id,
        name=item.name,
        days=days,
        highlights=highlights,
        itinerary_style=itinerary_style,
        included_summary=included_summary,
        notice_summary=notice_summary,
        age_limit=item.age_limit,
        certificate_limit=item.certificate_limit,
        price_range=ComparePriceRange(
            min=float(item.pricing.price_min) if item.pricing else 0.0,
            max=float(item.pricing.price_max) if item.pricing else 0.0,
            currency=item.pricing.currency if item.pricing else "CNY",
            updated_at=_to_iso(item.pricing.price_updated_at if item.pricing else None),
        ),
        next_schedule=CompareNextSchedule(
            date=next_date,
            updated_at=_to_iso(item.schedule.schedule_updated_at if item.schedule else None),
        ),
        suitable_for=_extract_suitable_for(tags),
    )


def _normalize_route_ids(route_ids: list[int] | None) -> list[int]:
    """Normalize route id list to unique ordered ints."""

    if not route_ids:
        return []
    deduped: list[int] = []
    seen: set[int] = set()
    for route_id in route_ids:
        try:
            value = int(route_id)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _build_ai_compare_prompt(routes: list[CompareRouteItem]) -> str:
    lines: list[str] = ["请基于以下路线对比数据给出分析建议："]
    for idx, item in enumerate(routes, start=1):
        lines.append(
            (
                f"{idx}. {item.name}\n"
                f"- 天数: {item.days}\n"
                f"- 行程风格: {item.itinerary_style}\n"
                f"- 价格: {item.price_range.min}~{item.price_range.max} {item.price_range.currency}\n"
                f"- 最近团期: {item.next_schedule.date or '暂无'}\n"
                f"- 亮点: {', '.join(item.highlights) if item.highlights else '暂无'}\n"
                f"- 适合人群: {', '.join(item.suitable_for) if item.suitable_for else '暂无'}\n"
                f"- 费用包含摘要: {item.included_summary or '暂无'}\n"
                f"- 注意事项摘要: {item.notice_summary or '暂无'}"
            )
        )
    lines.append("请输出：核心差异、推荐顺序、适合谁选。")
    return "\n\n".join(lines)


def _build_ai_compare_fallback(routes: list[CompareRouteItem]) -> str:
    if not routes:
        return "当前没有可分析的对比数据。"

    names = [item.name for item in routes if item.name]
    if len(names) == 1:
        return f"目前仅有 {names[0]}，建议再选择至少一条线路进行对比分析。"

    return (
        f"已完成基础对比：{', '.join(names)}。\n"
        "建议优先看三点：预算区间、行程风格、最近团期；"
        "若您告诉我偏好（预算/节奏/人群），我可以给出更明确推荐。"
    )


def _build_ai_compare_route_prompt(route_a: RouteBatchItem, route_b: RouteBatchItem) -> str:
    return "\n\n".join(
        [
            "请对比以下两条路线：",
            _serialize_route_for_ai(route_a, "路线A"),
            _serialize_route_for_ai(route_b, "路线B"),
            "请按以下结构输出：",
            "一、核心差异",
            "二、优缺点对比",
            "三、适合人群建议",
            "四、若用户预算有限该选哪条",
        ]
    )


def _build_ai_compare_route_fallback(route_a: RouteBatchItem, route_b: RouteBatchItem) -> str:
    price_a = _format_price_range(route_a)
    price_b = _format_price_range(route_b)
    return (
        f"已对比两条路线：{route_a.name} 与 {route_b.name}。\n"
        f"- {route_a.name} 价格区间：{price_a}\n"
        f"- {route_b.name} 价格区间：{price_b}\n"
        "建议优先比较：行程节奏、费用包含范围、注意事项风险，再结合您的预算和出行人群选择。"
    )


def _serialize_route_for_ai(item: RouteBatchItem, title: str) -> str:
    tags = "、".join(_to_text_list(item.tags)) or "暂无"
    highlights = str(item.highlights or "").strip() or "暂无"
    summary = str(item.summary or "").strip() or "暂无"
    base_info = str(item.base_info or "").strip() or "暂无"
    included = _truncate_text(item.included, 300) or "暂无"
    notice = _truncate_text(item.notice, 300) or "暂无"
    features = str(item.features or "").strip() or "暂无"
    cost_excluded = _truncate_text(item.cost_excluded, 300) or "暂无"
    age_limit = str(item.age_limit or "").strip() or "暂无"
    certificate_limit = str(item.certificate_limit or "").strip() or "暂无"
    itinerary = _truncate_text(_stringify_json_like(item.itinerary_json), 500) or "暂无"
    schedule = _truncate_text(_stringify_json_like(item.schedule.schedules_json if item.schedule else None), 300) or "暂无"
    return (
        f"{title}\n"
        f"- 名称: {item.name}\n"
        f"- 标签: {tags}\n"
        f"- 摘要: {summary}\n"
        f"- 亮点: {highlights}\n"
        f"- 基础信息: {base_info}\n"
        f"- 行程: {itinerary}\n"
        f"- 费用包含: {included}\n"
        f"- 注意事项: {notice}\n"
        f"- 线路特色: {features}\n"
        f"- 费用不含: {cost_excluded}\n"
        f"- 年龄限制: {age_limit}\n"
        f"- 证件要求: {certificate_limit}\n"
        f"- 价格区间: {_format_price_range(item)}\n"
        f"- 团期信息: {schedule}"
    )


def _format_price_range(item: RouteBatchItem) -> str:
    pricing = item.pricing
    if pricing is None:
        return "暂无"
    return f"{pricing.price_min}~{pricing.price_max} {pricing.currency}"


def _stringify_json_like(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "；".join(_stringify_json_like(v) for v in value)
    if isinstance(value, dict):
        parts: list[str] = []
        for key, nested in value.items():
            parts.append(f"{key}:{_stringify_json_like(nested)}")
        return "；".join(parts)
    return str(value)


def _to_text_list(value: Any) -> list[str]:
    """Convert tag-like value to string list."""

    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _infer_days(itinerary_json: Any, base_info: str) -> int:
    """Infer route days from itinerary structure or base info text."""

    if isinstance(itinerary_json, list) and itinerary_json:
        return len(itinerary_json)
    if isinstance(itinerary_json, dict):
        days_field = itinerary_json.get("days")
        if isinstance(days_field, list) and days_field:
            return len(days_field)
        if isinstance(days_field, int) and days_field > 0:
            return days_field

    match = re.search(r"(\d+)\s*天", base_info or "")
    if match:
        return int(match.group(1))
    return 0


def _infer_highlights(raw_highlights: str, tags: list[str]) -> list[str]:
    """Split highlights text first; fallback to tags."""

    if raw_highlights and raw_highlights.strip():
        parts = [
            part.strip()
            for part in re.split(r"[，,；;、\n|]+", raw_highlights)
            if part.strip()
        ]
        if parts:
            return parts[:3]
    return tags[:3]


def _infer_itinerary_style(tags: list[str]) -> str:
    """Infer itinerary style from tags with a deterministic fallback."""

    tags_text = " ".join(tags)
    if any(keyword in tags_text for keyword in ("深度", "深度游", "经典打卡", "打卡")):
        return "深度游"
    if any(keyword in tags_text for keyword in ("自由", "自由行", "休闲")):
        return "自由行"
    return "经典"


def _truncate_text(text: str | None, limit: int) -> str:
    """Trim and truncate text to a maximum length."""

    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit]


def _extract_next_schedule_date(schedules_json: Any) -> str | None:
    """Extract nearest non-expired schedule date from arbitrary JSON."""

    candidates: list[date] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                walk(nested)
            return
        if isinstance(value, list):
            for nested in value:
                walk(nested)
            return
        if isinstance(value, str):
            for match in re.findall(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value):
                try:
                    candidates.append(date(int(match[0]), int(match[1]), int(match[2])))
                except ValueError:
                    continue

    walk(schedules_json)
    if not candidates:
        return None

    today = date.today()
    future_or_today = sorted(d for d in set(candidates) if d >= today)
    if future_or_today:
        return future_or_today[0].isoformat()
    return sorted(set(candidates))[0].isoformat()


def _extract_suitable_for(tags: list[str]) -> list[str]:
    """Extract crowd-oriented tags for suitability display."""

    result: list[str] = []
    for keyword in _CROWD_KEYWORDS:
        if any(keyword in tag for tag in tags):
            result.append(keyword)
    return result


def _to_iso(value: datetime | Any | None) -> str:
    """Serialize datetime-like value to ISO string."""

    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return ""
    return str(value)
