"""Rematch reset node."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import GraphState, STAGE_REMATCH_COLLECTING
from app.prompts.rematch_confirm import build_rematch_confirm_prompt
from app.services.container import services
from app.services.llm_client import LLMClient
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
    confirmed = await _is_confirmed_rematch(user_message)
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


async def _is_confirmed_rematch(user_message: str) -> bool:
    llm_client, should_close = _resolve_llm_client()
    try:
        messages = build_rematch_confirm_prompt(user_message)
        result = await llm_client.chat(messages=messages, temperature=0.0, max_tokens=8)
        normalized = str(result or "").strip()
        if normalized == "1":
            return True
        if normalized == "2":
            return False
    except Exception as exc:
        _LOGGER.warning(f"rematch confirmation failed, use fallback: {exc}")
    finally:
        if should_close:
            await llm_client.aclose()

    return _fallback_confirm_rematch(user_message)


def _resolve_llm_client() -> tuple[LLMClient, bool]:
    try:
        return services.llm_client, False
    except Exception:
        return LLMClient(), True


def _fallback_confirm_rematch(user_message: str) -> bool:
    text = user_message.strip()
    if not text:
        return False
    return any(re.search(pattern, text) for pattern in _EXPLICIT_REMATCH_PATTERNS)


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
