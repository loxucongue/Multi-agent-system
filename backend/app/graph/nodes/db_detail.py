"""Route DB detail enrichment node."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.services.container import services
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)


async def route_db_detail_node(state: GraphState) -> dict[str, Any]:
    """Load route details/prices/schedules for candidate route ids from MySQL."""

    candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))
    active_route_id = _to_int_or_none(state.get("active_route_id"))
    trace_id = str(state.get("trace_id") or "-")
    existing_tool_results = state.get("tool_results")
    merged_tool_results = dict(existing_tool_results) if isinstance(existing_tool_results, dict) else {}

    route_service = _resolve_route_service()
    batch_rows = await route_service.get_routes_batch(candidate_route_ids) if candidate_route_ids else []

    details_by_id: dict[int, dict[str, Any]] = {}
    for row in batch_rows:
        payload = row.model_dump() if hasattr(row, "model_dump") else dict(row)
        route_id = _to_int_or_none(payload.get("id"))
        if route_id is None:
            continue
        details_by_id[route_id] = payload

    missing_route_ids = [rid for rid in candidate_route_ids if rid not in details_by_id]
    for missing_id in missing_route_ids:
        _LOGGER.warning(f"route detail missing in mysql trace_id={trace_id} route_id={missing_id}")

    filtered_candidate_ids = [rid for rid in candidate_route_ids if rid in details_by_id]
    if active_route_id in missing_route_ids:
        active_route_id = filtered_candidate_ids[0] if filtered_candidate_ids else None

    ordered_details = [details_by_id[rid] for rid in filtered_candidate_ids]
    route_prices = [{"route_id": item["id"], "pricing": item.get("pricing")} for item in ordered_details]
    route_schedules = [{"route_id": item["id"], "schedule": item.get("schedule")} for item in ordered_details]

    merged_tool_results.update(
        {
            "route_details": ordered_details,
            "route_prices": route_prices,
            "route_schedules": route_schedules,
        }
    )

    return {
        "candidate_route_ids": filtered_candidate_ids,
        "active_route_id": active_route_id,
        "tool_results": merged_tool_results,
    }


def _resolve_route_service() -> Any:
    try:
        return services.route_service
    except Exception as exc:
        raise RuntimeError("service container is not initialized for route db detail node") from exc


def _normalize_int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []

    normalized: list[int] = []
    for value in values:
        parsed = _to_int_or_none(value)
        if parsed is not None:
            normalized.append(parsed)
    return normalized


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
