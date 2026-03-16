"""Helpers for structured route content fields."""

from __future__ import annotations

import json
import re
from typing import Any


def flatten_text(value: Any) -> str:
    """Convert route content values into a readable plain-text string."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [flatten_text(item) for item in value]
        return "；".join(part for part in parts if part)
    if isinstance(value, dict):
        preferred_order = [
            "title",
            "destination_country",
            "total_days",
            "total_nights",
            "day_title",
            "poi_name",
            "activity",
            "hotel_name",
            "hotel_level",
        ]
        ordered_keys = [key for key in preferred_order if key in value]
        ordered_keys.extend(key for key in value.keys() if key not in ordered_keys)

        parts: list[str] = []
        for key in ordered_keys:
            nested = flatten_text(value.get(key))
            if not nested:
                continue
            if key in {"total_days", "total_nights"}:
                label = "天数" if key == "total_days" else "晚数"
                parts.append(f"{label}:{nested}")
            elif key in {"title", "destination_country"}:
                parts.append(nested)
            else:
                parts.append(f"{key}:{nested}")
        return "；".join(parts)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value).strip()


def ensure_string_list(value: Any) -> list[str]:
    """Normalize route content into a list of readable strings."""

    if value is None:
        return []
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            text = flatten_text(item)
            if text:
                normalized.append(text)
        return normalized
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return ensure_string_list(parsed)
        tokens = re.split(r"[；;\n]+", text)
        normalized = [token.strip() for token in tokens if token.strip()]
        return normalized or [text]

    text = flatten_text(value)
    return [text] if text else []


def ensure_dict(value: Any) -> dict[str, Any]:
    """Normalize route content into a dict."""

    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def ensure_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    """Normalize route itinerary into a list of dicts."""

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        return ensure_list_of_dicts(parsed)
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def infer_route_days(itinerary_json: Any, base_info: Any) -> int | None:
    """Infer route days from itinerary structure first, then basic_info."""

    itinerary_days = ensure_list_of_dicts(itinerary_json)
    if itinerary_days:
        return len(itinerary_days)

    base_info_dict = ensure_dict(base_info)
    total_days = base_info_dict.get("total_days")
    try:
        if total_days is not None:
            parsed = int(total_days)
            if parsed > 0:
                return parsed
    except (TypeError, ValueError):
        pass

    base_info_text = flatten_text(base_info)
    match = re.search(r"(\d+)\s*天", base_info_text)
    if match:
        return int(match.group(1))
    return None


def extract_highlight_tags(highlights: Any, limit: int = 3) -> list[str]:
    """Extract short highlight items for cards and compare views."""

    items = ensure_string_list(highlights)
    return items[:limit]


def summarize_route_field(value: Any, limit: int) -> str:
    """Summarize structured route content into a compact string."""

    text = flatten_text(value)
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit]
