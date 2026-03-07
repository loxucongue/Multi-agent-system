"""Price and schedule query node."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.graph.utils import normalize_int_list as _normalize_int_list_shared
from app.graph.utils import to_int_or_none as _to_int_or_none_shared
from app.services.container import services


async def price_schedule_node(state: GraphState) -> dict[str, Any]:
    """Query selected route price/schedule and return normalized tool payload."""

    candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))
    target_route_id = _to_int_or_none(state.get("target_route_id"))
    active_route_id = _to_int_or_none(state.get("active_route_id"))
    selected_route_id = target_route_id if target_route_id is not None else active_route_id

    result: dict[str, Any] = {"target_route_id": None}

    if selected_route_id is None:
        if candidate_route_ids:
            result["response_text"] = "请先选择一条线路（您可以点击候选列表中的线路），我再为您查询价格和团期。"
            result["ui_actions"] = [
                {
                    "action": "show_candidates",
                    "payload": {"route_ids": candidate_route_ids},
                }
            ]
            result["tool_results"] = {
                "need_route_selection": True,
                "candidate_route_ids": candidate_route_ids,
            }
            return result

        result["response_text"] = "当前没有可查询的线路，请先让我为您推荐路线。"
        result["tool_results"] = {"error": "missing_active_route_id"}
        return result

    route_service = _resolve_route_service()
    price_schedule = await route_service.get_route_price_schedule(selected_route_id)
    if price_schedule is None:
        result["response_text"] = "该线路暂未查询到价格和团期信息，您可以先看其他线路或稍后再试。"
        result["tool_results"] = {
            "route_id": selected_route_id,
            "error": "price_schedule_not_found",
        }
        return result

    payload = price_schedule.model_dump() if hasattr(price_schedule, "model_dump") else dict(price_schedule)
    pricing = payload.get("pricing") if isinstance(payload, dict) else None
    schedule = payload.get("schedule") if isinstance(payload, dict) else None

    result["tool_results"] = {
        "route_id": selected_route_id,
        "price": pricing,
        "schedule": schedule,
        "price_updated_at": _safe_get(pricing, "price_updated_at"),
        "schedule_updated_at": _safe_get(schedule, "schedule_updated_at"),
    }
    return result


def _resolve_route_service() -> Any:
    try:
        return services.route_service
    except Exception as exc:
        raise RuntimeError("service container is not initialized for price schedule node") from exc


def _normalize_int_list(values: Any) -> list[int]:
    return _normalize_int_list_shared(values)


def _to_int_or_none(value: Any) -> int | None:
    return _to_int_or_none_shared(value)


def _safe_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None
