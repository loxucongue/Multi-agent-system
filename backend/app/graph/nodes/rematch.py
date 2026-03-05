"""Rematch reset node."""

from __future__ import annotations

from typing import Any

from app.graph.state import GraphState


async def rematch_reset_node(state: GraphState) -> dict[str, Any]:
    """Reset route selection context and mark rematch flow entry."""

    excluded_ids = _normalize_int_list(state.get("excluded_route_ids", []))
    active_route_id = _to_int_or_none(state.get("active_route_id"))
    candidate_route_ids = _normalize_int_list(state.get("candidate_route_ids", []))

    merged_excluded = list(excluded_ids)
    if active_route_id is not None and active_route_id not in merged_excluded:
        merged_excluded.append(active_route_id)
    for rid in candidate_route_ids:
        if rid not in merged_excluded:
            merged_excluded.append(rid)

    return {
        "excluded_route_ids": merged_excluded,
        "active_route_id": None,
        "candidate_route_ids": [],
        "followup_count": 0,
        "from_rematch": True,
    }


def _normalize_int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    normalized: list[int] = []
    for value in values:
        parsed = _to_int_or_none(value)
        if parsed is not None and parsed not in normalized:
            normalized.append(parsed)
    return normalized


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
