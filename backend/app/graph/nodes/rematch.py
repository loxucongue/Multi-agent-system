"""Rematch reset node."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState, STAGE_REMATCH_COLLECTING
from app.graph.utils import normalize_int_list as _normalize_int_list_shared
from app.graph.utils import to_int_or_none as _to_int_or_none_shared
from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)
_EXPLICIT_REMATCH_PATTERNS = (
    r"换一批",
    r"重新推荐",
    r"重新匹配",
    r"有没有其他方案",
    r"再推荐几条",
    r"再来几条",
    r"换几条",
    r"换个方案",
)


async def rematch_reset_node(state: GraphState) -> dict[str, Any]:
    """Reset route selection context and mark rematch flow entry."""

    user_message = str(state.get("current_user_message") or "").strip()
    confirmed = _fallback_confirm_rematch(user_message)
    if not confirmed:
        return {
            "response_text": "请问是否需要重新为您匹配新的路线呢？",
            "request_human": True,
            "slots_ready": False,
        }

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
        "stage": STAGE_REMATCH_COLLECTING,
        "slots_ready": False,
        "request_human": False,
    }


def _fallback_confirm_rematch(user_message: str) -> bool:
    text = user_message.strip()
    if not text:
        return False
    return any(re.search(pattern, text) for pattern in _EXPLICIT_REMATCH_PATTERNS)


def _normalize_int_list(values: Any) -> list[int]:
    return _normalize_int_list_shared(values, dedupe=True)


def _to_int_or_none(value: Any) -> int | None:
    return _to_int_or_none_shared(value)
