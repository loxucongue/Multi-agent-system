"""Candidate selection node."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState
from app.graph.utils import to_int_or_none as _to_int_or_none_shared
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)


async def select_candidates_node(state: GraphState) -> dict[str, Any]:
    """Select top candidates after excluding blocked route ids."""

    tool_results = state.get("tool_results") or {}
    raw_candidates = tool_results.get("candidates") if isinstance(tool_results, dict) else []
    candidates: list[dict[str, Any]] = raw_candidates if isinstance(raw_candidates, list) else []

    excluded_ids = _normalize_int_set(state.get("excluded_route_ids", []))

    user_profile = state.get("user_profile")
    user_message = str(state.get("current_user_message") or "")
    destination_keywords = _extract_destination_keywords(user_profile, user_message)
    bonus_keywords = _extract_bonus_keywords(user_profile)

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

        score = _candidate_match_score(
            candidate=candidate,
            destination_keywords=destination_keywords,
            bonus_keywords=bonus_keywords,
        )
        if score <= 0:
            continue

        selected_scored.append((route_id, score, idx))

    selected_scored.sort(key=lambda item: (-item[1], item[2]))
    selected_route_ids = [route_id for route_id, _, _ in selected_scored[:3]]

    active_route_id = selected_route_ids[0] if selected_route_ids else None
    if not selected_route_ids and (destination_keywords or bonus_keywords) and candidates:
        _LOGGER.info(
            "no candidate matched profile, destination_keywords=%s bonus_keywords=%s total_candidates=%s",
            destination_keywords,
            bonus_keywords,
            len(candidates),
        )
        return {
            "active_route_id": None,
            "candidate_route_ids": [],
            "tool_results": {
                "candidates_filtered_out": candidates,
                "filter_warning": "no_candidate_matched_profile",
                "destination_keywords": destination_keywords,
                "bonus_keywords": bonus_keywords,
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


def _extract_destination_keywords(user_profile: Any, user_message: str) -> list[str]:
    profile_dict = _to_profile_dict(user_profile)
    profile_destinations: list[str] = []

    destinations = profile_dict.get("destinations")
    if isinstance(destinations, list):
        profile_destinations = [str(item).strip() for item in destinations if str(item).strip()]

    # If user explicitly says "去迪拜", prefer current-turn destination over stale profile values.
    message_destinations = _extract_destinations_from_message(user_message)
    if message_destinations:
        return message_destinations

    return _dedupe_preserve_order(profile_destinations)


def _extract_bonus_keywords(user_profile: Any) -> list[str]:
    profile_dict = _to_profile_dict(user_profile)
    keywords: list[str] = []

    style_prefs = profile_dict.get("style_prefs")
    if isinstance(style_prefs, list):
        keywords.extend([str(item).strip() for item in style_prefs if str(item).strip()])

    for key in ("days_range", "budget_range", "depart_date_range", "people", "origin_city"):
        value = str(profile_dict.get(key) or "").strip()
        if value:
            keywords.append(value)

    return _dedupe_preserve_order(keywords)


def _to_profile_dict(user_profile: Any) -> dict[str, Any]:
    if isinstance(user_profile, dict):
        return user_profile
    if hasattr(user_profile, "model_dump"):
        return user_profile.model_dump()
    return {}


def _extract_destinations_from_message(user_message: str) -> list[str]:
    text = str(user_message or "").strip()
    if not text:
        return []
    # Use unicode escapes to avoid source-encoding issues in terminals.
    matches = re.findall(r"(?:\u53bb|\u5230|\u60f3\u53bb)\s*([\u4e00-\u9fa5A-Za-z]{2,12})", text)
    candidates: list[str] = []
    for item in matches:
        normalized = _normalize_destination_token(item)
        if normalized:
            candidates.append(normalized)
    return _dedupe_preserve_order(candidates)


def _normalize_destination_token(token: str) -> str:
    text = str(token or "").strip()
    if not text:
        return ""

    suffixes = ("跟团游", "自由行", "旅游", "旅行", "跟团", "度假", "游玩", "玩")
    changed = True
    while changed and text:
        changed = False
        for suffix in suffixes:
            if text.endswith(suffix) and len(text) > len(suffix):
                text = text[: -len(suffix)].strip()
                changed = True
                break
    return text


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _candidate_match_score(
    candidate: dict[str, Any],
    destination_keywords: list[str],
    bonus_keywords: list[str],
) -> int:
    combined = _get_candidate_text(candidate)

    # Destination is a hard filter when available.
    if destination_keywords and not any(keyword and keyword in combined for keyword in destination_keywords):
        return 0

    # Destination match should dominate ranking; extra dimensions refine order.
    score = 100 if destination_keywords else 1
    score += sum(1 for keyword in bonus_keywords if keyword and keyword in combined)
    return score


def _get_candidate_text(candidate: dict[str, Any]) -> str:
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
                str(hot_route.get("base_info") or ""),
                " ".join(str(tag) for tag in hot_route.get("tags", []) if str(tag).strip())
                if isinstance(hot_route.get("tags"), list)
                else "",
            ]
        )

    return " ".join(text_parts)


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
    return _to_int_or_none_shared(value)
