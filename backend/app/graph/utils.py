"""Shared graph node utility helpers.

Centralize frequently duplicated helpers used across graph nodes.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.schemas import UserProfile
from app.services.container import services
from app.services.llm_client import LLMClient


def to_int_or_none(value: Any) -> int | None:
    """Convert value to int if possible, otherwise return None."""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_int_list(values: Any, dedupe: bool = False) -> list[int]:
    """Normalize arbitrary value to a list of ints."""

    if not isinstance(values, list):
        return []

    normalized: list[int] = []
    for value in values:
        parsed = to_int_or_none(value)
        if parsed is None:
            continue
        if dedupe and parsed in normalized:
            continue
        normalized.append(parsed)
    return normalized


def ensure_profile(value: Any) -> UserProfile:
    """Normalize unknown profile payload to UserProfile."""

    if isinstance(value, UserProfile):
        return value
    if isinstance(value, dict):
        return UserProfile.model_validate(value)
    return UserProfile()


def normalize_history(value: Any) -> list[dict[str, str]]:
    """Normalize context turns to [{user, assistant}] list."""

    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        user = str(item.get("user") or "").strip()
        assistant = str(item.get("assistant") or "").strip()
        if not user and not assistant:
            continue
        normalized.append({"user": user, "assistant": assistant})
    return normalized


def resolve_llm_client() -> tuple[LLMClient, bool]:
    """Return container llm client or a temporary fallback client.

    Returns:
        tuple(client, should_close)
    """

    try:
        return services.llm_client, False
    except Exception:
        return LLMClient(), True


def extract_profile_destinations(state: dict[str, Any]) -> list[str]:
    """Extract deduplicated destination list from state user_profile."""

    profile = state.get("user_profile")
    raw: list[str] = []

    if hasattr(profile, "destinations") and isinstance(profile.destinations, list):
        raw = [str(item).strip() for item in profile.destinations if str(item).strip()]
    elif isinstance(profile, dict):
        raw_destinations = profile.get("destinations")
        if isinstance(raw_destinations, list):
            raw = [str(item).strip() for item in raw_destinations if str(item).strip()]

    seen: set[str] = set()
    deduped: list[str] = []
    for d in raw:
        if d not in seen:
            seen.add(d)
            deduped.append(d)
    return deduped


_DEST_PATTERN = re.compile(r"(?:去|到|想去)\s*([\u4e00-\u9fa5A-Za-z]{2,12})")


def extract_destinations_from_text(text: str) -> list[str]:
    """Extract destination keywords from free text via regex."""

    message = str(text or "").strip()
    if not message:
        return []
    matches = _DEST_PATTERN.findall(message)
    seen: set[str] = set()
    deduped: list[str] = []
    for item in matches:
        lower = str(item).strip().lower()
        if lower and lower not in seen:
            seen.add(lower)
            deduped.append(lower)
    return deduped

