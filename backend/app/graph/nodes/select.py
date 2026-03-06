"""Candidate selection node."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)


async def select_candidates_node(state: GraphState) -> dict[str, Any]:
    """Select top candidates after excluding blocked route ids."""

    tool_results = state.get("tool_results") or {}
    raw_candidates = tool_results.get("candidates") if isinstance(tool_results, dict) else []
    candidates: list[dict[str, Any]] = raw_candidates if isinstance(raw_candidates, list) else []

    excluded_ids = _normalize_int_set(state.get("excluded_route_ids", []))

    selected_route_ids: list[int] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        raw_route_id = candidate.get("route_id")
        route_id = _to_int_or_none(raw_route_id)
        if raw_route_id is not None and route_id is None:
            _LOGGER.warning(
                "candidate route_id is not int-convertible, skipped "
                f"document_id={candidate.get('document_id')} raw_route_id={raw_route_id}"
            )
        if route_id is None:
            continue
        if route_id in excluded_ids:
            continue
        if route_id in selected_route_ids:
            continue
        selected_route_ids.append(route_id)
        if len(selected_route_ids) >= 3:
            break

    active_route_id = selected_route_ids[0] if selected_route_ids else None
    if not selected_route_ids and candidates:
        return {
            "active_route_id": None,
            "candidate_route_ids": [],
            "tool_results": {"candidates_raw": candidates},
        }
    return {
        "active_route_id": active_route_id,
        "candidate_route_ids": selected_route_ids,
    }


def _normalize_int_set(values: Any) -> set[int]:
    if not isinstance(values, list):
        return set()
    normalized: set[int] = set()
    for value in values:
        parsed = _to_int_or_none(value)
        if parsed is not None:
            normalized.add(parsed)
    return normalized


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
