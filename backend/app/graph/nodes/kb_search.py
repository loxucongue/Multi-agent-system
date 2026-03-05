"""Route knowledge-base search node."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.models.schemas import UserProfile
from app.services.container import services
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)
_DAY_SUFFIX = "\u5929"


async def routes_kb_search_node(state: GraphState) -> dict[str, Any]:
    """Search route candidates from KB and fallback to hot routes when needed."""

    profile = _ensure_profile(state.get("user_profile"))
    trace_id = str(state.get("trace_id") or "-")

    workflow_service, route_service = _resolve_search_services()

    primary_query = _build_primary_query(profile)
    destination_only_query = _build_destination_query(profile)
    has_extra_query_conditions = _has_extra_query_conditions(profile)

    candidates = await _search_candidates(workflow_service, primary_query, trace_id) if primary_query else []

    should_retry_with_loose_query = (
        not candidates
        and has_extra_query_conditions
        and destination_only_query
        and destination_only_query != primary_query
    )
    if should_retry_with_loose_query:
        candidates = await _search_candidates(workflow_service, destination_only_query, trace_id)

    if not candidates:
        hot_routes = await route_service.get_hot_routes()
        candidates = [_hot_route_to_candidate(route) for route in hot_routes]

    return {"tool_results": {"candidates": candidates}}


def _resolve_search_services() -> tuple[Any, Any]:
    try:
        return services.workflow_service, services.route_service
    except Exception as exc:
        raise RuntimeError("service container is not initialized for kb search node") from exc


def _ensure_profile(value: Any) -> UserProfile:
    if isinstance(value, UserProfile):
        return value
    if isinstance(value, dict):
        return UserProfile.model_validate(value)
    return UserProfile()


def _build_primary_query(profile: UserProfile) -> str:
    destinations = " ".join([v for v in profile.destinations if str(v).strip()]).strip()

    days_range = (profile.days_range or "").strip()
    days_part = ""
    if days_range:
        days_part = days_range if days_range.endswith(_DAY_SUFFIX) else f"{days_range}{_DAY_SUFFIX}"

    style_part = " ".join([v for v in profile.style_prefs if str(v).strip()]).strip()
    budget_part = (profile.budget_range or "").strip()

    parts = [destinations, days_part, style_part, budget_part]
    return " ".join([part for part in parts if part]).strip()


def _build_destination_query(profile: UserProfile) -> str:
    return " ".join([v for v in profile.destinations if str(v).strip()]).strip()


def _has_extra_query_conditions(profile: UserProfile) -> bool:
    return bool(
        (profile.days_range and profile.days_range.strip())
        or (profile.budget_range and profile.budget_range.strip())
        or profile.style_prefs
    )


async def _search_candidates(workflow_service: Any, query: str, trace_id: str) -> list[dict[str, Any]]:
    try:
        result = await workflow_service.run_route_search(query=query, trace_id=trace_id)
    except Exception as exc:
        _LOGGER.warning(f"route kb search failed query={query!r}: {exc}")
        return []

    raw_candidates = getattr(result, "candidates", None)
    if not isinstance(raw_candidates, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_candidates:
        if hasattr(item, "model_dump"):
            payload = item.model_dump()
        elif isinstance(item, dict):
            payload = dict(item)
        else:
            continue
        normalized.append(payload)

    return normalized


def _hot_route_to_candidate(route_card: Any) -> dict[str, Any]:
    payload = route_card.model_dump() if hasattr(route_card, "model_dump") else dict(route_card)
    route_id = payload.get("id")
    route_id_str = _to_int_str_or_none(route_id)
    return {
        "document_id": f"hot_route_{route_id}",
        "route_id": route_id_str,
        "output": str(payload.get("summary") or ""),
        "hot_route": payload,
    }


def _to_int_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(int(value))
    except (TypeError, ValueError):
        _LOGGER.warning(f"hot route id is not int-convertible, id={value}")
        return None
