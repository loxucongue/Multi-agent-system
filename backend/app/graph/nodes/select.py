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

    user_profile = state.get("user_profile")
    matching_keywords = _extract_match_keywords(user_profile)

    selected_scored: list[tuple[int, int, int]] = []
    for idx, candidate in enumerate(candidates):
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
        if any(existing_id == route_id for existing_id, _, _ in selected_scored):
            continue
        if matching_keywords:
            score = _candidate_match_score(candidate, matching_keywords)
            if score <= 0:
                continue
        else:
            score = 1
        selected_scored.append((route_id, score, idx))

    selected_scored.sort(key=lambda item: (-item[1], item[2]))
    selected_route_ids = [route_id for route_id, _, _ in selected_scored[:3]]

    active_route_id = selected_route_ids[0] if selected_route_ids else None
    if not selected_route_ids and matching_keywords and candidates:
        return {
            "active_route_id": None,
            "candidate_route_ids": [],
            "tool_results": {
                "candidates_filtered_out": candidates,
                "filter_warning": "no_candidate_matched_profile",
            },
        }
    if not selected_route_ids and candidates:
        return {
            "active_route_id": None,
            "candidate_route_ids": [],
            "tool_results": {
                "candidates_without_id": candidates,
                "parse_warning": "route_id解析失败，请检查知识库文档格式",
            },
        }
    return {
        "active_route_id": active_route_id,
        "candidate_route_ids": selected_route_ids,
    }


def _extract_match_keywords(user_profile: Any) -> list[str]:
    if not isinstance(user_profile, dict):
        if hasattr(user_profile, "model_dump"):
            user_profile = user_profile.model_dump()
        else:
            return []

    keywords: list[str] = []
    destinations = user_profile.get("destinations")
    if isinstance(destinations, list):
        keywords.extend([str(item).strip() for item in destinations if str(item).strip()])

    style_prefs = user_profile.get("style_prefs")
    if isinstance(style_prefs, list):
        keywords.extend([str(item).strip() for item in style_prefs if str(item).strip()])

    days_range = str(user_profile.get("days_range") or "").strip()
    if days_range:
        keywords.append(days_range)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in keywords:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _candidate_match_score(candidate: dict[str, Any], keywords: list[str]) -> int:
    text_parts: list[str] = [
        str(candidate.get("output") or ""),
        str(candidate.get("document_id") or ""),
    ]
    hot_route = candidate.get("hot_route")
    if isinstance(hot_route, dict):
        text_parts.extend(
            [
                str(hot_route.get("name") or ""),
                str(hot_route.get("summary") or ""),
                " ".join(str(tag) for tag in hot_route.get("tags", []) if str(tag).strip())
                if isinstance(hot_route.get("tags"), list)
                else "",
            ]
        )

    combined = " ".join(text_parts)
    return sum(1 for keyword in keywords if keyword and keyword in combined)


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
