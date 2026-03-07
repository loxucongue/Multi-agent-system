"""Route follow-up node."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.graph.utils import normalize_int_list as _normalize_int_list_shared
from app.graph.utils import to_int_or_none as _to_int_or_none_shared
from app.services.container import services
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)


async def route_followup_node(state: GraphState) -> dict[str, Any]:
    """Fetch detail for active/target route or ask user to choose a candidate."""

    followup_count = _to_int_or_zero(state.get("followup_count")) + 1
    candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))

    target_route_id = _to_int_or_none(state.get("target_route_id"))
    active_route_id = _to_int_or_none(state.get("active_route_id"))
    selected_route_id = target_route_id if target_route_id is not None else active_route_id

    result: dict[str, Any] = {
        "followup_count": followup_count,
        "target_route_id": None,  # clear after this turn to avoid stale selection
    }

    if selected_route_id is not None:
        route_service = _resolve_route_service()
        detail = await route_service.get_route_detail(selected_route_id)
        if detail is not None:
            payload = detail.model_dump() if hasattr(detail, "model_dump") else dict(detail)
            result["tool_results"] = {
                "route_detail": payload,
                "selected_route_id": selected_route_id,
            }
            return result

        _LOGGER.warning(f"followup route detail not found route_id={selected_route_id}")

    if candidate_route_ids:
        result["response_text"] = "您想了解哪一条线路的详情？可以点选候选线路，我再为您展开说明。"
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

    result["response_text"] = "当前没有可追问的线路，我先根据您的需求重新为您推荐几条方案。"
    result["tool_results"] = {"need_rematch": True}
    return result


def _resolve_route_service() -> Any:
    try:
        return services.route_service
    except Exception as exc:
        raise RuntimeError("service container is not initialized for route followup node") from exc


def _normalize_int_list(values: Any) -> list[int]:
    return _normalize_int_list_shared(values)


def _to_int_or_none(value: Any) -> int | None:
    return _to_int_or_none_shared(value)


def _to_int_or_zero(value: Any) -> int:
    parsed = _to_int_or_none(value)
    return parsed if parsed is not None else 0
